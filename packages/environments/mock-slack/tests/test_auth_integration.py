"""Integration tests for the auth retrofit (AUTH_ENABLED).

Fully offline: JWKS is injected statically via env_0_auth_client.testing, and
event reporting is disabled (AUTH_REPORT=0) except where a MockTransport
captures events explicitly.

The FastAPI app in mock_slack.api.app is a module-level singleton and
AUTH_ENABLED is read at import time, so the ``auth_app`` fixture builds a
FRESH instance via importlib.reload (with auth disabled, so the module-level
``_apply_auth(app)`` is a no-op) and then applies the middleware explicitly
with the static JWKS. Teardown reloads once more so every other test module
keeps using a pristine, auth-disabled singleton.

Token coexistence (slack-specific): slack's legacy API auth is Bearer
``xoxb-``/``xoxp-`` prefix sniffing with NO value validation. Those tokens are
not JWTs (no three-dot header.payload.signature structure), so with
AUTH_ENABLED=1 the middleware rejects them as malformed (401); they keep
working only in disabled mode -- both modes are pinned below.
"""

import importlib
import json
import re
import sys

import httpx
import pytest
from fastapi import FastAPI
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from env_0_auth_client.testing import generate_test_keypair, jwks_for, make_jwt
from mock_slack.models import init_db, reset_engine

KID = "test-key-001"
PRIVATE_KEY, PUBLIC_KEY = generate_test_keypair()
JWKS = jwks_for(PUBLIC_KEY, kid=KID)

# Actual identities seeded by scenario "default", seed 42 (see
# mock_slack/seed/content.py PERSONAS): auth's slack seeds must use THESE
# slack user ids as token subs.
ALICE = "U01ALEXCHEN"
ALICE_EMAIL = "alex@nexusai.com"
PRIYA = "U02PRIYAPATEL"
PRIYA_EMAIL = "priya@nexusai.com"
BOT = "B01MOCKBOT"  # is_bot=True app user
GENERAL = "C01GENERAL"


def _token(scope: str = "", sub: str = ALICE, **kwargs) -> str:
    return make_jwt(private_key=PRIVATE_KEY, kid=KID, sub=sub, scope=scope, **kwargs)


