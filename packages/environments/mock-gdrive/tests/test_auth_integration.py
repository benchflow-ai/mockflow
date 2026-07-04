"""Integration tests for the auth retrofit (AUTH_ENABLED).

Fully offline: JWKS is injected statically via env_0_auth_client.testing, and
event reporting is disabled (AUTH_REPORT=0) except where a MockTransport
captures events explicitly.

The FastAPI app in mock_gdrive.api.app is a module-level singleton and
AUTH_ENABLED is read at import time, so the ``auth_app`` fixture builds a
FRESH instance via importlib.reload (with auth disabled, so the module-level
``_apply_auth(app)`` is a no-op) and then applies the middleware explicitly
with the static JWKS. Teardown reloads once more so every other test module
keeps using a pristine, auth-disabled singleton.

mock_gdrive.api.deps is NOT reloaded, so the ``get_db`` dependency override
and the ``ImpersonationError`` class identity are stable across reloads.
"""

import importlib
import json
import sys

import httpx
import pytest
from fastapi import FastAPI
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from env_0_auth_client.testing import generate_test_keypair, jwks_for, make_jwt
from mock_gdrive.api.deps import get_db
from mock_gdrive.models import User, File, Permission

KID = "test-key-001"
PRIVATE_KEY, PUBLIC_KEY = generate_test_keypair()
JWKS = jwks_for(PUBLIC_KEY, kid=KID)

# Identities matching mock_gdrive/seed/hierarchy.py USERS -- the auth
# seeds must align with THESE ids (auth adapts, gdrive seeds unchanged).
ALEX = "user_alex"
ALEX_EMAIL = "alex@nexusai.com"
JORDAN = "user_jordan"
JORDAN_EMAIL = "jordan@nexusai.com"


def _token(scope: str = "", sub: str = ALEX, **kwargs) -> str:
    return make_jwt(private_key=PRIVATE_KEY, kid=KID, sub=sub, scope=scope, **kwargs)


