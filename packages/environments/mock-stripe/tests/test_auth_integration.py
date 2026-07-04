"""Integration tests for the auth retrofit (AUTH_ENABLED).

Fully offline: JWKS is injected statically via env_0_auth_client.testing, and
event reporting is disabled (AUTH_REPORT=0) except where a MockTransport
captures events explicitly.

The FastAPI app in mock_stripe.api.app is a module-level singleton and
AUTH_ENABLED is read at import time, so the ``auth_app`` fixture builds a
FRESH instance via importlib.reload (with auth disabled, so the module-level
``_apply_auth(app)`` is a no-op) and then applies the middleware explicitly with
the static JWKS. Teardown reloads once more so every other test module keeps
using a pristine, auth-disabled singleton.

Token coexistence (stripe-specific): stripe's legacy auth is a per-request
``sk_test_`` API-key dependency (Bearer or HTTP Basic). An ``sk_test_`` key is
NOT a JWT (no three-dot header.payload.signature structure), so with
AUTH_ENABLED=1 the middleware rejects a bare key as malformed/non-Bearer
(401); keys keep working only in disabled mode. stripe is single-tenant
with no {userId} path params, so there is NO impersonation guard -- the value
here is per-resource scope enforcement (least privilege over Stripe ops).
"""

from __future__ import annotations

import importlib
import json
import sys

import httpx
import pytest
from fastapi import FastAPI
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from env_0_auth_client.testing import generate_test_keypair, jwks_for, make_jwt
from mock_stripe.models import init_db, reset_engine
from mock_stripe.seed.generator import DEFAULT_API_KEY

KID = "test-key-001"
PRIVATE_KEY, PUBLIC_KEY = generate_test_keypair()
JWKS = jwks_for(PUBLIC_KEY, kid=KID)

# stripe is single-tenant; the token sub is recorded but never used as a
# path identity. client_id mirrors the seeded confidential client.
SUB = "user1"
CLIENT_ID = "stripe-agent"

FORM = {"Content-Type": "application/x-www-form-urlencoded"}


def _token(scope: str = "", sub: str = SUB, **kwargs) -> str:
    return make_jwt(private_key=PRIVATE_KEY, kid=KID, sub=sub,
                    client_id=CLIENT_ID, scope=scope, **kwargs)


