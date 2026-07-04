"""Integration tests for the auth retrofit (AUTH_ENABLED).

Fully offline: JWKS is injected statically via env_0_auth_client.testing, and
event reporting is disabled (AUTH_REPORT=0) except where a MockTransport
captures events explicitly.

The FastAPI app in mock_gcal.api.app is a module-level singleton and
AUTH_ENABLED is read at import time, so the ``auth_app`` fixture builds a
FRESH instance via importlib.reload (with auth disabled, so the module-level
``_apply_auth(app)`` is a no-op) and then applies the middleware explicitly
with the static JWKS. Teardown reloads once more so every other test module
keeps using a pristine, auth-disabled singleton.
"""

import importlib
import json
import sys
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from fastapi import FastAPI
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from env_0_auth_client.testing import generate_test_keypair, jwks_for, make_jwt
from mock_gcal.models import init_db, reset_engine
from mock_gcal.seed.generator import seed_database

KID = "test-key-001"
PRIVATE_KEY, PUBLIC_KEY = generate_test_keypair()
JWKS = jwks_for(PUBLIC_KEY, kid=KID)

# Actual identities seeded by scenario "default", seed 42 (see
# mock_gcal/seed/generator.py): the auth seeds must match THESE ids.
ALICE = "user1"
ALICE_EMAIL = "alex@nexusai.com"
# Second user: only exists in DBs seeded with num_users=2 (two_user_client);
# for impersonation tests the check fires before any DB lookup, so the user
# does not need to exist in the seeded DB.
OTHER_USER = "user2"
OTHER_EMAIL = "alex2@nexusai.com"


def _token(scope: str = "", sub: str = ALICE, **kwargs) -> str:
    return make_jwt(private_key=PRIVATE_KEY, kid=KID, sub=sub, scope=scope, **kwargs)


