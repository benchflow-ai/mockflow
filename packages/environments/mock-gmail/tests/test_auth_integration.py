"""Integration tests for the auth retrofit (AUTH_ENABLED).

Fully offline: JWKS is injected statically via env_0_auth_client.testing, and
event reporting is disabled (AUTH_REPORT=0) except where a MockTransport
captures events explicitly.

The FastAPI app in mock_gmail.api.app is a module-level singleton and
AUTH_ENABLED is read at import time, so the ``auth_app`` fixture builds a
FRESH instance via importlib.reload (with auth disabled, so the module-level
``_apply_auth(app)`` is a no-op) and then applies the middleware explicitly
with the static JWKS. Teardown reloads once more so every other test module
keeps using a pristine, auth-disabled singleton.
"""

import base64
import importlib
import json
import sys
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from fastapi import FastAPI
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from env_0_auth_client.testing import generate_test_keypair, jwks_for, make_jwt
from mock_gmail.models import init_db, reset_engine

KID = "test-key-001"
PRIVATE_KEY, PUBLIC_KEY = generate_test_keypair()
JWKS = jwks_for(PUBLIC_KEY, kid=KID)

# Actual identities seeded by scenario "default", seed 42 (see
# mock_gmail/seed/generator.py): the auth seeds must match THESE ids.
ALICE = "user1"
ALICE_EMAIL = "alex@nexusai.com"
# Any id other than the token sub; the impersonation check fires before the
# DB lookup, so this user does not need to exist in the seeded DB.
OTHER_USER = "user2"


def _token(scope: str = "", sub: str = ALICE, **kwargs) -> str:
    return make_jwt(private_key=PRIVATE_KEY, kid=KID, sub=sub, scope=scope, **kwargs)


def _bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _raw(subject: str = "Auth test", body: str = "hello") -> str:
    msg = f"From: {ALICE_EMAIL}\r\nTo: colleague@example.com\r\nSubject: {subject}\r\n\r\n{body}"
    return base64.urlsafe_b64encode(msg.encode()).decode().rstrip("=")