def _bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def auth_app(monkeypatch):
    """Fresh app instance with StripeMockAuthMiddleware and static (offline) JWKS."""
    for var in ("AUTH_ENABLED", "AUTH_INTROSPECT", "AUTH_ISSUER", "AUTH_URL"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("AUTH_REPORT", "0")

    import mock_stripe.api.app as app_module

    app_module = importlib.reload(app_module)  # fresh singleton, no auth yet
    monkeypatch.setenv("AUTH_ENABLED", "1")
    assert app_module._apply_auth(app_module.app, jwks_static=JWKS) is True

    yield app_module.app

    # Restore a pristine auth-disabled singleton for the other test modules.
    monkeypatch.delenv("AUTH_ENABLED", raising=False)
    importlib.reload(app_module)


@pytest.fixture
def auth_client(auth_app, seeded_db):
    """TestClient against the auth-enabled fresh app + seeded temp database."""
    reset_engine()
    init_db(seeded_db)
    with TestClient(auth_app) as c:
        yield c
    reset_engine()


# ---------------------------------------------------------------------------
class TestScopeMapCoverage:
    def test_every_v1_route_has_scope_map_entry(self):
        """Every registered /v1 route must appear in STRIPE_SCOPE_MAP (no gaps,
        no stale keys)."""
        from mock_stripe.api.app import app
        from mock_stripe.auth_scopes import STRIPE_SCOPE_MAP

        registered = set()
        for route in app.routes:
            if isinstance(route, APIRoute) and route.path.startswith("/v1"):
                for method in route.methods:
                    if method not in ("HEAD", "OPTIONS"):
                        registered.add((method, route.path))

        assert registered, "no /v1 routes registered -- enumeration broken?"
        missing = registered - set(STRIPE_SCOPE_MAP)
        assert not missing, f"routes missing from STRIPE_SCOPE_MAP: {sorted(missing)}"
        stale = set(STRIPE_SCOPE_MAP) - registered
        assert not stale, f"STRIPE_SCOPE_MAP keys matching no registered route: {sorted(stale)}"

    def test_scope_lists_are_stripe_style(self):
        from mock_stripe.auth_scopes import STRIPE_SCOPE_MAP

        for key, scopes in STRIPE_SCOPE_MAP.items():
            assert scopes, f"empty scope list for {key}"
            for scope in scopes:
                assert scope.startswith("stripe."), f"non-Stripe scope {scope!r} for {key}"

    def test_write_routes_require_write_or_full_only(self):
        """A mutating route must be satisfied ONLY by <res>.write or stripe.full
        (read_only / <res>.read must NOT appear)."""
        from mock_stripe.auth_scopes import STRIPE_SCOPE_MAP

        write_keys = [
            ("POST", "/v1/payment_intents"),
            ("POST", "/v1/payment_intents/{pi_id}/confirm"),
            ("POST", "/v1/refunds"),
            ("POST", "/v1/customers"),
            ("DELETE", "/v1/customers/{customer_id}"),
        ]
        for key in write_keys:
            scopes = STRIPE_SCOPE_MAP[key]
            assert "stripe.read_only" not in scopes, key
            assert all(s.endswith(".write") or s == "stripe.full" for s in scopes), (key, scopes)

    def test_every_non_v1_route_is_exempt(self):
        """Web dashboard root, admin, docs, redoc and mcp routes bypass auth."""
        from mock_stripe.api.app import app
        from mock_stripe.api.auth_middleware import (
            EXEMPT_EXACT_PATHS,
            StripeMockAuthMiddleware,
        )

        mw = StripeMockAuthMiddleware(app, jwks_static=JWKS)
        not_exempt = []
        for route in app.routes:
            path = getattr(route, "path", None)
            if path is None or path.startswith("/v1"):
                continue
            if path in EXEMPT_EXACT_PATHS or mw._is_exempt(path):
                continue
            not_exempt.append(path)
        assert not not_exempt, f"non-/v1 routes not covered by exemptions: {sorted(not_exempt)}"

    def test_exempt_prefixes_extend_contract_defaults(self):
        from env_0_auth_client.middleware import DEFAULT_EXEMPT_PREFIXES
        from mock_stripe.api.auth_middleware import STRIPE_EXEMPT_PREFIXES

        for prefix in DEFAULT_EXEMPT_PREFIXES:
            assert prefix in STRIPE_EXEMPT_PREFIXES
        for prefix in ("/static", "/mcp", "/redoc"):
            assert prefix in STRIPE_EXEMPT_PREFIXES


# ---------------------------------------------------------------------------
class TestAuthEnabledScopeEnforcement:
    def test_payment_intents_write_confirms_a_pi(self, auth_client):
        token = _token("stripe.payment_intents.write")
        created = auth_client.post(
            "/v1/payment_intents",
            headers={**_bearer(token), **FORM},
            content="amount=1099&currency=usd&automatic_payment_methods[enabled]=true",
        )
        assert created.status_code == 200, created.text
        pi = created.json()
        confirmed = auth_client.post(
            f"/v1/payment_intents/{pi['id']}/confirm",
            headers=_bearer(token),
            data={"payment_method": "pm_card_visa"},
        )
        assert confirmed.status_code == 200, confirmed.text
        body = confirmed.json()
        assert body["status"] == "succeeded"
        assert body["amount_received"] == 1099

    def test_customers_read_can_list_customers(self, auth_client):
        resp = auth_client.get("/v1/customers", headers=_bearer(_token("stripe.customers.read")))
        assert resp.status_code == 200
        assert resp.json()["object"] == "list"

    def test_customers_read_cannot_create_payment_intent(self, auth_client):
        resp = auth_client.post(
            "/v1/payment_intents",
            headers={**_bearer(_token("stripe.customers.read")), **FORM},
            content="amount=500&currency=usd",
        )
        assert resp.status_code == 403
        err = resp.json()["error"]
        assert err["code"] == 403
        assert err["status"] == "PERMISSION_DENIED"
        assert err["required_scopes"] == ["stripe.payment_intents.write", "stripe.full"]
        assert err["token_scopes"] == ["stripe.customers.read"]
        assert "hint" in err

    def test_write_scope_satisfies_reads_on_same_resource(self, auth_client):
        # write implies read: customers.write can GET /v1/customers.
        resp = auth_client.get("/v1/customers", headers=_bearer(_token("stripe.customers.write")))
        assert resp.status_code == 200

    def test_read_only_satisfies_any_read(self, auth_client):
        for path in ("/v1/customers", "/v1/balance", "/v1/charges", "/v1/events"):
            resp = auth_client.get(path, headers=_bearer(_token("stripe.read_only")))
            assert resp.status_code == 200, (path, resp.text)

    def test_read_only_denied_on_write(self, auth_client):
        resp = auth_client.post(
            "/v1/refunds",
            headers={**_bearer(_token("stripe.read_only")), **FORM},
            content="payment_intent=pi_nonexistent",
        )
        assert resp.status_code == 403
        err = resp.json()["error"]
        assert err["required_scopes"] == ["stripe.refunds.write", "stripe.full"]
        assert err["token_scopes"] == ["stripe.read_only"]

    def test_full_satisfies_everything(self, auth_client):
        token = _token("stripe.full")
        assert auth_client.get("/v1/customers", headers=_bearer(token)).status_code == 200
        created = auth_client.post(
            "/v1/customers", headers={**_bearer(token), **FORM}, content="name=Full Scope",
        )
        assert created.status_code == 200

    def test_balance_read_requires_balance_scope(self, auth_client):
        denied = auth_client.get("/v1/balance", headers=_bearer(_token("stripe.customers.read")))
        assert denied.status_code == 403
        assert denied.json()["error"]["required_scopes"] == [
            "stripe.balance.read", "stripe.read_only", "stripe.full",
        ]
        allowed = auth_client.get("/v1/balance", headers=_bearer(_token("stripe.balance.read")))
        assert allowed.status_code == 200
        assert allowed.json()["object"] == "balance"

    def test_account_accepts_any_stripe_scope(self, auth_client):
        # /v1/account is the lowest-privilege read: any Stripe scope grants it.
        for scope in ("stripe.customers.read", "stripe.refunds.write", "stripe.read_only"):
            resp = auth_client.get("/v1/account", headers=_bearer(_token(scope)))
            assert resp.status_code == 200, (scope, resp.text)


# ---------------------------------------------------------------------------
class TestAuthEnabledTokenValidation:
    def test_no_token_401_with_www_authenticate(self, auth_client):
        resp = auth_client.get("/v1/customers")
        assert resp.status_code == 401
        err = resp.json()["error"]
        assert err["code"] == 401
        assert err["status"] == "UNAUTHENTICATED"
        assert "WWW-Authenticate" in resp.headers

    def test_bare_sk_test_key_under_auth_is_401(self, auth_client):
        """Coexistence rule: a legacy sk_test_ key is not a JWT, so the
        middleware rejects it (401) -- it never reaches require_api_key."""
        resp = auth_client.get("/v1/customers", headers=_bearer(DEFAULT_API_KEY))
        assert resp.status_code == 401
        err = resp.json()["error"]
        assert err["status"] == "UNAUTHENTICATED"
        assert "malformed" in err["message"]

    def test_basic_auth_sk_test_key_under_auth_is_401(self, auth_client):
        import base64
        token = base64.b64encode(f"{DEFAULT_API_KEY}:".encode()).decode()
        resp = auth_client.get("/v1/customers", headers={"Authorization": f"Basic {token}"})
        assert resp.status_code == 401
        assert resp.json()["error"]["status"] == "UNAUTHENTICATED"

    def test_expired_token_401_with_refresh_hint(self, auth_client):
        resp = auth_client.get(
            "/v1/customers", headers=_bearer(_token("stripe.customers.read", expires_in=-60)),
        )
        assert resp.status_code == 401
        err = resp.json()["error"]
        assert err["status"] == "UNAUTHENTICATED"
        assert "expired at" in err["message"]
        assert "/oauth2/token" in err["hint"]
        assert "grant_type=refresh_token" in err["hint"]
        assert resp.headers["WWW-Authenticate"].startswith('Bearer error="invalid_token"')

    def test_bad_signature_401(self, auth_client):
        other_private, _ = generate_test_keypair()
        forged = make_jwt(private_key=other_private, kid=KID, sub=SUB,
                          client_id=CLIENT_ID, scope="stripe.full")
        resp = auth_client.get("/v1/customers", headers=_bearer(forged))
        assert resp.status_code == 401
        assert resp.json()["error"]["status"] == "UNAUTHENTICATED"

    def test_options_bypass_auth(self, auth_client):
        resp = auth_client.options("/v1/customers")
        assert resp.status_code != 401


# ---------------------------------------------------------------------------
class TestSecurityEventReporting:
    """The middleware reports scope_escalation_attempt / invalid_token /
    resource_access back to auth (fire-and-forget). Confirm they fire."""

    def _capture(self, monkeypatch):
        from env_0_auth_client import reporting

        events: list[dict] = []

        def handler(request: httpx.Request) -> httpx.Response:
            events.append(json.loads(request.content))
            return httpx.Response(200, json={"status": "ok"})

        monkeypatch.setenv("AUTH_REPORT", "1")  # read at call time
        reporting.set_transport(httpx.MockTransport(handler))
        return events

    def test_scope_escalation_attempt_reported(self, auth_client, monkeypatch):
        from env_0_auth_client import reporting

        events = self._capture(monkeypatch)
        try:
            resp = auth_client.post(
                "/v1/payment_intents",
                headers={**_bearer(_token("stripe.customers.read")), **FORM},
                content="amount=500&currency=usd",
            )
            assert resp.status_code == 403
        finally:
            reporting.set_transport(None)

        escalations = [e for e in events if e["event_type"] == "scope_escalation_attempt"]
        assert escalations, f"no scope_escalation_attempt among: {events}"
        ev = escalations[0]
        assert ev["client_id"] == CLIENT_ID
        assert ev["details"]["required_scopes"] == ["stripe.payment_intents.write", "stripe.full"]
        assert ev["details"]["token_scopes"] == ["stripe.customers.read"]

    def test_invalid_token_reported(self, auth_client, monkeypatch):
        from env_0_auth_client import reporting

        events = self._capture(monkeypatch)
        try:
            resp = auth_client.get("/v1/customers", headers=_bearer(DEFAULT_API_KEY))
            assert resp.status_code == 401
        finally:
            reporting.set_transport(None)

        assert any(e["event_type"] == "invalid_token" for e in events), events

    def test_resource_access_reported_on_2xx(self, auth_client, monkeypatch):
        from env_0_auth_client import reporting

        events = self._capture(monkeypatch)
        try:
            resp = auth_client.get("/v1/customers", headers=_bearer(_token("stripe.customers.read")))
            assert resp.status_code == 200
        finally:
            reporting.set_transport(None)

        accesses = [e for e in events if e["event_type"] == "resource_access"]
        assert accesses, f"no resource_access among: {events}"
        assert accesses[0]["details"]["route"] == "/v1/customers"


# ---------------------------------------------------------------------------
class TestWebUIAndExemptions:
    """With AUTH_ENABLED=1 the web dashboard root and admin/health/docs
    stay reachable WITHOUT a token; the /v1 API still requires a JWT."""

    def test_dashboard_root_no_token_200(self, auth_client):
        resp = auth_client.get("/")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]

    def test_root_with_query_params_no_token_200(self, auth_client):
        resp = auth_client.get("/", params={"foo": "bar"})
        assert resp.status_code == 200

    def test_health_no_token_200(self, auth_client):
        resp = auth_client.get("/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}

    def test_admin_state_no_token_200(self, auth_client):
        assert auth_client.get("/_admin/state").status_code == 200

    def test_web_prefix_does_not_exempt_webhook_endpoints(self, auth_client):
        # Segment-boundary matching: the "/web" default prefix must never bleed
        # into "/v1/webhook_endpoints".
        resp = auth_client.get("/v1/webhook_endpoints")
        assert resp.status_code == 401

    def test_api_still_requires_token_while_dashboard_is_open(self, auth_client):
        assert auth_client.get("/").status_code == 200
        resp = auth_client.get("/v1/customers")
        assert resp.status_code == 401
        assert resp.json()["error"]["status"] == "UNAUTHENTICATED"


# ---------------------------------------------------------------------------
class TestSandboxFlowWithJwt:
    def test_benjasl_sandbox_flow_end_to_end(self, auth_client):
        """customer -> PI -> confirm -> refund, all with one sufficiently-scoped
        (stripe.full) JWT."""
        token = _token("stripe.full")
        auth = _bearer(token)

        customer = auth_client.post(
            "/v1/customers", headers={**auth, **FORM}, content="name=Sandbox Buyer",
        )
        assert customer.status_code == 200, customer.text
        cid = customer.json()["id"]

        pi = auth_client.post(
            "/v1/payment_intents",
            headers={**auth, **FORM},
            content=f"amount=2500&currency=usd&customer={cid}&automatic_payment_methods[enabled]=true",
        ).json()
        confirmed = auth_client.post(
            f"/v1/payment_intents/{pi['id']}/confirm",
            headers=auth, data={"payment_method": "pm_card_visa"},
        ).json()
        assert confirmed["status"] == "succeeded"

        refund = auth_client.post(
            "/v1/refunds", headers={**auth, **FORM},
            content=f"payment_intent={pi['id']}&amount=500",
        )
        assert refund.status_code == 200, refund.text
        assert refund.json()["status"] == "succeeded"

    def test_read_only_jwt_blocked_on_refund(self, auth_client):
        resp = auth_client.post(
            "/v1/refunds", headers={**_bearer(_token("stripe.read_only")), **FORM},
            content="payment_intent=pi_x&amount=500",
        )
        assert resp.status_code == 403
        assert resp.json()["error"]["required_scopes"] == ["stripe.refunds.write", "stripe.full"]


# ---------------------------------------------------------------------------
class TestAuthDisabledRegression:
    """CRITICAL: with AUTH_ENABLED unset, behavior is byte-identical legacy.

    The standard ``client`` fixture uses the module singleton (assembled with
    auth disabled). The legacy sk_test_ key dependency must keep working and no
    MockAuthMiddleware may be installed.
    """

    def test_singleton_has_no_auth_middleware(self, client):
        from mock_stripe.api.app import app

        assert not any(
            "MockAuthMiddleware" in m.cls.__name__ for m in app.user_middleware
        ), "auth middleware must not be installed when AUTH_ENABLED is unset"

    def test_sk_test_key_still_works(self, client):
        resp = client.get("/v1/customers", headers=_bearer(DEFAULT_API_KEY))
        assert resp.status_code == 200
        assert resp.json()["object"] == "list"

    def test_basic_auth_key_still_works(self, client):
        import base64
        token = base64.b64encode(f"{DEFAULT_API_KEY}:".encode()).decode()
        resp = client.get("/v1/customers", headers={"Authorization": f"Basic {token}"})
        assert resp.status_code == 200

    def test_missing_key_401_stripe_envelope(self, client):
        resp = client.get("/v1/customers")
        assert resp.status_code == 401
        # Legacy Stripe envelope (type+message), NOT the auth contract body.
        err = resp.json()["error"]
        assert err["type"] == "invalid_request_error"
        assert "did not provide an API key" in err["message"]

    def test_bad_key_401_stripe_envelope(self, client):
        resp = client.get("/v1/customers", headers=_bearer("sk_test_wrongwrongwrong"))
        assert resp.status_code == 401
        assert resp.json()["error"]["code"] == "api_key_invalid"

    def test_jwt_value_ignored_when_auth_disabled(self, client):
        # A JWT-shaped string is just an unknown key in legacy mode -> 401 bad key.
        forged = make_jwt(private_key=PRIVATE_KEY, kid=KID, sub=SUB,
                          client_id=CLIENT_ID, scope="stripe.full")
        resp = client.get("/v1/customers", headers=_bearer(forged))
        assert resp.status_code == 401
        assert resp.json()["error"]["code"] == "api_key_invalid"

    def test_apply_auth_returns_false_when_disabled(self, monkeypatch):
        import mock_stripe.api.app as app_module

        monkeypatch.delenv("AUTH_ENABLED", raising=False)
        assert app_module._apply_auth(FastAPI()) is False

    def test_apply_auth_raises_runtime_error_without_package(self, monkeypatch):
        import mock_stripe.api.app as app_module

        monkeypatch.setenv("AUTH_ENABLED", "1")
        monkeypatch.setitem(sys.modules, "env_0_auth_client", None)
        with pytest.raises(RuntimeError, match="auth-client is not installed"):
            app_module._apply_auth(FastAPI())