def _bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def auth_app(monkeypatch):
    """Fresh app instance with GdriveEnv_0AuthMiddleware and static (offline) JWKS."""
    for var in ("AUTH_ENABLED", "AUTH_INTROSPECT", "AUTH_ISSUER", "AUTH_URL"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("AUTH_REPORT", "0")

    import mock_gdrive.api.app as app_module

    app_module = importlib.reload(app_module)  # fresh singleton, no auth yet
    monkeypatch.setenv("AUTH_ENABLED", "1")
    assert app_module._apply_auth(app_module.app, jwks_static=JWKS) is True

    yield app_module.app

    # Restore a pristine auth-disabled singleton for the other test modules.
    monkeypatch.delenv("AUTH_ENABLED", raising=False)
    importlib.reload(app_module)


@pytest.fixture
def auth_seed(db_session):
    """Users matching the default seed identities + content-bearing files."""
    alex = User(id=ALEX, email=ALEX_EMAIL, display_name="Alex Chen")
    jordan = User(id=JORDAN, email=JORDAN_EMAIL, display_name="Jordan Kim")
    db_session.add_all([alex, jordan])

    binary = File(
        id="file_binary",
        name="notes.txt",
        mime_type="text/plain",
        owner_id=ALEX,
        last_modifying_user_id=ALEX,
        content_blob=b"hello drive content",
        size=19,
    )
    gdoc = File(
        id="file_gdoc",
        name="Design Doc",
        mime_type="application/vnd.google-apps.document",
        owner_id=ALEX,
        last_modifying_user_id=ALEX,
        content_text="exported document text",
    )
    db_session.add_all([binary, gdoc])
    db_session.add_all([
        Permission(
            id=f"perm_{f.id}",
            file_id=f.id,
            role="owner",
            type="user",
            email_address=ALEX_EMAIL,
            display_name="Alex Chen",
        )
        for f in (binary, gdoc)
    ])
    db_session.commit()
    return {"binary": binary, "gdoc": gdoc}


@pytest.fixture
def auth_client(auth_app, db_session, auth_seed):
    """TestClient against the auth-enabled fresh app + in-memory seeded DB."""
    def _override_get_db():
        try:
            yield db_session
        finally:
            pass

    auth_app.dependency_overrides[get_db] = _override_get_db
    with TestClient(auth_app) as c:
        yield c
    auth_app.dependency_overrides.clear()


class TestScopeMapCoverage:
    def test_every_drive_route_has_scope_map_entry(self):
        """Every registered /drive/v3 + /upload/drive/v3 route must appear in
        SCOPE_MAP (and the map must hold no stale keys)."""
        from mock_gdrive.api.app import app
        from mock_gdrive.auth_scopes import API_PREFIXES, SCOPE_MAP

        registered = set()
        for route in app.routes:
            if isinstance(route, APIRoute) and route.path.startswith(API_PREFIXES):
                for method in route.methods:
                    if method not in ("HEAD", "OPTIONS"):
                        registered.add((method, route.path))

        assert registered, "no /drive/v3 routes registered -- enumeration broken?"
        missing = registered - set(SCOPE_MAP)
        assert not missing, f"routes missing from SCOPE_MAP: {sorted(missing)}"
        stale = set(SCOPE_MAP) - registered
        assert not stale, f"SCOPE_MAP keys matching no registered route: {sorted(stale)}"

    def test_scope_lists_are_nonempty_drive_scopes(self):
        from mock_gdrive.auth_scopes import CONTENT_DOWNLOAD_SCOPES, SCOPE_MAP

        for key, scopes in SCOPE_MAP.items():
            assert scopes, f"empty scope list for {key}"
            for scope in scopes:
                assert scope.startswith("drive."), f"unexpected scope {scope!r} for {key}"
        assert CONTENT_DOWNLOAD_SCOPES == ["drive.readonly", "drive.full"]

    def test_permissions_routes_pinned_to_drive_full(self):
        """Sharing endpoints (delegated-access surface) must require drive.full only."""
        from mock_gdrive.auth_scopes import SCOPE_MAP

        perm_keys = [k for k in SCOPE_MAP if "/permissions" in k[1]]
        assert len(perm_keys) == 5
        for key in perm_keys:
            assert SCOPE_MAP[key] == ["drive.full"], key


class TestAuthEnabled:
    def test_token_sub_resolves_user(self, auth_client):
        resp = auth_client.get(
            "/drive/v3/about", headers=_bearer(_token("drive.metadata.readonly"))
        )
        assert resp.status_code == 200
        assert resp.json()["user"]["emailAddress"] == ALEX_EMAIL

    def test_valid_token_lists_files(self, auth_client):
        resp = auth_client.get(
            "/drive/v3/files", headers=_bearer(_token("drive.readonly"))
        )
        assert resp.status_code == 200
        names = [f["name"] for f in resp.json()["files"]]
        assert "notes.txt" in names

    def test_metadata_scope_reads_file_metadata(self, auth_client):
        resp = auth_client.get(
            "/drive/v3/files/file_binary",
            headers=_bearer(_token("drive.metadata.readonly")),
        )
        assert resp.status_code == 200
        assert resp.json()["name"] == "notes.txt"

    def test_metadata_scope_cannot_download_content(self, auth_client):
        # ...but ?alt=media downloads content, so metadata.readonly is rejected
        # by the middleware's alt=media upgrade (exact contract 403 body).
        resp = auth_client.get(
            "/drive/v3/files/file_binary",
            params={"alt": "media"},
            headers=_bearer(_token("drive.metadata.readonly")),
        )
        assert resp.status_code == 403
        err = resp.json()["error"]
        assert err["code"] == 403
        assert err["status"] == "PERMISSION_DENIED"
        assert err["required_scopes"] == ["drive.readonly", "drive.full"]
        assert err["token_scopes"] == ["drive.metadata.readonly"]
        assert "hint" in err

    def test_readonly_scope_downloads_content(self, auth_client):
        resp = auth_client.get(
            "/drive/v3/files/file_binary",
            params={"alt": "media"},
            headers=_bearer(_token("drive.readonly")),
        )
        assert resp.status_code == 200
        assert resp.content == b"hello drive content"

    def test_export_requires_content_scope(self, auth_client):
        denied = auth_client.get(
            "/drive/v3/files/file_gdoc/export",
            params={"mimeType": "text/plain"},
            headers=_bearer(_token("drive.metadata.readonly")),
        )
        assert denied.status_code == 403
        assert denied.json()["error"]["required_scopes"] == ["drive.readonly", "drive.full"]

        allowed = auth_client.get(
            "/drive/v3/files/file_gdoc/export",
            params={"mimeType": "text/plain"},
            headers=_bearer(_token("drive.readonly")),
        )
        assert allowed.status_code == 200
        assert allowed.content == b"exported document text"

    def test_create_without_write_scope_403(self, auth_client):
        resp = auth_client.post(
            "/drive/v3/files",
            json={"name": "new.txt", "mimeType": "text/plain"},
            headers=_bearer(_token("drive.readonly")),
        )
        assert resp.status_code == 403
        err = resp.json()["error"]
        assert err["required_scopes"] == ["drive.file", "drive.full"]
        assert err["token_scopes"] == ["drive.readonly"]

    def test_create_with_drive_file_scope_200(self, auth_client):
        resp = auth_client.post(
            "/drive/v3/files",
            json={"name": "new.txt", "mimeType": "text/plain"},
            headers=_bearer(_token("drive.file")),
        )
        assert resp.status_code == 200
        assert resp.json()["name"] == "new.txt"

    def test_delete_with_drive_file_scope_204(self, auth_client):
        resp = auth_client.delete(
            "/drive/v3/files/file_binary", headers=_bearer(_token("drive.file"))
        )
        assert resp.status_code == 204

    def test_permissions_require_drive_full(self, auth_client):
        # Even reads of the sharing surface are pinned to drive.full -- and
        # drive.file (write-capable) is NOT sufficient.
        for scope in ("drive.readonly", "drive.file"):
            resp = auth_client.get(
                "/drive/v3/files/file_binary/permissions",
                headers=_bearer(_token(scope)),
            )
            assert resp.status_code == 403, scope
            assert resp.json()["error"]["required_scopes"] == ["drive.full"]

        resp = auth_client.get(
            "/drive/v3/files/file_binary/permissions",
            headers=_bearer(_token("drive.full")),
        )
        assert resp.status_code == 200
        assert resp.json()["permissions"]

    def test_share_with_drive_full_200(self, auth_client):
        resp = auth_client.post(
            "/drive/v3/files/file_binary/permissions",
            json={"role": "reader", "type": "user", "emailAddress": JORDAN_EMAIL},
            headers=_bearer(_token("drive.full")),
        )
        assert resp.status_code in (200, 201)
        assert resp.json()["role"] == "reader"

    def test_mock_header_matching_token_user_allowed(self, auth_client):
        for value in (ALEX, ALEX_EMAIL):
            resp = auth_client.get(
                "/drive/v3/about",
                headers={**_bearer(_token("drive.readonly")), "X-Mock-Drive-User": value},
            )
            assert resp.status_code == 200, value
            assert resp.json()["user"]["emailAddress"] == ALEX_EMAIL

    def test_mock_header_other_user_403_impersonation_body(self, auth_client):
        resp = auth_client.get(
            "/drive/v3/about",
            headers={**_bearer(_token("drive.readonly", sub=ALEX)), "X-Mock-Drive-User": JORDAN},
        )
        assert resp.status_code == 403
        # Exact contract body -- NOT the Drive error envelope.
        assert resp.json() == {
            "error": {
                "code": 403,
                "status": "PERMISSION_DENIED",
                "message": "Cannot access another user's resources",
                "authenticated_user": ALEX,
                "requested_user": JORDAN,
            }
        }

    def test_mock_header_other_user_by_email_403(self, auth_client):
        resp = auth_client.get(
            "/drive/v3/about",
            headers={
                **_bearer(_token("drive.readonly", sub=ALEX)),
                "X-Mock-Drive-User": JORDAN_EMAIL,
            },
        )
        assert resp.status_code == 403
        err = resp.json()["error"]
        assert err["authenticated_user"] == ALEX
        assert err["requested_user"] == JORDAN_EMAIL

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
                "/drive/v3/about",
                headers={
                    **_bearer(_token("drive.readonly", sub=ALEX)),
                    "X-Mock-Drive-User": JORDAN,
                },
            )
            assert resp.status_code == 403
        finally:
            reporting.set_transport(None)

        attempts = [e for e in events if e["event_type"] == "impersonation_attempt"]
        assert attempts, f"no impersonation_attempt among events: {events}"
        event = attempts[0]
        assert event["user_id"] == ALEX
        assert event["details"]["authenticated_user"] == ALEX
        assert event["details"]["requested_user"] == JORDAN

    def test_media_scope_escalation_is_reported(self, auth_client, monkeypatch):
        from env_0_auth_client import reporting

        events = []

        def handler(request: httpx.Request) -> httpx.Response:
            events.append(json.loads(request.content))
            return httpx.Response(200, json={"status": "ok"})

        monkeypatch.setenv("AUTH_REPORT", "1")
        reporting.set_transport(httpx.MockTransport(handler))
        try:
            resp = auth_client.get(
                "/drive/v3/files/file_binary",
                params={"alt": "media"},
                headers=_bearer(_token("drive.metadata.readonly")),
            )
            assert resp.status_code == 403
        finally:
            reporting.set_transport(None)

        attempts = [e for e in events if e["event_type"] == "scope_escalation_attempt"]
        assert attempts, f"no scope_escalation_attempt among events: {events}"
        details = attempts[0]["details"]
        assert details["route"] == "/drive/v3/files/{fileId}"
        assert details["alt"] == "media"
        assert details["required_scopes"] == ["drive.readonly", "drive.full"]

    def test_expired_token_401_with_refresh_hint(self, auth_client):
        resp = auth_client.get(
            "/drive/v3/files",
            headers=_bearer(_token("drive.readonly", expires_in=-60)),
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
        resp = auth_client.get("/drive/v3/files")
        assert resp.status_code == 401
        err = resp.json()["error"]
        assert err["code"] == 401
        assert err["status"] == "UNAUTHENTICATED"
        assert "WWW-Authenticate" in resp.headers

    def test_legacy_bearer_identifier_is_rejected(self, auth_client):
        # Pre-auth, `Authorization: Bearer user_alex` selected a user. Under
        # auth the Authorization header must be a verified JWT -- a bare
        # identifier is a malformed token, never an identity.
        resp = auth_client.get("/drive/v3/files", headers=_bearer(ALEX))
        assert resp.status_code == 401
        assert resp.json()["error"]["status"] == "UNAUTHENTICATED"

    def test_bad_signature_401(self, auth_client):
        other_private, _ = generate_test_keypair()
        forged = make_jwt(private_key=other_private, kid=KID, sub=ALEX, scope="drive.full")
        resp = auth_client.get("/drive/v3/files", headers=_bearer(forged))
        assert resp.status_code == 401
        assert resp.json()["error"]["status"] == "UNAUTHENTICATED"

    def test_health_unauthenticated(self, auth_client):
        resp = auth_client.get("/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}

    def test_admin_action_log_unauthenticated(self, auth_client):
        resp = auth_client.get("/_admin/action_log")
        assert resp.status_code == 200


class TestEmailClaimFallback:
    """Identity-alignment: a token whose ``sub`` is not a local user id is
    resolved via its ``email`` claim (case-insensitive); the resolved LOCAL
    user is the effective identity everywhere downstream.
    """

    # env-0-auth-style id (gmail/gcal use 'user1') that does NOT exist in
    # gdrive, whose local id for the same person is 'user_alex'.
    NONLOCAL_SUB = "user1"

    def _fallback_token(self, scope: str = "drive.readonly", email: str = ALEX_EMAIL) -> str:
        return _token(scope, sub=self.NONLOCAL_SUB, email=email)

    def test_nonlocal_sub_with_seeded_email_lists_files_as_user_alex(self, auth_client):
        resp = auth_client.get("/drive/v3/files", headers=_bearer(self._fallback_token()))
        assert resp.status_code == 200
        names = [f["name"] for f in resp.json()["files"]]
        assert "notes.txt" in names

    def test_nonlocal_sub_resolves_to_local_identity(self, auth_client):
        resp = auth_client.get(
            "/drive/v3/about",
            headers=_bearer(self._fallback_token("drive.metadata.readonly")),
        )
        assert resp.status_code == 200
        assert resp.json()["user"]["emailAddress"] == ALEX_EMAIL

    def test_email_match_is_case_insensitive(self, auth_client):
        resp = auth_client.get(
            "/drive/v3/about",
            headers=_bearer(
                self._fallback_token("drive.metadata.readonly", email=ALEX_EMAIL.upper())
            ),
        )
        assert resp.status_code == 200
        assert resp.json()["user"]["emailAddress"] == ALEX_EMAIL

    def test_header_naming_resolved_local_id_does_not_trip_guard(self, auth_client):
        resp = auth_client.get(
            "/drive/v3/files",
            headers={
                **_bearer(self._fallback_token()),
                "X-Mock-Drive-User": ALEX,  # the RESOLVED local id
            },
        )
        assert resp.status_code == 200

    def test_header_naming_other_user_still_403s(self, auth_client):
        resp = auth_client.get(
            "/drive/v3/files",
            headers={
                **_bearer(self._fallback_token()),
                "X-Mock-Drive-User": JORDAN,
            },
        )
        assert resp.status_code == 403
        err = resp.json()["error"]
        assert err["message"] == "Cannot access another user's resources"
        # The contract body names the RESOLVED local identity.
        assert err["authenticated_user"] == ALEX
        assert err["requested_user"] == JORDAN

    def test_unknown_sub_and_unknown_email_404_as_before(self, auth_client):
        resp = auth_client.get(
            "/drive/v3/files",
            headers=_bearer(_token("drive.readonly", sub="ghost", email="ghost@nowhere.test")),
        )
        assert resp.status_code == 404

    def test_local_sub_wins_over_email_claim(self, auth_client):
        # Resolution order pin: id == sub (a) beats the email claim (b) -- a
        # token for user_jordan carrying alex's email acts as user_jordan.
        resp = auth_client.get(
            "/drive/v3/about",
            headers=_bearer(
                _token("drive.metadata.readonly", sub=JORDAN, email=ALEX_EMAIL)
            ),
        )
        assert resp.status_code == 200
        assert resp.json()["user"]["emailAddress"] == JORDAN_EMAIL


class TestWebUIExemption:
    """With AUTH_ENABLED=1, the human web UI stays usable WITHOUT a token.

    The web dashboard identifies users via the mock_gdrive_user cookie (browser
    session), not Bearer tokens -- the real-world session-vs-API split. /mcp is
    likewise exempt (agent MCP clients are out of OAuth scope for v1, same
    decision as gmail). The API under /drive/v3 still requires Bearer
    tokens. See mock_gdrive/api/auth_middleware.py.
    """

    def test_home_root_no_token_200(self, auth_client):
        resp = auth_client.get("/")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]

    def test_home_with_query_params_no_token_200(self, auth_client):
        # Query strings don't change the path: still the exact-match "/" route.
        resp = auth_client.get("/", params={"view": "starred", "q": "notes"})
        assert resp.status_code == 200

    def test_file_detail_no_token_200(self, auth_client):
        resp = auth_client.get("/file/file_binary")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]

    def test_switch_user_no_token_303(self, auth_client):
        resp = auth_client.get(
            "/switch-user", params={"email": JORDAN_EMAIL}, follow_redirects=False
        )
        assert resp.status_code == 303

    def test_mcp_not_gated_by_auth(self, auth_client):
        # MCP is not mounted in tests: a 404 (rather than 401) proves the
        # middleware exempts /mcp instead of demanding a Bearer token.
        resp = auth_client.get("/mcp")
        assert resp.status_code == 404

    def test_api_still_requires_token_while_web_is_open(self, auth_client):
        # The "/" exemption is EXACT-match, not a "/" prefix that would
        # swallow every path: the API must still 401 without a token.
        assert auth_client.get("/").status_code == 200
        resp = auth_client.get("/drive/v3/files")
        assert resp.status_code == 401
        assert resp.json()["error"]["status"] == "UNAUTHENTICATED"

    def test_exempt_file_prefix_does_not_cover_api_files(self, auth_client):
        # "/file" is segment-boundary matched: it must NOT exempt
        # /drive/v3/files (different path entirely) nor leak via "/files".
        resp = auth_client.get("/drive/v3/files/file_binary")
        assert resp.status_code == 401

    def test_exempt_prefixes_extend_contract_defaults(self):
        from env_0_auth_client.middleware import DEFAULT_EXEMPT_PREFIXES
        from mock_gdrive.api.auth_middleware import GDRIVE_EXEMPT_PREFIXES

        for prefix in DEFAULT_EXEMPT_PREFIXES:
            assert prefix in GDRIVE_EXEMPT_PREFIXES
        for prefix in ("/file", "/switch-user", "/static", "/mcp"):
            assert prefix in GDRIVE_EXEMPT_PREFIXES