def _bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _rfc3339(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _event_body(summary: str = "Auth test event") -> dict:
    start = datetime.now(timezone.utc).replace(microsecond=0) + timedelta(days=1)
    return {
        "summary": summary,
        "start": {"dateTime": _rfc3339(start)},
        "end": {"dateTime": _rfc3339(start + timedelta(hours=1))},
    }


def _freebusy_body() -> dict:
    now = datetime.now(timezone.utc).replace(microsecond=0)
    return {
        "timeMin": _rfc3339(now),
        "timeMax": _rfc3339(now + timedelta(days=2)),
        "items": [{"id": "primary"}],
    }


@pytest.fixture
def auth_app(monkeypatch):
    """Fresh app instance with Env_0AuthMiddleware and static (offline) JWKS."""
    for var in ("AUTH_ENABLED", "AUTH_INTROSPECT", "AUTH_ISSUER", "AUTH_URL"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("AUTH_REPORT", "0")

    # NOTE: `import mock_gcal.api.app as m` would bind the FastAPI INSTANCE
    # (mock_gcal/api/__init__.py does `from .app import app`, shadowing the
    # submodule attribute); import_module resolves the real module object.
    app_module = importlib.import_module("mock_gcal.api.app")

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


@pytest.fixture
def two_user_db(db_path):
    """Temp DB seeded with TWO users (user1 + user2) for header-bypass tests."""
    reset_engine()
    seed_database(scenario="default", seed=42, db_path=db_path, num_users=2)
    return db_path


@pytest.fixture
def two_user_auth_client(auth_app, two_user_db):
    """Auth-enabled TestClient against the two-user database."""
    reset_engine()
    init_db(two_user_db)
    with TestClient(auth_app) as c:
        yield c
    reset_engine()


@pytest.fixture
def two_user_client(two_user_db):
    """Legacy (auth-disabled) TestClient against the two-user database."""
    reset_engine()
    init_db(two_user_db)
    from mock_gcal.api.app import app

    with TestClient(app) as c:
        yield c
    reset_engine()


class TestScopeMapCoverage:
    def test_every_gcal_route_has_scope_map_entry(self):
        """Every registered /calendar/v3 route must appear in SCOPE_MAP (and no stale keys)."""
        from mock_gcal.api.app import app
        from mock_gcal.auth_scopes import GCAL_PREFIX, SCOPE_MAP

        registered = set()
        for route in app.routes:
            if isinstance(route, APIRoute) and route.path.startswith(GCAL_PREFIX):
                for method in route.methods:
                    if method not in ("HEAD", "OPTIONS"):
                        registered.add((method, route.path))

        assert registered, "no /calendar/v3 routes registered -- enumeration broken?"
        missing = registered - set(SCOPE_MAP)
        assert not missing, f"routes missing from SCOPE_MAP: {sorted(missing)}"
        stale = set(SCOPE_MAP) - registered
        assert not stale, f"SCOPE_MAP keys matching no registered route: {sorted(stale)}"

    def test_scope_lists_are_nonempty_calendar_scopes(self):
        from mock_gcal.auth_scopes import SCOPE_MAP

        for key, scopes in SCOPE_MAP.items():
            assert scopes, f"empty scope list for {key}"
            for scope in scopes:
                assert scope.startswith("calendar."), f"unexpected scope {scope!r} for {key}"

    def test_acl_endpoints_require_full_only(self):
        """Sharing/ACL endpoints (reads included) are gated behind calendar.full."""
        from mock_gcal.auth_scopes import SCOPE_MAP

        acl_keys = [k for k in SCOPE_MAP if "/acl" in k[1]]
        assert acl_keys, "no ACL routes in SCOPE_MAP?"
        for key in acl_keys:
            assert SCOPE_MAP[key] == ["calendar.full"], f"{key} must be calendar.full-only"


class TestAuthEnabled:
    def test_me_resolves_to_token_sub(self, auth_client):
        resp = auth_client.get(
            "/calendar/v3/users/me/profile", headers=_bearer(_token("calendar.readonly"))
        )
        assert resp.status_code == 200
        assert resp.json()["emailAddress"] == ALICE_EMAIL

    def test_valid_token_lists_events(self, auth_client):
        resp = auth_client.get(
            "/calendar/v3/calendars/primary/events",
            headers=_bearer(_token("calendar.readonly")),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["items"]

    def test_explicit_matching_user_id_allowed(self, auth_client):
        resp = auth_client.get(
            f"/calendar/v3/users/{ALICE}/settings",
            headers=_bearer(_token("calendar.readonly")),
        )
        assert resp.status_code == 200

    def test_events_readonly_reads_events_but_not_calendar_list(self, auth_client):
        # calendar.events.readonly may read events...
        listing = auth_client.get(
            "/calendar/v3/calendars/primary/events",
            headers=_bearer(_token("calendar.events.readonly")),
        )
        assert listing.status_code == 200
        # ...but it is events-only: calendarList reads are rejected.
        resp = auth_client.get(
            "/calendar/v3/users/me/calendarList",
            headers=_bearer(_token("calendar.events.readonly")),
        )
        assert resp.status_code == 403
        err = resp.json()["error"]
        assert err["status"] == "PERMISSION_DENIED"
        assert err["required_scopes"] == ["calendar.readonly", "calendar.events", "calendar.full"]
        assert "calendar.events.readonly" not in err["required_scopes"]

    def test_event_insert_without_write_scope_403(self, auth_client):
        resp = auth_client.post(
            "/calendar/v3/calendars/primary/events",
            json=_event_body(),
            headers=_bearer(_token("calendar.readonly")),
        )
        assert resp.status_code == 403
        err = resp.json()["error"]
        assert err["code"] == 403
        assert err["status"] == "PERMISSION_DENIED"
        assert err["required_scopes"] == ["calendar.events", "calendar.full"]
        assert err["token_scopes"] == ["calendar.readonly"]
        assert "hint" in err

    def test_event_insert_with_events_scope_200(self, auth_client):
        resp = auth_client.post(
            "/calendar/v3/calendars/primary/events",
            json=_event_body(),
            headers=_bearer(_token("calendar.events")),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"]
        assert data["summary"] == "Auth test event"

    def test_acl_read_requires_full_scope(self, auth_client):
        denied = auth_client.get(
            "/calendar/v3/calendars/primary/acl",
            headers=_bearer(_token("calendar.readonly")),
        )
        assert denied.status_code == 403
        err = denied.json()["error"]
        assert err["required_scopes"] == ["calendar.full"]
        assert err["token_scopes"] == ["calendar.readonly"]

        allowed = auth_client.get(
            "/calendar/v3/calendars/primary/acl",
            headers=_bearer(_token("calendar.full")),
        )
        assert allowed.status_code == 200

    def test_calendar_mutation_requires_full_scope(self, auth_client):
        resp = auth_client.patch(
            "/calendar/v3/calendars/primary",
            json={"summary": "Renamed"},
            headers=_bearer(_token("calendar.events")),
        )
        assert resp.status_code == 403
        assert resp.json()["error"]["required_scopes"] == ["calendar.full"]

    def test_freebusy_scopes(self, auth_client):
        # contract pin: freebusy -> calendar.readonly | calendar.full
        ok = auth_client.post(
            "/calendar/v3/freeBusy",
            json=_freebusy_body(),
            headers=_bearer(_token("calendar.readonly")),
        )
        assert ok.status_code == 200
        assert "primary" in ok.json()["calendars"]

        denied = auth_client.post(
            "/calendar/v3/freeBusy",
            json=_freebusy_body(),
            headers=_bearer(_token("calendar.events")),
        )
        assert denied.status_code == 403
        assert denied.json()["error"]["required_scopes"] == ["calendar.readonly", "calendar.full"]

    def test_mismatching_user_id_403_impersonation_body(self, auth_client):
        resp = auth_client.get(
            f"/calendar/v3/users/{OTHER_USER}/settings",
            headers=_bearer(_token("calendar.readonly", sub=ALICE)),
        )
        assert resp.status_code == 403
        # Exact contract body -- NOT the Google Calendar error envelope.
        assert resp.json() == {
            "error": {
                "code": 403,
                "status": "PERMISSION_DENIED",
                "message": "Cannot access another user's resources",
                "authenticated_user": ALICE,
                "requested_user": OTHER_USER,
            }
        }

    def test_impersonation_attempt_is_reported(self, auth_client, monkeypatch):
        from env_0_auth_client import reporting

        events = []

        def handler(request: httpx.Request) -> httpx.Response:
            events.append(json.loads(request.content))
            return httpx.Response(200, json={"status": "ok"})

        monkeypatch.setenv("AUTH_REPORT", "1")  # read at call time
        reporting.set_transport(httpx.MockTransport(handler))
        try:
            resp = auth_client.get(
                f"/calendar/v3/users/{OTHER_USER}/settings",
                headers=_bearer(_token("calendar.readonly", sub=ALICE)),
            )
            assert resp.status_code == 403
        finally:
            reporting.set_transport(None)

        attempts = [e for e in events if e["event_type"] == "impersonation_attempt"]
        assert attempts, f"no impersonation_attempt among events: {events}"
        event = attempts[0]
        assert event["user_id"] == ALICE
        assert event["details"]["authenticated_user"] == ALICE
        assert event["details"]["requested_user"] == OTHER_USER

    def test_expired_token_401_with_refresh_hint(self, auth_client):
        resp = auth_client.get(
            "/calendar/v3/users/me/calendarList",
            headers=_bearer(_token("calendar.readonly", expires_in=-60)),
        )
        assert resp.status_code == 401
        err = resp.json()["error"]
        assert err["code"] == 401
        assert err["status"] == "UNAUTHENTICATED"
        assert "expired at" in err["message"]
        assert "/oauth2/token" in err["hint"]
        assert "grant_type=refresh_token" in err["hint"]
        assert resp.headers["WWW-Authenticate"].startswith('Bearer error="invalid_token"')

    def test_no_token_401(self, auth_client):
        resp = auth_client.get("/calendar/v3/users/me/calendarList")
        assert resp.status_code == 401
        err = resp.json()["error"]
        assert err["code"] == 401
        assert err["status"] == "UNAUTHENTICATED"
        assert "WWW-Authenticate" in resp.headers

    def test_bad_signature_401(self, auth_client):
        other_private, _ = generate_test_keypair()
        forged = make_jwt(private_key=other_private, kid=KID, sub=ALICE, scope="calendar.full")
        resp = auth_client.get("/calendar/v3/users/me/calendarList", headers=_bearer(forged))
        assert resp.status_code == 401
        assert resp.json()["error"]["status"] == "UNAUTHENTICATED"

    def test_token_sub_unknown_user_404(self, auth_client):
        # Verified token whose sub has no gcal User row: 404 (Google
        # envelope), protecting handlers like get_profile from a 500.
        resp = auth_client.get(
            "/calendar/v3/users/me/profile",
            headers=_bearer(_token("calendar.readonly", sub="ghost")),
        )
        assert resp.status_code == 404
        assert "ghost" in resp.json()["error"]["message"]

    def test_actor_endpoint_uses_token_sub(self, auth_client):
        # Endpoints without a userId path param resolve the actor from the
        # token: the created event lands in user1's primary calendar.
        resp = auth_client.post(
            "/calendar/v3/calendars/primary/events",
            json=_event_body("Actor identity event"),
            headers=_bearer(_token("calendar.events", sub=ALICE)),
        )
        assert resp.status_code == 200
        event_id = resp.json()["id"]
        readback = auth_client.get(
            f"/calendar/v3/calendars/primary/events/{event_id}",
            headers=_bearer(_token("calendar.readonly", sub=ALICE)),
        )
        assert readback.status_code == 200

    def test_health_unauthenticated(self, auth_client):
        resp = auth_client.get("/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}

    def test_admin_state_unauthenticated(self, auth_client):
        resp = auth_client.get("/_admin/state")
        assert resp.status_code == 200
        assert "users" in resp.json()

    def test_admin_action_log_unauthenticated(self, auth_client):
        resp = auth_client.get("/_admin/action_log")
        assert resp.status_code == 200


class TestEmailClaimFallback:
    """Identity-alignment: a token whose ``sub`` is not a local user id is
    resolved via its ``email`` claim (case-insensitive); the resolved LOCAL id
    is the effective identity everywhere downstream (userId routes AND actor
    routes).
    """

    # env-0-auth-style id that does NOT exist in gcal's seeds.
    NONLOCAL_SUB = "user_001"

    def _fallback_token(self, scope: str = "calendar.readonly", email: str = ALICE_EMAIL) -> str:
        return _token(scope, sub=self.NONLOCAL_SUB, email=email)

    def test_nonlocal_sub_with_seeded_email_resolves_me(self, auth_client):
        resp = auth_client.get(
            "/calendar/v3/users/me/calendarList", headers=_bearer(self._fallback_token())
        )
        assert resp.status_code == 200
        assert resp.json()["items"]

    def test_email_match_is_case_insensitive(self, auth_client):
        resp = auth_client.get(
            "/calendar/v3/users/me/calendarList",
            headers=_bearer(self._fallback_token(email=ALICE_EMAIL.upper())),
        )
        assert resp.status_code == 200

    def test_actor_endpoint_resolves_via_email_claim(self, auth_client):
        # Routes without a userId path param (resolve_actor_user_id): the
        # event is created in the RESOLVED local user's primary calendar.
        resp = auth_client.post(
            "/calendar/v3/calendars/primary/events",
            json=_event_body("Email-fallback actor event"),
            headers=_bearer(self._fallback_token("calendar.events")),
        )
        assert resp.status_code == 200
        event_id = resp.json()["id"]
        # Readable back as user1 (the local identity the token resolved to).
        readback = auth_client.get(
            f"/calendar/v3/calendars/primary/events/{event_id}",
            headers=_bearer(_token("calendar.readonly", sub=ALICE)),
        )
        assert readback.status_code == 200

    def test_explicit_resolved_local_id_does_not_trip_guard(self, auth_client):
        resp = auth_client.get(
            f"/calendar/v3/users/{ALICE}/settings", headers=_bearer(self._fallback_token())
        )
        assert resp.status_code == 200

    def test_genuinely_different_user_still_403s(self, two_user_auth_client):
        resp = two_user_auth_client.get(
            f"/calendar/v3/users/{OTHER_USER}/settings",
            headers=_bearer(self._fallback_token()),
        )
        assert resp.status_code == 403
        err = resp.json()["error"]
        assert err["message"] == "Cannot access another user's resources"
        # The contract body names the RESOLVED local identity.
        assert err["authenticated_user"] == ALICE
        assert err["requested_user"] == OTHER_USER

    def test_unknown_sub_and_unknown_email_404_as_before(self, auth_client):
        resp = auth_client.get(
            "/calendar/v3/users/me/profile",
            headers=_bearer(_token("calendar.readonly", sub="ghost", email="ghost@nowhere.test")),
        )
        assert resp.status_code == 404
        assert "ghost" in resp.json()["error"]["message"]

    def test_local_sub_wins_over_email_claim(self, two_user_auth_client):
        # Resolution order pin: id == sub (a) beats the email claim (b) -- a
        # token for user2 carrying user1's email acts as user2.
        resp = two_user_auth_client.get(
            "/calendar/v3/users/me/settings",
            headers=_bearer(_token("calendar.readonly", sub=OTHER_USER, email=ALICE_EMAIL)),
        )
        assert resp.status_code == 200
        # Settings exist per-user; verify identity via the explicit path form.
        explicit = two_user_auth_client.get(
            f"/calendar/v3/users/{OTHER_USER}/settings",
            headers=_bearer(_token("calendar.readonly", sub=OTHER_USER, email=ALICE_EMAIL)),
        )
        assert explicit.status_code == 200


class TestWebUIExemption:
    """With AUTH_ENABLED=1, the human web UI stays usable WITHOUT a token.

    The web dashboard identifies users via the mock_gcal_user cookie (browser
    session), not Bearer tokens -- the real-world session-vs-API split. /mcp is
    likewise exempt (agent MCP clients are out of OAuth scope for v1). The API
    under /calendar/v3 still requires Bearer tokens. See
    mock_gcal/api/auth_middleware.py.
    """

    def test_calendar_root_no_token_200(self, auth_client):
        resp = auth_client.get("/")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]

    def test_calendar_root_with_query_params_no_token_200(self, auth_client):
        # Query strings don't change the path: still the exact-match "/" route.
        resp = auth_client.get("/", params={"week": "2026-06-08"})
        assert resp.status_code == 200

    def test_dev_routes_no_token_200(self, auth_client):
        resp = auth_client.get("/dev/api-explorer")
        assert resp.status_code == 200

    def test_mcp_not_gated_by_auth(self, auth_client):
        # MCP is not mounted in tests: a 404 (rather than 401) proves the
        # middleware exempts /mcp instead of demanding a Bearer token.
        resp = auth_client.get("/mcp")
        assert resp.status_code == 404

    def test_api_still_requires_token_while_web_is_open(self, auth_client):
        # The "/" exemption is EXACT-match, not a "/" prefix that would
        # swallow every path: the API must still 401 without a token.
        assert auth_client.get("/").status_code == 200
        resp = auth_client.get("/calendar/v3/users/me/calendarList")
        assert resp.status_code == 401
        assert resp.json()["error"]["status"] == "UNAUTHENTICATED"

    def test_exempt_prefixes_extend_contract_defaults(self):
        from env_0_auth_client.middleware import DEFAULT_EXEMPT_PREFIXES
        from mock_gcal.api.auth_middleware import GCAL_EXEMPT_PREFIXES

        for prefix in DEFAULT_EXEMPT_PREFIXES:
            assert prefix in GCAL_EXEMPT_PREFIXES
        for prefix in ("/static", "/mcp"):
            assert prefix in GCAL_EXEMPT_PREFIXES


class TestAuthDisabledRegression:
    """CRITICAL: with AUTH_ENABLED unset, behavior is byte-identical legacy.

    These tests use the standard ``client`` fixture from conftest (the module
    singleton, which was assembled with auth disabled) or ``two_user_client``
    where a second user is needed to observe header-based switching.
    """

    def test_singleton_has_no_auth_middleware(self, client):
        from mock_gcal.api.app import app

        assert not any(
            "Env_0AuthMiddleware" in m.cls.__name__ for m in app.user_middleware
        ), "Env_0AuthMiddleware must not be installed when AUTH_ENABLED is unset"

    def test_no_bearer_required_me_falls_back_to_first_user(self, client):
        resp = client.get("/calendar/v3/users/me/profile")
        assert resp.status_code == 200
        assert resp.json()["emailAddress"] == ALICE_EMAIL

    def test_header_resolution_by_id(self, two_user_client):
        resp = two_user_client.get(
            "/calendar/v3/users/me/profile", headers={"X-Env-0-Gcal-User": OTHER_USER}
        )
        assert resp.status_code == 200
        assert resp.json()["emailAddress"] == OTHER_EMAIL

    def test_header_resolution_by_email(self, two_user_client):
        resp = two_user_client.get(
            "/calendar/v3/users/me/profile", headers={"X-Env-0-Gcal-User": OTHER_EMAIL}
        )
        assert resp.status_code == 200
        assert resp.json()["emailAddress"] == OTHER_EMAIL

    def test_mock_gcal_user_header_also_resolves(self, two_user_client):
        # Legacy gcal quirk (unlike gmail): X-Mock-Gcal-User is a resolution
        # fallback after X-Env-0-Gcal-User.
        resp = two_user_client.get(
            "/calendar/v3/users/me/profile", headers={"X-Mock-Gcal-User": OTHER_USER}
        )
        assert resp.status_code == 200
        assert resp.json()["emailAddress"] == OTHER_EMAIL

    def test_explicit_unknown_user_404_gcal_envelope(self, client):
        resp = client.get("/calendar/v3/users/no_such_user/settings")
        assert resp.status_code == 404
        err = resp.json()["error"]
        # Legacy Google envelope (has 'errors' list), not the auth contract body.
        assert err["status"] == "NOT_FOUND"
        assert err["errors"][0]["reason"] == "notFound"

    def test_apply_auth_returns_false_when_disabled(self, monkeypatch):
        app_module = importlib.import_module("mock_gcal.api.app")

        monkeypatch.delenv("AUTH_ENABLED", raising=False)
        assert app_module._apply_auth(FastAPI()) is False

    def test_apply_auth_raises_runtime_error_without_package(self, monkeypatch):
        app_module = importlib.import_module("mock_gcal.api.app")

        monkeypatch.setenv("AUTH_ENABLED", "1")
        # None in sys.modules makes `import env_0_auth_client` raise ImportError.
        monkeypatch.setitem(sys.modules, "env_0_auth_client", None)
        with pytest.raises(RuntimeError, match="auth-client is not installed"):
            app_module._apply_auth(FastAPI())


class TestNoHeaderBypassWhenAuthEnabled:
    """X-Env-0-Gcal-User / X-Mock-Gcal-User must be IGNORED under auth.

    Legacy identity headers must never override (or substitute for) the
    token's sub -- on userId routes AND on actor-resolved routes.
    """

    def test_header_cannot_switch_me_to_another_user(self, two_user_auth_client):
        resp = two_user_auth_client.get(
            "/calendar/v3/users/me/profile",
            headers={
                **_bearer(_token("calendar.readonly", sub=ALICE)),
                "X-Env-0-Gcal-User": OTHER_USER,  # exists in this DB -- still ignored
            },
        )
        assert resp.status_code == 200
        assert resp.json()["emailAddress"] == ALICE_EMAIL

    def test_header_by_email_is_ignored_too(self, two_user_auth_client):
        resp = two_user_auth_client.get(
            "/calendar/v3/users/me/profile",
            headers={
                **_bearer(_token("calendar.readonly", sub=ALICE)),
                "X-Env-0-Gcal-User": OTHER_EMAIL,
            },
        )
        assert resp.status_code == 200
        assert resp.json()["emailAddress"] == ALICE_EMAIL

    def test_mock_gcal_user_header_is_ignored_too(self, two_user_auth_client):
        resp = two_user_auth_client.get(
            "/calendar/v3/users/me/profile",
            headers={
                **_bearer(_token("calendar.readonly", sub=ALICE)),
                "X-Mock-Gcal-User": OTHER_USER,
            },
        )
        assert resp.status_code == 200
        assert resp.json()["emailAddress"] == ALICE_EMAIL

    def test_header_cannot_switch_actor_endpoints(self, two_user_auth_client):
        # Actor-resolved endpoint (no userId in path): the event must land in
        # user1's primary calendar despite the header naming user2.
        resp = two_user_auth_client.post(
            "/calendar/v3/calendars/primary/events",
            json=_event_body("Header bypass attempt"),
            headers={
                **_bearer(_token("calendar.events", sub=ALICE)),
                "X-Env-0-Gcal-User": OTHER_USER,
            },
        )
        assert resp.status_code == 200
        event_id = resp.json()["id"]
        # Visible in user1's primary calendar...
        as_user1 = two_user_auth_client.get(
            f"/calendar/v3/calendars/primary/events/{event_id}",
            headers=_bearer(_token("calendar.readonly", sub=ALICE)),
        )
        assert as_user1.status_code == 200
        # ...and NOT in user2's.
        as_user2 = two_user_auth_client.get(
            f"/calendar/v3/calendars/primary/events/{event_id}",
            headers=_bearer(_token("calendar.readonly", sub=OTHER_USER)),
        )
        assert as_user2.status_code == 404

    def test_header_without_token_is_still_401(self, two_user_auth_client):
        resp = two_user_auth_client.get(
            "/calendar/v3/users/me/profile",
            headers={"X-Env-0-Gcal-User": ALICE},
        )
        assert resp.status_code == 401
        assert resp.json()["error"]["status"] == "UNAUTHENTICATED"

    def test_header_cannot_bless_impersonation(self, two_user_auth_client):
        # Explicit foreign userId + matching header still 403s.
        resp = two_user_auth_client.get(
            f"/calendar/v3/users/{OTHER_USER}/settings",
            headers={
                **_bearer(_token("calendar.readonly", sub=ALICE)),
                "X-Env-0-Gcal-User": OTHER_USER,
            },
        )
        assert resp.status_code == 403
        assert resp.json()["error"]["message"] == "Cannot access another user's resources"