@pytest.fixture
def auth_app(monkeypatch):
    """Fresh app instance with Env_0AuthMiddleware and static (offline) JWKS."""
    for var in ("AUTH_ENABLED", "AUTH_INTROSPECT", "AUTH_ISSUER", "AUTH_URL"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("AUTH_REPORT", "0")

    import mock_gmail.api.app as app_module

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


class TestScopeMapCoverage:
    def test_every_gmail_route_has_scope_map_entry(self):
        """Every registered /gmail/v1 route must appear in SCOPE_MAP (and no stale keys)."""
        from mock_gmail.api.app import app
        from mock_gmail.auth_scopes import GMAIL_PREFIX, SCOPE_MAP

        registered = set()
        for route in app.routes:
            if isinstance(route, APIRoute) and route.path.startswith(GMAIL_PREFIX):
                for method in route.methods:
                    if method not in ("HEAD", "OPTIONS"):
                        registered.add((method, route.path))

        assert registered, "no /gmail/v1 routes registered -- enumeration broken?"
        missing = registered - set(SCOPE_MAP)
        assert not missing, f"routes missing from SCOPE_MAP: {sorted(missing)}"
        stale = set(SCOPE_MAP) - registered
        assert not stale, f"SCOPE_MAP keys matching no registered route: {sorted(stale)}"

    def test_scope_lists_are_nonempty_gmail_scopes(self):
        from mock_gmail.auth_scopes import SCOPE_MAP

        for key, scopes in SCOPE_MAP.items():
            assert scopes, f"empty scope list for {key}"
            for scope in scopes:
                assert scope.startswith("gmail."), f"unexpected scope {scope!r} for {key}"


class TestAuthEnabled:
    def test_me_resolves_to_token_sub(self, auth_client):
        resp = auth_client.get(
            "/gmail/v1/users/me/profile", headers=_bearer(_token("gmail.readonly"))
        )
        assert resp.status_code == 200
        assert resp.json()["emailAddress"] == ALICE_EMAIL

    def test_valid_token_lists_messages(self, auth_client):
        resp = auth_client.get(
            "/gmail/v1/users/me/messages", headers=_bearer(_token("gmail.readonly"))
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["resultSizeEstimate"] > 0
        assert data["messages"]

    def test_explicit_matching_user_id_allowed(self, auth_client):
        resp = auth_client.get(
            f"/gmail/v1/users/{ALICE}/messages", headers=_bearer(_token("gmail.readonly"))
        )
        assert resp.status_code == 200

    def test_send_without_send_scope_403(self, auth_client):
        resp = auth_client.post(
            "/gmail/v1/users/me/messages/send",
            json={"raw": _raw()},
            headers=_bearer(_token("gmail.readonly")),
        )
        assert resp.status_code == 403
        err = resp.json()["error"]
        assert err["code"] == 403
        assert err["status"] == "PERMISSION_DENIED"
        assert err["required_scopes"] == ["gmail.send", "gmail.full"]
        assert err["token_scopes"] == ["gmail.readonly"]
        assert "hint" in err

    def test_send_with_send_scope_200(self, auth_client):
        resp = auth_client.post(
            "/gmail/v1/users/me/messages/send",
            json={"raw": _raw()},
            headers=_bearer(_token("gmail.send")),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"]
        assert "SENT" in data["labelIds"]

    def test_metadata_scope_cannot_read_message_body(self, auth_client):
        # gmail.metadata may list messages...
        listing = auth_client.get(
            "/gmail/v1/users/me/messages", headers=_bearer(_token("gmail.metadata"))
        )
        assert listing.status_code == 200
        msg_id = listing.json()["messages"][0]["id"]
        # ...but messages.get can expose full bodies, so metadata is rejected.
        resp = auth_client.get(
            f"/gmail/v1/users/me/messages/{msg_id}",
            headers=_bearer(_token("gmail.metadata")),
        )
        assert resp.status_code == 403
        err = resp.json()["error"]
        assert err["status"] == "PERMISSION_DENIED"
        assert "gmail.readonly" in err["required_scopes"]
        assert "gmail.metadata" not in err["required_scopes"]

    def test_mismatching_user_id_403_impersonation_body(self, auth_client):
        resp = auth_client.get(
            f"/gmail/v1/users/{OTHER_USER}/messages",
            headers=_bearer(_token("gmail.readonly", sub=ALICE)),
        )
        assert resp.status_code == 403
        # Exact contract body -- NOT the Gmail error envelope.
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
                f"/gmail/v1/users/{OTHER_USER}/messages",
                headers=_bearer(_token("gmail.readonly", sub=ALICE)),
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
            "/gmail/v1/users/me/messages",
            headers=_bearer(_token("gmail.readonly", expires_in=-60)),
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
        resp = auth_client.get("/gmail/v1/users/me/messages")
        assert resp.status_code == 401
        err = resp.json()["error"]
        assert err["code"] == 401
        assert err["status"] == "UNAUTHENTICATED"
        assert "WWW-Authenticate" in resp.headers

    def test_bad_signature_401(self, auth_client):
        other_private, _ = generate_test_keypair()
        forged = make_jwt(private_key=other_private, kid=KID, sub=ALICE, scope="gmail.full")
        resp = auth_client.get("/gmail/v1/users/me/messages", headers=_bearer(forged))
        assert resp.status_code == 401
        assert resp.json()["error"]["status"] == "UNAUTHENTICATED"

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
    is the effective identity everywhere downstream.
    """

    # env-0-auth-style id that does NOT exist in gmail's seeds.
    NONLOCAL_SUB = "user_001"

    def _fallback_token(self, scope: str = "gmail.readonly", email: str = ALICE_EMAIL) -> str:
        return _token(scope, sub=self.NONLOCAL_SUB, email=email)

    def test_nonlocal_sub_with_seeded_email_resolves_me(self, auth_client):
        resp = auth_client.get(
            "/gmail/v1/users/me/profile", headers=_bearer(self._fallback_token())
        )
        assert resp.status_code == 200
        assert resp.json()["emailAddress"] == ALICE_EMAIL

    def test_nonlocal_sub_lists_messages_end_to_end(self, auth_client):
        resp = auth_client.get(
            "/gmail/v1/users/me/messages", headers=_bearer(self._fallback_token())
        )
        assert resp.status_code == 200
        assert resp.json()["resultSizeEstimate"] > 0

    def test_email_match_is_case_insensitive(self, auth_client):
        resp = auth_client.get(
            "/gmail/v1/users/me/profile",
            headers=_bearer(self._fallback_token(email=ALICE_EMAIL.upper())),
        )
        assert resp.status_code == 200
        assert resp.json()["emailAddress"] == ALICE_EMAIL

    def test_explicit_resolved_local_id_does_not_trip_guard(self, auth_client):
        # Naming the RESOLVED local id explicitly is the token's own identity.
        resp = auth_client.get(
            f"/gmail/v1/users/{ALICE}/messages", headers=_bearer(self._fallback_token())
        )
        assert resp.status_code == 200

    def test_genuinely_different_user_still_403s(self, auth_client):
        resp = auth_client.get(
            f"/gmail/v1/users/{OTHER_USER}/messages",
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
            "/gmail/v1/users/me/profile",
            headers=_bearer(_token("gmail.readonly", sub="ghost", email="ghost@nowhere.test")),
        )
        assert resp.status_code == 404

    def test_local_sub_wins_over_email_claim(self, multi_client):
        # Resolution order pin: id == sub (a) is checked BEFORE the email
        # claim (b) -- a token for user_101 carrying alice's work email acts
        # as user_101, not user1.
        resp = multi_client.get(
            "/gmail/v1/users/me/profile",
            headers=_bearer(_token("gmail.readonly", sub=PERSONAL, email=ALICE_EMAIL)),
        )
        assert resp.status_code == 200
        assert resp.json()["emailAddress"] == PERSONAL_EMAIL


class TestAuthDisabledRegression:
    """CRITICAL: with AUTH_ENABLED unset, behavior is byte-identical legacy.

    These tests use the standard ``client`` fixture from conftest (the module
    singleton, which was assembled with auth disabled).
    """

    def test_singleton_has_no_auth_middleware(self, client):
        from mock_gmail.api.app import app

        assert not any(
            "Env_0AuthMiddleware" in m.cls.__name__ for m in app.user_middleware
        ), "Env_0AuthMiddleware must not be installed when AUTH_ENABLED is unset"

    def test_no_bearer_required_me_falls_back_to_first_user(self, client):
        resp = client.get("/gmail/v1/users/me/profile")
        assert resp.status_code == 200
        assert resp.json()["emailAddress"] == ALICE_EMAIL

    def test_header_resolution_by_id(self, client):
        # NOTE: the deps layer reads the X-Env-0-Gmail-User header (FastAPI
        # parameter x_env_0_gmail_user); X-Mock-Gmail-User is only used by the
        # action-log middleware and never affects resolution.
        resp = client.get(
            "/gmail/v1/users/me/profile", headers={"X-Env-0-Gmail-User": ALICE}
        )
        assert resp.status_code == 200
        assert resp.json()["emailAddress"] == ALICE_EMAIL

    def test_header_resolution_by_email(self, client):
        resp = client.get(
            "/gmail/v1/users/me/profile", headers={"X-Env-0-Gmail-User": ALICE_EMAIL}
        )
        assert resp.status_code == 200
        assert resp.json()["emailAddress"] == ALICE_EMAIL

    def test_mock_gmail_user_header_does_not_resolve(self, client):
        # Legacy quirk preserved: X-Mock-Gmail-User does NOT participate in
        # user resolution ('me' still falls back to the first user).
        resp = client.get(
            "/gmail/v1/users/me/profile", headers={"X-Mock-Gmail-User": "no-such-user"}
        )
        assert resp.status_code == 200
        assert resp.json()["emailAddress"] == ALICE_EMAIL

    def test_explicit_unknown_user_404_gmail_envelope(self, client):
        resp = client.get("/gmail/v1/users/no_such_user/messages")
        assert resp.status_code == 404
        err = resp.json()["error"]
        # Legacy Gmail envelope (has 'errors' list), not the auth contract body.
        assert err["status"] == "NOT_FOUND"
        assert err["errors"][0]["reason"] == "notFound"

    def test_apply_auth_returns_false_when_disabled(self, monkeypatch):
        import mock_gmail.api.app as app_module

        monkeypatch.delenv("AUTH_ENABLED", raising=False)
        assert app_module._apply_auth(FastAPI()) is False

    def test_apply_auth_raises_runtime_error_without_package(self, monkeypatch):
        import mock_gmail.api.app as app_module

        monkeypatch.setenv("AUTH_ENABLED", "1")
        # None in sys.modules makes `import env_0_auth_client` raise ImportError.
        monkeypatch.setitem(sys.modules, "env_0_auth_client", None)
        with pytest.raises(RuntimeError, match="auth-client is not installed"):
            app_module._apply_auth(FastAPI())


# --- Multi-account fixtures (gmail scenario `multi_account`, mirrors auth) ---

PERSONAL = "user_101"
PERSONAL_EMAIL = "alex.personal@gmail.local"


@pytest.fixture
def multi_seeded_db(db_path):
    """Temp DB seeded with the `multi_account` scenario (user1 + user_101)."""
    from mock_gmail.seed.generator import seed_database

    reset_engine()
    seed_database(scenario="multi_account", seed=42, db_path=db_path)
    return db_path


@pytest.fixture
def multi_client(auth_app, multi_seeded_db):
    """Auth-enabled TestClient against the multi-account database."""
    reset_engine()
    init_db(multi_seeded_db)
    with TestClient(auth_app) as c:
        yield c
    reset_engine()


class TestWebUIExemption:
    """With AUTH_ENABLED=1, the human web UI is Bearer-token-EXEMPT but
    session-gated (W7).

    The mailbox routes (``/``, ``/thread/*``) identify users via the
    ``mock_gmail_user`` cookie (browser session), not Bearer tokens -- the
    real-world session-vs-API split. Under auth, that session must be
    established via SSO first (see TestWebSessionSSO); with a valid session
    cookie these routes serve HTML and never demand a token. POST mutations,
    ``/dev/*`` tooling and ``/mcp`` are not GET-gated. The API under
    ``/gmail/v1`` still requires Bearer tokens. See
    mock_gmail/api/auth_middleware.py, mock_gmail/web/sso.py and API_NOTES.md.
    """

    def _first_id(self, model):
        from mock_gmail.models import get_session_factory

        db = get_session_factory()()
        try:
            row = db.query(model).first()
            assert row is not None
            return row.id
        finally:
            db.close()

    def _session(self, client):
        """Attach an established gmail web session (cookie -> seeded user)."""
        client.cookies.set("mock_gmail_user", ALICE)
        return client

    def test_inbox_root_with_session_200(self, auth_client):
        resp = self._session(auth_client).get("/")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]

    def test_inbox_with_query_params_with_session_200(self, auth_client):
        # Query strings don't change the path: still the exact-match "/" route.
        resp = self._session(auth_client).get("/", params={"label": "INBOX", "q": "meeting"})
        assert resp.status_code == 200

    def test_thread_page_with_session_200(self, auth_client):
        from mock_gmail.models import Thread

        resp = self._session(auth_client).get(f"/thread/{self._first_id(Thread)}")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]

    def test_star_no_token_303(self, auth_client):
        from mock_gmail.models import Message

        resp = auth_client.post(
            f"/star/{self._first_id(Message)}", follow_redirects=False
        )
        assert resp.status_code == 303

    def test_mark_read_no_token_303(self, auth_client):
        from mock_gmail.models import Message

        resp = auth_client.post(
            f"/mark-read/{self._first_id(Message)}", follow_redirects=False
        )
        assert resp.status_code == 303

    def test_trash_no_token_303(self, auth_client):
        from mock_gmail.models import Message

        resp = auth_client.post(
            f"/trash/{self._first_id(Message)}", follow_redirects=False
        )
        assert resp.status_code == 303

    def test_dev_routes_no_token_200(self, auth_client):
        resp = auth_client.get("/dev/api-explorer")
        assert resp.status_code == 200

    def test_mcp_not_gated_by_auth(self, auth_client):
        # MCP is not mounted in tests: a 404 (rather than 401) proves the
        # middleware exempts /mcp instead of demanding a Bearer token.
        resp = auth_client.get("/mcp")
        assert resp.status_code == 404

    def test_api_still_requires_token_while_web_is_session_gated(self, auth_client):
        # The "/" exemption is EXACT-match, not a "/" prefix that would
        # swallow every path: with a web session "/" serves HTML, but the API
        # must still 401 without a Bearer token.
        self._session(auth_client)
        assert auth_client.get("/").status_code == 200
        resp = auth_client.get("/gmail/v1/users/me/messages")
        assert resp.status_code == 401
        assert resp.json()["error"]["status"] == "UNAUTHENTICATED"

    def test_exempt_prefixes_extend_contract_defaults(self):
        from env_0_auth_client.middleware import DEFAULT_EXEMPT_PREFIXES
        from mock_gmail.api.auth_middleware import GMAIL_EXEMPT_PREFIXES

        for prefix in DEFAULT_EXEMPT_PREFIXES:
            assert prefix in GMAIL_EXEMPT_PREFIXES
        for prefix in ("/thread", "/compose", "/star", "/trash", "/mark-read", "/static", "/mcp"):
            assert prefix in GMAIL_EXEMPT_PREFIXES


def _web_sso_assertion(sub: str = ALICE, email: str = ALICE_EMAIL,
                       expires_in: int = 120, purpose: str = "web_sso") -> str:
    """Mint a env-0-auth-shaped web-SSO identity assertion (test-signed)."""
    extra = {"purpose": purpose} if purpose is not None else {}
    return make_jwt(private_key=PRIVATE_KEY, kid=KID, sub=sub, email=email,
                    expires_in=expires_in, extra_claims=extra)


class TestWebSessionSSO:
    """W7: under auth, sessionless browsers on the mailbox web UI are bounced
    into auth's login flow, and /web/auth/callback turns auth's signed
    identity assertion into an established gmail web session.

    Offline: the auth_app fixture wires the static test JWKS into sso (via
    _apply_auth's jwks_static), so the callback verifies assertions without HTTP.
    """

    LOGIN_PREFIX = "http://localhost:9000/web/login"

    def _login_next(self, location: str) -> str:
        """Pull the callback URL out of the login redirect's `next` param."""
        assert location.startswith(self.LOGIN_PREFIX + "?"), location
        return parse_qs(urlparse(location).query)["next"][0]

    def _callback_next(self, location: str) -> str:
        """Pull the original-path `next` out of the callback URL."""
        return parse_qs(urlparse(self._login_next(location)).query)["next"][0]

    # --- middleware: sessionless GET -> 302 to auth login ---

    def test_sessionless_inbox_redirects_to_login(self, auth_client):
        resp = auth_client.get("/", follow_redirects=False)
        assert resp.status_code == 302
        callback = self._login_next(resp.headers["location"])
        assert "/web/auth/callback" in callback
        assert self._callback_next(resp.headers["location"]) == "/"

    def test_sessionless_thread_redirects_to_login(self, auth_client):
        from mock_gmail.models import Thread

        tid = self._first_thread_id()
        resp = auth_client.get(f"/thread/{tid}", follow_redirects=False)
        assert resp.status_code == 302
        assert self._callback_next(resp.headers["location"]) == f"/thread/{tid}"

    def test_redirect_preserves_original_query_string(self, auth_client):
        resp = auth_client.get("/", params={"label": "SENT"}, follow_redirects=False)
        assert resp.status_code == 302
        assert self._callback_next(resp.headers["location"]) == "/?label=SENT"

    def _first_thread_id(self):
        from mock_gmail.models import Thread, get_session_factory

        db = get_session_factory()()
        try:
            return db.query(Thread).first().id
        finally:
            db.close()

    # --- callback: assertion -> established session ---

    def test_callback_valid_assertion_sets_session_cookie(self, auth_client):
        resp = auth_client.get(
            "/web/auth/callback",
            params={"next": "/", "env_0_identity": _web_sso_assertion()},
            follow_redirects=False,
        )
        assert resp.status_code == 302
        assert resp.headers["location"] == "/"
        assert resp.cookies.get("mock_gmail_user") == ALICE

    def test_callback_then_inbox_serves_html(self, auth_client):
        # Establish the session via the callback, then the jar carries the
        # cookie so the inbox renders (no further redirect).
        auth_client.get(
            "/web/auth/callback",
            params={"next": "/", "env_0_identity": _web_sso_assertion()},
            follow_redirects=False,
        )
        resp = auth_client.get("/", follow_redirects=False)
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]

    def test_callback_resolves_by_email_when_sub_unknown(self, auth_client):
        # sub not a local id, but the email claim matches a seeded mailbox.
        resp = auth_client.get(
            "/web/auth/callback",
            params={"next": "/",
                    "env_0_identity": _web_sso_assertion(sub="user_xyz", email=ALICE_EMAIL)},
            follow_redirects=False,
        )
        assert resp.status_code == 302
        assert resp.cookies.get("mock_gmail_user") == ALICE

    def test_callback_unknown_identity_403(self, auth_client):
        resp = auth_client.get(
            "/web/auth/callback",
            params={"next": "/",
                    "env_0_identity": _web_sso_assertion(sub="ghost", email="ghost@nowhere.test")},
            follow_redirects=False,
        )
        assert resp.status_code == 403

    # --- callback: bad assertions restart the login dance ---

    def test_callback_missing_assertion_bounces_to_login(self, auth_client):
        resp = auth_client.get("/web/auth/callback", params={"next": "/"},
                               follow_redirects=False)
        assert resp.status_code == 302
        assert resp.headers["location"].startswith(self.LOGIN_PREFIX)
        assert "mock_gmail_user" not in resp.cookies

    def test_callback_garbage_assertion_bounces_to_login(self, auth_client):
        resp = auth_client.get(
            "/web/auth/callback",
            params={"next": "/", "env_0_identity": "not-a-jwt"},
            follow_redirects=False,
        )
        assert resp.status_code == 302
        assert resp.headers["location"].startswith(self.LOGIN_PREFIX)

    def test_callback_expired_assertion_bounces_to_login(self, auth_client):
        resp = auth_client.get(
            "/web/auth/callback",
            params={"next": "/", "env_0_identity": _web_sso_assertion(expires_in=-60)},
            follow_redirects=False,
        )
        assert resp.status_code == 302
        assert resp.headers["location"].startswith(self.LOGIN_PREFIX)

    def test_callback_assertion_without_purpose_rejected(self, auth_client):
        # A plain access-token-shaped JWT (no purpose=web_sso) must not pass.
        resp = auth_client.get(
            "/web/auth/callback",
            params={"next": "/", "env_0_identity": _web_sso_assertion(purpose=None)},
            follow_redirects=False,
        )
        assert resp.status_code == 302
        assert resp.headers["location"].startswith(self.LOGIN_PREFIX)

    def test_callback_assertion_bad_signature_bounces(self, auth_client):
        other_priv, _ = generate_test_keypair()
        forged = make_jwt(private_key=other_priv, kid=KID, sub=ALICE,
                          email=ALICE_EMAIL, extra_claims={"purpose": "web_sso"})
        resp = auth_client.get(
            "/web/auth/callback",
            params={"next": "/", "env_0_identity": forged},
            follow_redirects=False,
        )
        assert resp.status_code == 302
        assert resp.headers["location"].startswith(self.LOGIN_PREFIX)

    def test_callback_clamps_open_redirect(self, auth_client):
        # An external `next` is clamped to "/" even with a valid assertion.
        resp = auth_client.get(
            "/web/auth/callback",
            params={"next": "http://evil.test/steal", "env_0_identity": _web_sso_assertion()},
            follow_redirects=False,
        )
        assert resp.status_code == 302
        assert resp.headers["location"] == "/"
        assert resp.cookies.get("mock_gmail_user") == ALICE

    # --- regression: dev tooling & POST routes are NOT session-gated ---

    def test_dev_routes_not_session_gated(self, auth_client):
        assert auth_client.get("/dev/api-explorer", follow_redirects=False).status_code == 200

    def test_callback_path_not_session_gated(self, auth_client):
        # The callback itself must never bounce (it has no session yet) -- a
        # missing assertion 302s to login, not a gate loop on /web/auth/callback.
        resp = auth_client.get("/web/auth/callback", follow_redirects=False)
        assert resp.status_code == 302
        assert resp.headers["location"].startswith(self.LOGIN_PREFIX)


class TestWebSSOAuthDisabledRegression:
    """With AUTH_ENABLED unset, the web UI is the legacy open dashboard:
    no session gate, no SSO redirect, no /web/auth/callback verification path."""

    def test_inbox_open_without_session(self, client):
        resp = client.get("/", follow_redirects=False)
        assert resp.status_code == 200

    def test_no_web_session_middleware_installed(self, client):
        from mock_gmail.api.app import app

        assert not any(
            "GmailWebSessionMiddleware" in m.cls.__name__ for m in app.user_middleware
        ), "web-session middleware must be absent when auth is disabled"


class TestMultiAccountIdentity:
    """Two personas, two tokens: user1 (work) and user_101 (personal).

    Token isolation per the contract: a token's sub is the ONLY identity it
    can act as -- explicit userIds for anyone else 403, `me` follows the token.
    """

    def test_me_resolves_per_token(self, multi_client):
        work = multi_client.get(
            "/gmail/v1/users/me/profile",
            headers=_bearer(_token("gmail.readonly", sub=ALICE)),
        )
        personal = multi_client.get(
            "/gmail/v1/users/me/profile",
            headers=_bearer(_token("gmail.readonly", sub=PERSONAL)),
        )
        assert work.status_code == personal.status_code == 200
        assert work.json()["emailAddress"] == ALICE_EMAIL
        assert personal.json()["emailAddress"] == PERSONAL_EMAIL

    def test_work_token_cannot_read_personal_messages(self, multi_client):
        resp = multi_client.get(
            f"/gmail/v1/users/{PERSONAL}/messages",
            headers=_bearer(_token("gmail.readonly", sub=ALICE)),
        )
        assert resp.status_code == 403
        assert resp.json() == {
            "error": {
                "code": 403,
                "status": "PERMISSION_DENIED",
                "message": "Cannot access another user's resources",
                "authenticated_user": ALICE,
                "requested_user": PERSONAL,
            }
        }

    def test_personal_token_reads_personal_messages(self, multi_client):
        token = _token("gmail.readonly", sub=PERSONAL)
        resp = multi_client.get(
            f"/gmail/v1/users/{PERSONAL}/messages", headers=_bearer(token)
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["resultSizeEstimate"] >= 4  # 3 inbox + 1 sent seeded
        msg_id = data["messages"][0]["id"]
        msg = multi_client.get(
            f"/gmail/v1/users/{PERSONAL}/messages/{msg_id}", headers=_bearer(token)
        )
        assert msg.status_code == 200

    def test_personal_token_cannot_read_work_account(self, multi_client):
        resp = multi_client.get(
            f"/gmail/v1/users/{ALICE}/messages",
            headers=_bearer(_token("gmail.readonly", sub=PERSONAL)),
        )
        assert resp.status_code == 403
        err = resp.json()["error"]
        assert err["authenticated_user"] == PERSONAL
        assert err["requested_user"] == ALICE

    def test_message_ids_do_not_leak_across_accounts(self, multi_client):
        # Fetch a WORK message id, then try to read it as the PERSONAL user
        # via `me`: ownership filtering must 404 (id not in that mailbox).
        work_token = _token("gmail.readonly", sub=ALICE)
        listing = multi_client.get(
            "/gmail/v1/users/me/messages", headers=_bearer(work_token)
        )
        work_msg_id = listing.json()["messages"][0]["id"]
        resp = multi_client.get(
            f"/gmail/v1/users/me/messages/{work_msg_id}",
            headers=_bearer(_token("gmail.readonly", sub=PERSONAL)),
        )
        assert resp.status_code == 404

    def test_seed_creates_personal_persona(self, multi_client):
        state = multi_client.get("/_admin/state").json()
        assert PERSONAL in state["users"], f"user_101 missing: {list(state['users'])}"


class TestNoHeaderBypassWhenAuthEnabled:
    """X-Env-0-Gmail-User (and X-Mock-Gmail-User) must be IGNORED under auth.

    Offline regression for the live cross-service check: legacy identity
    headers must never override (or substitute for) the token's sub.
    """

    def test_header_cannot_switch_me_to_another_user(self, multi_client):
        resp = multi_client.get(
            "/gmail/v1/users/me/profile",
            headers={
                **_bearer(_token("gmail.readonly", sub=ALICE)),
                "X-Env-0-Gmail-User": PERSONAL,  # exists in this DB -- still ignored
            },
        )
        assert resp.status_code == 200
        assert resp.json()["emailAddress"] == ALICE_EMAIL

    def test_header_by_email_is_ignored_too(self, multi_client):
        resp = multi_client.get(
            "/gmail/v1/users/me/profile",
            headers={
                **_bearer(_token("gmail.readonly", sub=ALICE)),
                "X-Env-0-Gmail-User": PERSONAL_EMAIL,
            },
        )
        assert resp.status_code == 200
        assert resp.json()["emailAddress"] == ALICE_EMAIL

    def test_mock_gmail_user_header_is_ignored_too(self, multi_client):
        resp = multi_client.get(
            "/gmail/v1/users/me/messages",
            headers={
                **_bearer(_token("gmail.readonly", sub=PERSONAL)),
                "X-Mock-Gmail-User": ALICE,
            },
        )
        assert resp.status_code == 200
        # All returned messages belong to the personal mailbox (4 seeded).
        assert resp.json()["resultSizeEstimate"] == 4

    def test_header_without_token_is_still_401(self, multi_client):
        resp = multi_client.get(
            "/gmail/v1/users/me/profile",
            headers={"X-Env-0-Gmail-User": ALICE},
        )
        assert resp.status_code == 401
        assert resp.json()["error"]["status"] == "UNAUTHENTICATED"

    def test_header_cannot_bless_impersonation(self, multi_client):
        # Explicit foreign userId + matching header still 403s.
        resp = multi_client.get(
            f"/gmail/v1/users/{PERSONAL}/messages",
            headers={
                **_bearer(_token("gmail.readonly", sub=ALICE)),
                "X-Env-0-Gmail-User": PERSONAL,
            },
        )
        assert resp.status_code == 403
        assert resp.json()["error"]["message"] == "Cannot access another user's resources"