def _bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def auth_app(monkeypatch):
    """Fresh app instance with SlackEnv_0AuthMiddleware and static (offline) JWKS."""
    for var in ("AUTH_ENABLED", "AUTH_INTROSPECT", "AUTH_ISSUER", "AUTH_URL"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("AUTH_REPORT", "0")

    import mock_slack.api.app as app_module

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
    def test_every_api_route_has_scope_map_entry(self):
        """Every registered /api route must appear in SCOPE_MAP (and no stale keys)."""
        from mock_slack.api.app import app
        from mock_slack.auth_scopes import SCOPE_MAP, SLACK_PREFIX

        registered = set()
        for route in app.routes:
            if isinstance(route, APIRoute) and route.path.startswith(SLACK_PREFIX + "/"):
                for method in route.methods:
                    if method not in ("HEAD", "OPTIONS"):
                        registered.add((method, route.path))

        assert registered, "no /api routes registered -- enumeration broken?"
        missing = registered - set(SCOPE_MAP)
        assert not missing, f"routes missing from SCOPE_MAP: {sorted(missing)}"
        stale = set(SCOPE_MAP) - registered
        assert not stale, f"SCOPE_MAP keys matching no registered route: {sorted(stale)}"

    def test_scope_lists_are_slack_style_scopes(self):
        from mock_slack.auth_scopes import SCOPE_MAP

        # auth.test deliberately requires a valid token but no scope (real
        # Slack: auth.test has no required scopes).
        no_scope_ok = {("POST", "/api/auth.test")}
        for key, scopes in SCOPE_MAP.items():
            if key in no_scope_ok:
                assert scopes == [], f"{key} pinned as the only no-scope route"
                continue
            assert scopes, f"empty scope list for {key}"
            for scope in scopes:
                assert re.fullmatch(r"[a-z][a-z.]*:[a-z][a-z.]*", scope), (
                    f"non-Slack-style scope {scope!r} for {key}"
                )

    def test_every_non_api_route_is_exempt(self):
        """Web UI, admin, docs, static and mcp routes bypass auth entirely."""
        from mock_slack.api.app import app
        from mock_slack.api.auth_middleware import (
            EXEMPT_EXACT_PATHS,
            SlackEnv_0AuthMiddleware,
        )

        mw = SlackEnv_0AuthMiddleware(app, jwks_static=JWKS)
        not_exempt = []
        for route in app.routes:
            path = getattr(route, "path", None)
            if path is None or path.startswith("/api/"):
                continue
            if path in EXEMPT_EXACT_PATHS or mw._is_exempt(path):
                continue
            not_exempt.append(path)
        assert not not_exempt, f"non-API routes not covered by exemptions: {sorted(not_exempt)}"

    def test_exempt_prefixes_extend_contract_defaults(self):
        from env_0_auth_client.middleware import DEFAULT_EXEMPT_PREFIXES
        from mock_slack.api.auth_middleware import SLACK_EXEMPT_PREFIXES

        for prefix in DEFAULT_EXEMPT_PREFIXES:
            assert prefix in SLACK_EXEMPT_PREFIXES
        for prefix in ("/static", "/mcp", "/channel", "/dms", "/threads", "/new-dm"):
            assert prefix in SLACK_EXEMPT_PREFIXES


class TestAuthEnabled:
    def test_valid_token_lists_channels(self, auth_client):
        resp = auth_client.get(
            "/api/conversations.list", headers=_bearer(_token("channels:read"))
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert data["channels"]

    def test_auth_test_requires_token_but_no_scope(self, auth_client):
        # No token -> 401 from the middleware (not the Slack envelope).
        resp = auth_client.post("/api/auth.test")
        assert resp.status_code == 401
        # Any valid token, even with zero scopes -> 200.
        resp = auth_client.post("/api/auth.test", headers=_bearer(_token("")))
        assert resp.status_code == 200
        assert resp.json()["ok"] is True

    def test_wrong_scope_403_with_required_scopes(self, auth_client):
        resp = auth_client.post(
            "/api/chat.postMessage",
            json={"channel": GENERAL, "text": "hello"},
            headers=_bearer(_token("channels:read")),
        )
        assert resp.status_code == 403
        err = resp.json()["error"]
        assert err["code"] == 403
        assert err["status"] == "PERMISSION_DENIED"
        assert err["required_scopes"] == ["chat:write"]
        assert err["token_scopes"] == ["channels:read"]
        assert "hint" in err

    def test_history_requires_channels_history(self, auth_client):
        denied = auth_client.get(
            "/api/conversations.history",
            params={"channel": GENERAL},
            headers=_bearer(_token("channels:read")),
        )
        assert denied.status_code == 403
        assert denied.json()["error"]["required_scopes"] == ["channels:history"]

        allowed = auth_client.get(
            "/api/conversations.history",
            params={"channel": GENERAL},
            headers=_bearer(_token("channels:history")),
        )
        assert allowed.status_code == 200
        assert allowed.json()["ok"] is True

    def test_email_endpoints_require_users_read_email(self, auth_client):
        # users:read is NOT enough: this mock always embeds profile.email.
        denied = auth_client.get(
            "/api/users.info",
            params={"user": PRIYA},
            headers=_bearer(_token("users:read")),
        )
        assert denied.status_code == 403
        err = denied.json()["error"]
        assert err["required_scopes"] == ["users:read.email"]
        assert err["token_scopes"] == ["users:read"]

        allowed = auth_client.get(
            "/api/users.info",
            params={"user": PRIYA},
            headers=_bearer(_token("users:read.email")),
        )
        assert allowed.status_code == 200
        assert allowed.json()["user"]["profile"]["email"] == PRIYA_EMAIL

    def test_presence_read_allowed_with_users_read(self, auth_client):
        resp = auth_client.get(
            "/api/users.getPresence", headers=_bearer(_token("users:read"))
        )
        assert resp.status_code == 200
        assert resp.json()["ok"] is True

    def test_jwt_identity_is_a_user_token(self, auth_client):
        """The token's sub (a human) makes token_type 'user': search works and
        conversations.list carries the user-token-only last_read field."""
        search = auth_client.get(
            "/api/search.messages",
            params={"query": "the"},
            headers=_bearer(_token("search:read")),
        )
        assert search.status_code == 200
        assert search.json()["ok"] is True  # bot tokens get not_allowed_token_type

        listing = auth_client.get(
            "/api/conversations.list", headers=_bearer(_token("channels:read"))
        )
        assert all("last_read" in ch for ch in listing.json()["channels"])

    def test_bot_sub_is_a_bot_token(self, auth_client):
        """A token whose sub is the bot app user keeps bot-token semantics."""
        search = auth_client.get(
            "/api/search.messages",
            params={"query": "the"},
            headers=_bearer(_token("search:read", sub=BOT)),
        )
        assert search.status_code == 200
        assert search.json() == {"ok": False, "error": "not_allowed_token_type"}

        listing = auth_client.get(
            "/api/conversations.list", headers=_bearer(_token("channels:read", sub=BOT))
        )
        assert all("last_read" not in ch for ch in listing.json()["channels"])

    def test_legacy_xoxb_token_rejected_when_auth_enabled(self, auth_client):
        """Coexistence rule: xoxb-* tokens are not JWTs (no three-dot
        structure) and only work when AUTH_ENABLED is unset."""
        resp = auth_client.get(
            "/api/conversations.list",
            headers={"Authorization": "Bearer xoxb-mock-bot-token"},
        )
        assert resp.status_code == 401
        err = resp.json()["error"]
        assert err["status"] == "UNAUTHENTICATED"
        assert "malformed" in err["message"]

    def test_legacy_xoxp_token_rejected_when_auth_enabled(self, auth_client):
        resp = auth_client.get(
            "/api/search.messages",
            params={"query": "x"},
            headers={"Authorization": "Bearer xoxp-mock-user-token"},
        )
        assert resp.status_code == 401
        assert resp.json()["error"]["status"] == "UNAUTHENTICATED"

    def test_expired_token_401_with_refresh_hint(self, auth_client):
        resp = auth_client.get(
            "/api/conversations.list",
            headers=_bearer(_token("channels:read", expires_in=-60)),
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
        resp = auth_client.get("/api/conversations.list")
        assert resp.status_code == 401
        err = resp.json()["error"]
        assert err["code"] == 401
        assert err["status"] == "UNAUTHENTICATED"
        assert "WWW-Authenticate" in resp.headers

    def test_bad_signature_401(self, auth_client):
        other_private, _ = generate_test_keypair()
        forged = make_jwt(private_key=other_private, kid=KID, sub=ALICE, scope="channels:read")
        resp = auth_client.get("/api/conversations.list", headers=_bearer(forged))
        assert resp.status_code == 401
        assert resp.json()["error"]["status"] == "UNAUTHENTICATED"

    def test_options_requests_bypass_auth(self, auth_client):
        resp = auth_client.options("/api/conversations.list")
        assert resp.status_code != 401

    def test_health_unauthenticated(self, auth_client):
        resp = auth_client.get("/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}

    def test_admin_state_unauthenticated(self, auth_client):
        resp = auth_client.get("/_admin/state")
        assert resp.status_code == 200

    def test_admin_action_log_unauthenticated(self, auth_client):
        resp = auth_client.get("/_admin/action_log")
        assert resp.status_code == 200


class TestIdentityAndImpersonation:
    """Slack has no {userId} path params -- the token IS the identity -- so the
    gmail-style impersonation guard reduces to the few endpoints that accept
    an explicit acting-user override (users.profile.set). Directory READS of
    other users stay legitimate, exactly like real Slack."""

    SENTINEL = "auth-test-status-7f3a"

    def test_profile_set_implicit_self_targets_token_sub(self, auth_client):
        # Without auth, this endpoint targets the FIRST non-bot user; the
        # token sub must win instead.
        resp = auth_client.post(
            "/api/users.profile.set",
            json={"profile": {"status_text": self.SENTINEL}},
            headers=_bearer(_token("users.profile:write", sub=PRIYA)),
        )
        assert resp.status_code == 200
        assert resp.json()["ok"] is True
        assert resp.json()["profile"]["status_text"] == self.SENTINEL

        priya = auth_client.get(
            "/api/users.profile.get",
            params={"user": PRIYA},
            headers=_bearer(_token("users:read.email")),
        ).json()
        assert priya["profile"]["status_text"] == self.SENTINEL
        alex = auth_client.get(
            "/api/users.profile.get",
            params={"user": ALICE},
            headers=_bearer(_token("users:read.email")),
        ).json()
        assert alex["profile"]["status_text"] != self.SENTINEL

    def test_profile_set_explicit_matching_user_allowed(self, auth_client):
        resp = auth_client.post(
            "/api/users.profile.set",
            json={"user": PRIYA, "profile": {"status_text": "ok"}},
            headers=_bearer(_token("users.profile:write", sub=PRIYA)),
        )
        assert resp.status_code == 200
        assert resp.json()["ok"] is True

    def test_profile_set_mismatching_user_403_impersonation_body(self, auth_client):
        resp = auth_client.post(
            "/api/users.profile.set",
            json={"user": PRIYA, "profile": {"status_text": "hacked"}},
            headers=_bearer(_token("users.profile:write", sub=ALICE)),
        )
        assert resp.status_code == 403
        # Exact contract body -- NOT the Slack {"ok": false} envelope.
        assert resp.json() == {
            "error": {
                "code": 403,
                "status": "PERMISSION_DENIED",
                "message": "Cannot access another user's resources",
                "authenticated_user": ALICE,
                "requested_user": PRIYA,
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
            resp = auth_client.post(
                "/api/users.profile.set",
                json={"user": PRIYA, "profile": {"status_text": "hacked"}},
                headers=_bearer(_token("users.profile:write", sub=ALICE)),
            )
            assert resp.status_code == 403
        finally:
            reporting.set_transport(None)

        attempts = [e for e in events if e["event_type"] == "impersonation_attempt"]
        assert attempts, f"no impersonation_attempt among events: {events}"
        event = attempts[0]
        assert event["user_id"] == ALICE
        assert event["details"]["authenticated_user"] == ALICE
        assert event["details"]["requested_user"] == PRIYA

    def test_directory_reads_of_other_users_are_allowed(self, auth_client):
        resp = auth_client.get(
            "/api/users.info",
            params={"user": PRIYA},
            headers=_bearer(_token("users:read.email", sub=ALICE)),
        )
        assert resp.status_code == 200
        assert resp.json()["user"]["id"] == PRIYA

    def test_set_presence_targets_token_sub(self, auth_client):
        resp = auth_client.post(
            "/api/users.setPresence",
            json={"presence": "away"},
            headers=_bearer(_token("users:write", sub=PRIYA)),
        )
        assert resp.status_code == 200
        assert resp.json()["ok"] is True

        explicit = auth_client.get(
            "/api/users.getPresence",
            params={"user": PRIYA},
            headers=_bearer(_token("users:read", sub=ALICE)),
        ).json()
        assert explicit["presence"] == "away"

        implicit = auth_client.get(
            "/api/users.getPresence",
            headers=_bearer(_token("users:read", sub=PRIYA)),
        ).json()
        assert implicit["presence"] == "away"

    def test_profile_get_implicit_self(self, auth_client):
        resp = auth_client.get(
            "/api/users.profile.get",
            headers=_bearer(_token("users:read.email", sub=PRIYA)),
        )
        assert resp.status_code == 200
        assert resp.json()["profile"]["email"] == PRIYA_EMAIL


class TestEmailClaimFallback:
    """Identity-alignment: a token whose ``sub`` is not a local slack user id
    is resolved via its ``email`` claim (case-insensitive) to a LOCAL slack
    user; the resolved id is the effective identity everywhere the token sub
    is consumed (implicit-self endpoints, token-type, impersonation guard).
    """

    # auth's gmail/gcal-aligned id; NOT a slack user id (slack's
    # local id for the same person is U01ALEXCHEN).
    NONLOCAL_SUB = "user1"

    def _fallback_token(self, scope: str = "users:read.email", email: str = ALICE_EMAIL) -> str:
        return _token(scope, sub=self.NONLOCAL_SUB, email=email)

    def test_nonlocal_sub_with_seeded_email_resolves_implicit_self(self, auth_client):
        resp = auth_client.get(
            "/api/users.profile.get", headers=_bearer(self._fallback_token())
        )
        assert resp.status_code == 200
        assert resp.json()["ok"] is True
        assert resp.json()["profile"]["email"] == ALICE_EMAIL

    def test_email_match_is_case_insensitive(self, auth_client):
        resp = auth_client.get(
            "/api/users.profile.get",
            headers=_bearer(self._fallback_token(email=ALICE_EMAIL.upper())),
        )
        assert resp.status_code == 200
        assert resp.json()["profile"]["email"] == ALICE_EMAIL

    def test_resolved_identity_is_a_user_token(self, auth_client):
        # token-type resolution follows the RESOLVED identity: search.messages
        # is user-token-only and must accept the resolved human identity.
        resp = auth_client.get(
            "/api/search.messages",
            params={"query": "anything"},
            headers=_bearer(self._fallback_token("search:read")),
        )
        assert resp.status_code == 200
        assert resp.json()["ok"] is True

    def test_set_presence_targets_resolved_local_user(self, auth_client):
        resp = auth_client.post(
            "/api/users.setPresence",
            json={"presence": "away"},
            headers=_bearer(self._fallback_token("users:write")),
        )
        assert resp.status_code == 200
        assert resp.json()["ok"] is True
        explicit = auth_client.get(
            "/api/users.getPresence",
            params={"user": ALICE},
            headers=_bearer(_token("users:read", sub=PRIYA)),
        ).json()
        assert explicit["presence"] == "away"

    def test_profile_set_naming_resolved_local_id_does_not_trip_guard(self, auth_client):
        resp = auth_client.post(
            "/api/users.profile.set",
            json={"user": ALICE, "profile": {"status_text": "fallback-ok"}},
            headers=_bearer(self._fallback_token("users.profile:write")),
        )
        assert resp.status_code == 200
        assert resp.json()["ok"] is True
        assert resp.json()["profile"]["status_text"] == "fallback-ok"

    def test_profile_set_genuinely_different_user_still_403s(self, auth_client):
        resp = auth_client.post(
            "/api/users.profile.set",
            json={"user": PRIYA, "profile": {"status_text": "hacked"}},
            headers=_bearer(self._fallback_token("users.profile:write")),
        )
        assert resp.status_code == 403
        err = resp.json()["error"]
        assert err["message"] == "Cannot access another user's resources"
        # The contract body names the RESOLVED local identity.
        assert err["authenticated_user"] == ALICE
        assert err["requested_user"] == PRIYA

    def test_unknown_sub_and_unknown_email_behaves_as_before(self, auth_client):
        # No local id AND no email match: the raw sub passes through as-is and
        # routes answer exactly as they did pre-fallback (user_not_found).
        resp = auth_client.get(
            "/api/users.profile.get",
            headers=_bearer(_token("users:read.email", sub="ghost", email="ghost@nowhere.test")),
        )
        assert resp.status_code == 200
        assert resp.json() == {"ok": False, "error": "user_not_found"}

    def test_local_sub_wins_over_email_claim(self, auth_client):
        # Resolution order pin: id == sub (a) beats the email claim (b) -- a
        # token for PRIYA carrying alex's email acts as PRIYA.
        resp = auth_client.get(
            "/api/users.profile.get",
            headers=_bearer(_token("users:read.email", sub=PRIYA, email=ALICE_EMAIL)),
        )
        assert resp.status_code == 200
        assert resp.json()["profile"]["email"] == PRIYA_EMAIL

    def test_bot_email_fallback_keeps_bot_token_type(self, auth_client):
        # A nonlocal sub resolving (by email) to the bot row must still be
        # treated as a bot token: search.messages is user-token-only. The
        # seeded bot has email="", so give it one in this test's temp DB.
        from mock_slack.models import SlackUser, get_session_factory

        bot_email = "mockbot@nexusai.com"
        db = get_session_factory()()
        try:
            bot = db.query(SlackUser).filter(SlackUser.id == BOT).first()
            assert bot is not None
            bot.email = bot_email
            db.commit()
        finally:
            db.close()
        resp = auth_client.get(
            "/api/search.messages",
            params={"query": "anything"},
            headers=_bearer(_token("search:read", sub="svc_bot", email=bot_email)),
        )
        assert resp.status_code == 200
        assert resp.json() == {"ok": False, "error": "not_allowed_token_type"}


class TestWebUIExemption:
    """With AUTH_ENABLED=1, the human web UI stays usable WITHOUT a token.

    The web UI identifies users via browser sessions, not Bearer tokens --
    the real-world session-vs-API split. /mcp is likewise exempt (agent MCP
    clients are out of OAuth scope for v1). The API under /api still requires
    Bearer tokens. See mock_slack/api/auth_middleware.py and API_NOTES.md.
    """

    def test_workspace_root_no_token_200(self, auth_client):
        resp = auth_client.get("/")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]

    def test_root_with_query_params_no_token_200(self, auth_client):
        # Query strings don't change the path: still the exact-match "/" route.
        resp = auth_client.get("/", params={"foo": "bar"})
        assert resp.status_code == 200

    def test_channel_page_no_token_200(self, auth_client):
        resp = auth_client.get(f"/channel/{GENERAL}")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]

    def test_dms_page_no_token_200(self, auth_client):
        resp = auth_client.get("/dms")
        assert resp.status_code == 200

    def test_threads_page_no_token_200(self, auth_client):
        resp = auth_client.get("/threads")
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
        resp = auth_client.get("/api/conversations.list")
        assert resp.status_code == 401
        assert resp.json()["error"]["status"] == "UNAUTHENTICATED"

    def test_app_prefix_does_not_exempt_api(self, auth_client):
        # Segment-boundary matching: the "/app" web prefix must never bleed
        # into "/api/...".
        resp = auth_client.post("/api/auth.test")
        assert resp.status_code == 401


class TestAuthDisabledRegression:
    """CRITICAL: with AUTH_ENABLED unset, behavior is byte-identical legacy.

    These tests use the standard ``client`` fixture from conftest (the module
    singleton, which was assembled with auth disabled). In this mode the
    legacy token-agnostic Bearer handling -- xoxb-/xoxp- prefix sniffing, no
    value validation, no 401s -- must keep working untouched.
    """

    def test_singleton_has_no_auth_middleware(self, client):
        from mock_slack.api.app import app

        assert not any(
            "Env_0AuthMiddleware" in m.cls.__name__ for m in app.user_middleware
        ), "Env_0AuthMiddleware must not be installed when AUTH_ENABLED is unset"

    def test_xoxb_bot_token_still_works(self, client):
        resp = client.get(
            "/api/conversations.list",
            headers={"Authorization": "Bearer xoxb-mock-bot-token"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        # Bot-token shape: no last_read.
        assert all("last_read" not in ch for ch in data["channels"])

    def test_xoxp_user_token_still_works(self, client):
        resp = client.get(
            "/api/search.messages",
            params={"query": "x"},
            headers={"Authorization": "Bearer xoxp-mock-user-token"},
        )
        assert resp.status_code == 200
        assert resp.json()["ok"] is True

    def test_no_token_still_works(self, client):
        resp = client.get("/api/conversations.list")
        assert resp.status_code == 200
        assert resp.json()["ok"] is True

    def test_arbitrary_token_value_still_works(self, client):
        # Token-agnostic legacy mode: even a JWT-shaped garbage value is
        # accepted (and treated as a bot token).
        resp = client.get(
            "/api/conversations.list",
            headers={"Authorization": "Bearer eyJhbGciOiJSUzI1NiJ9.e30.garbage"},
        )
        assert resp.status_code == 200
        assert resp.json()["ok"] is True

    def test_profile_set_explicit_other_user_is_not_impersonation(self, client):
        # The impersonation guard must be a no-op without auth.
        resp = client.post(
            "/api/users.profile.set",
            json={"user": PRIYA, "profile": {"status_text": "legacy"}},
        )
        assert resp.status_code == 200
        assert resp.json()["ok"] is True

    def test_apply_auth_returns_false_when_disabled(self, monkeypatch):
        import mock_slack.api.app as app_module

        monkeypatch.delenv("AUTH_ENABLED", raising=False)
        assert app_module._apply_auth(FastAPI()) is False

    def test_apply_auth_raises_runtime_error_without_package(self, monkeypatch):
        import mock_slack.api.app as app_module

        monkeypatch.setenv("AUTH_ENABLED", "1")
        # None in sys.modules makes `import env_0_auth_client` raise ImportError.
        monkeypatch.setitem(sys.modules, "env_0_auth_client", None)
        with pytest.raises(RuntimeError, match="auth-client is not installed"):
            app_module._apply_auth(FastAPI())