class TestAuthDisabledRegression:
    """CRITICAL: with AUTH_ENABLED unset, behavior is byte-identical legacy.

    These tests use the standard ``client`` fixture from conftest (the module
    singleton, which was assembled with auth disabled).
    """

    def test_singleton_has_no_auth_middleware(self, client):
        from mock_gdrive.api.app import app

        assert not any(
            "Env_0AuthMiddleware" in m.cls.__name__ for m in app.user_middleware
        ), "Env_0AuthMiddleware must not be installed when AUTH_ENABLED is unset"

    def test_no_headers_falls_back_to_first_user(self, client, seed_user):
        resp = client.get("/drive/v3/about")
        assert resp.status_code == 200
        assert resp.json()["user"]["emailAddress"] == seed_user.email

    def test_header_resolution_by_id(self, client, seed_users):
        resp = client.get(
            "/drive/v3/about", headers={"X-Mock-Drive-User": "user_bob"}
        )
        assert resp.status_code == 200
        assert resp.json()["user"]["emailAddress"] == "bob@example.com"

    def test_header_resolution_by_email(self, client, seed_users):
        resp = client.get(
            "/drive/v3/about", headers={"X-Mock-Drive-User": "alice@example.com"}
        )
        assert resp.status_code == 200
        assert resp.json()["user"]["emailAddress"] == "alice@example.com"

    def test_legacy_bearer_identifier_resolution(self, client, seed_users):
        # Legacy quirk preserved: a bare Bearer identifier selects a user.
        resp = client.get(
            "/drive/v3/about", headers={"Authorization": "Bearer user_bob"}
        )
        assert resp.status_code == 200
        assert resp.json()["user"]["emailAddress"] == "bob@example.com"

    def test_unknown_identifier_401_drive_envelope(self, client, seed_user):
        resp = client.get(
            "/drive/v3/about", headers={"X-Mock-Drive-User": "no_such_user"}
        )
        assert resp.status_code == 401
        err = resp.json()["error"]
        # Legacy Drive envelope (has 'errors' list), not the auth contract body.
        assert err["status"] == "UNAUTHENTICATED"
        assert err["errors"][0]["reason"] == "unauthorized"

    def test_apply_auth_returns_false_when_disabled(self, monkeypatch):
        import mock_gdrive.api.app as app_module

        monkeypatch.delenv("AUTH_ENABLED", raising=False)
        assert app_module._apply_auth(FastAPI()) is False

    def test_apply_auth_raises_runtime_error_without_package(self, monkeypatch):
        import mock_gdrive.api.app as app_module

        monkeypatch.setenv("AUTH_ENABLED", "1")
        # None in sys.modules makes `import env_0_auth_client` raise ImportError.
        monkeypatch.setitem(sys.modules, "env_0_auth_client", None)
        with pytest.raises(RuntimeError, match="auth-client is not installed"):
            app_module._apply_auth(FastAPI())
