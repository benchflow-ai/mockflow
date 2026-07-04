"""Integration tests for the auth retrofit (AUTH_ENABLED).

Fully offline: JWKS is injected statically via env_0_auth_client.testing, and
event reporting is disabled (AUTH_REPORT=0) except where a MockTransport
captures events explicitly.

The FastAPI app in mock_gdoc.api.app is a module-level singleton and
AUTH_ENABLED is read at import time, so the ``auth_app`` fixture builds a
FRESH instance via importlib.reload (with auth disabled, so the module-level
``_apply_auth(app)`` is a no-op) and then applies the middleware explicitly
with the static JWKS. Teardown reloads once more so every other test module
keeps using a pristine, auth-disabled singleton.

Identity note: gdoc has no userId path parameter -- the X-Env-0-Gdoc-User
header is the only explicit identity channel, so under auth the header is the
impersonation analog of gmail's mismatching path userId (mismatch -> contract
403 + impersonation_attempt report; matching/absent header -> token sub).
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
from mock_gdoc.models import Document, Permission, get_session_factory, init_db, reset_engine

KID = "test-key-001"
PRIVATE_KEY, PUBLIC_KEY = generate_test_keypair()
JWKS = jwks_for(PUBLIC_KEY, kid=KID)

# Actual identities seeded by scenario "default", seed 42 (see
# mock_gdoc/seed/generator.py + mock_gdoc/seed/content.py): the primary user
# is user_0; personas get user_1..user_9 (user_1 = Sarah Chen).
ALEX = "user_0"
ALEX_EMAIL = "alex@nexusai.com"
# Any identity other than the token sub; the impersonation check fires before
# any requested-user DB lookup, so existence is irrelevant.
OTHER_USER = "user_1"


def _token(scope: str = "", sub: str = ALEX, **kwargs) -> str:
    return make_jwt(private_key=PRIVATE_KEY, kid=KID, sub=sub, scope=scope, **kwargs)


def _bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _owned_doc_id(unshared: bool = False, uncommented: bool = False) -> str:
    """Id of a document owned by user_0 (optionally unshared / comment-free)."""
    from mock_gdoc.models import Comment

    db = get_session_factory()()
    try:
        query = db.query(Document).filter(Document.user_id == ALEX)
        if unshared:
            shared_ids = {p.document_id for p in db.query(Permission).all()}
            query = query.filter(~Document.id.in_(shared_ids))
        if uncommented:
            commented_ids = {c.document_id for c in db.query(Comment).all()}
            query = query.filter(~Document.id.in_(commented_ids))
        doc = query.first()
        assert doc is not None
        return doc.id
    finally:
        db.close()


@pytest.fixture
def auth_app(monkeypatch):
    """Fresh app instance with GdocEnv_0AuthMiddleware and static (offline) JWKS."""
    for var in ("AUTH_ENABLED", "AUTH_INTROSPECT", "AUTH_ISSUER", "AUTH_URL"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("AUTH_REPORT", "0")

    import mock_gdoc.api.app as app_module

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
        """Every registered /v1 route must appear in SCOPE_MAP (and no stale keys)."""
        from mock_gdoc.api.app import app
        from mock_gdoc.auth_scopes import DOCS_PREFIX, SCOPE_MAP

        registered = set()
        for route in app.routes:
            if isinstance(route, APIRoute) and route.path.startswith(DOCS_PREFIX):
                for method in route.methods:
                    if method not in ("HEAD", "OPTIONS"):
                        registered.add((method, route.path))

        assert registered, "no /v1 routes registered -- enumeration broken?"
        missing = registered - set(SCOPE_MAP)
        assert not missing, f"routes missing from SCOPE_MAP: {sorted(missing)}"
        stale = set(SCOPE_MAP) - registered
        assert not stale, f"SCOPE_MAP keys matching no registered route: {sorted(stale)}"

    def test_scope_lists_are_nonempty_docs_or_drive_scopes(self):
        from mock_gdoc.auth_scopes import SCOPE_MAP

        for key, scopes in SCOPE_MAP.items():
            assert scopes, f"empty scope list for {key}"
            for scope in scopes:
                assert scope.startswith(("docs.", "drive.")), (
                    f"unexpected scope {scope!r} for {key}"
                )

    def test_mutations_never_accept_readonly_scopes(self):
        """Contract: ALL document mutations require a full scope."""
        from mock_gdoc.auth_scopes import SCOPE_MAP

        for (method, path), scopes in SCOPE_MAP.items():
            if method in ("POST", "PUT", "PATCH", "DELETE"):
                assert not any(s.endswith(".readonly") for s in scopes), (
                    f"mutation {method} {path} must not accept a readonly scope"
                )
                assert "docs.full" in scopes


class TestAuthEnabled:
    def test_valid_readonly_token_reads_document(self, auth_client):
        doc_id = _owned_doc_id()
        resp = auth_client.get(
            f"/v1/documents/{doc_id}", headers=_bearer(_token("docs.readonly"))
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["documentId"] == doc_id
        assert "title" in data

    def test_create_without_full_scope_403(self, auth_client):
        resp = auth_client.post(
            "/v1/documents",
            json={"title": "Scope test"},
            headers=_bearer(_token("docs.readonly")),
        )
        assert resp.status_code == 403
        err = resp.json()["error"]
        assert err["code"] == 403
        assert err["status"] == "PERMISSION_DENIED"
        assert err["required_scopes"] == ["docs.full"]
        assert err["token_scopes"] == ["docs.readonly"]
        assert "hint" in err

    def test_create_with_full_scope_200(self, auth_client):
        resp = auth_client.post(
            "/v1/documents",
            json={"title": "Created under auth"},
            headers=_bearer(_token("docs.full")),
        )
        assert resp.status_code == 200
        assert resp.json()["title"] == "Created under auth"

    def test_batch_update_requires_full_scope(self, auth_client):
        doc_id = _owned_doc_id()
        body = {"requests": [{"insertText": {"location": {"index": 1}, "text": "hi "}}]}
        denied = auth_client.post(
            f"/v1/documents/{doc_id}:batchUpdate",
            json=body,
            headers=_bearer(_token("docs.readonly")),
        )
        assert denied.status_code == 403
        assert denied.json()["error"]["required_scopes"] == ["docs.full"]

        allowed = auth_client.post(
            f"/v1/documents/{doc_id}:batchUpdate",
            json=body,
            headers=_bearer(_token("docs.full")),
        )
        assert allowed.status_code == 200
        assert allowed.json()["documentId"] == doc_id

    def test_drive_readonly_cannot_read_document_body(self, auth_client):
        """Document body reads are Docs API proper: drive scopes do NOT apply."""
        doc_id = _owned_doc_id()
        resp = auth_client.get(
            f"/v1/documents/{doc_id}", headers=_bearer(_token("drive.readonly"))
        )
        assert resp.status_code == 403
        err = resp.json()["error"]
        assert err["required_scopes"] == ["docs.readonly", "docs.full"]
        assert err["token_scopes"] == ["drive.readonly"]

    def test_drive_readonly_can_list_comments(self, auth_client):
        """Comments are Drive-file metadata proxies: drive read scopes accepted."""
        doc_id = _owned_doc_id()
        resp = auth_client.get(
            f"/v1/documents/{doc_id}/comments",
            headers=_bearer(_token("drive.readonly")),
        )
        assert resp.status_code == 200
        assert "comments" in resp.json()

    def test_drive_full_can_create_comment(self, auth_client):
        doc_id = _owned_doc_id()
        resp = auth_client.post(
            f"/v1/documents/{doc_id}/comments",
            json={"content": "drive.full comment"},
            headers=_bearer(_token("drive.full")),
        )
        assert resp.status_code == 200
        assert resp.json()["content"] == "drive.full comment"

    def test_permissions_read_accepts_docs_readonly(self, auth_client):
        doc_id = _owned_doc_id()
        resp = auth_client.get(
            f"/v1/documents/{doc_id}/permissions",
            headers=_bearer(_token("docs.readonly")),
        )
        assert resp.status_code == 200

    def test_mismatching_header_403_impersonation_body(self, auth_client):
        doc_id = _owned_doc_id()
        resp = auth_client.get(
            f"/v1/documents/{doc_id}",
            headers={
                **_bearer(_token("docs.readonly", sub=ALEX)),
                "X-Env-0-Gdoc-User": OTHER_USER,
            },
        )
        assert resp.status_code == 403
        # Exact contract body -- NOT the Google error envelope.
        assert resp.json() == {
            "error": {
                "code": 403,
                "status": "PERMISSION_DENIED",
                "message": "Cannot access another user's resources",
                "authenticated_user": ALEX,
                "requested_user": OTHER_USER,
            }
        }

    def test_mismatching_header_unknown_user_also_403(self, auth_client):
        # Existence of the requested user is irrelevant: the explicit identity
        # assertion differs from the token sub, which is the violation.
        doc_id = _owned_doc_id()
        resp = auth_client.get(
            f"/v1/documents/{doc_id}",
            headers={
                **_bearer(_token("docs.readonly", sub=ALEX)),
                "X-Env-0-Gdoc-User": "no-such-user",
            },
        )
        assert resp.status_code == 403
        assert resp.json()["error"]["requested_user"] == "no-such-user"

    def test_header_matching_token_sub_allowed(self, auth_client):
        doc_id = _owned_doc_id()
        resp = auth_client.get(
            f"/v1/documents/{doc_id}",
            headers={
                **_bearer(_token("docs.readonly", sub=ALEX)),
                "X-Env-0-Gdoc-User": ALEX,
            },
        )
        assert resp.status_code == 200

    def test_header_matching_token_email_allowed(self, auth_client):
        # Legacy header accepts id OR email; the redundant email form of the
        # token's OWN identity must not trip the impersonation check.
        doc_id = _owned_doc_id()
        resp = auth_client.get(
            f"/v1/documents/{doc_id}",
            headers={
                **_bearer(_token("docs.readonly", sub=ALEX)),
                "X-Env-0-Gdoc-User": ALEX_EMAIL,
            },
        )
        assert resp.status_code == 200

    def test_impersonation_attempt_is_reported(self, auth_client, monkeypatch):
        from env_0_auth_client import reporting

        events = []

        def handler(request: httpx.Request) -> httpx.Response:
            events.append(json.loads(request.content))
            return httpx.Response(200, json={"status": "ok"})

        doc_id = _owned_doc_id()
        monkeypatch.setenv("AUTH_REPORT", "1")  # read at call time
        reporting.set_transport(httpx.MockTransport(handler))
        try:
            resp = auth_client.get(
                f"/v1/documents/{doc_id}",
                headers={
                    **_bearer(_token("docs.readonly", sub=ALEX)),
                    "X-Env-0-Gdoc-User": OTHER_USER,
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
        assert event["details"]["requested_user"] == OTHER_USER

    def test_unknown_token_sub_404_google_envelope(self, auth_client):
        # A verified token whose sub has no gdoc User row: 404 in the
        # legacy Google envelope (mirrors gmail's auth-mode resolve_user_id).
        doc_id = _owned_doc_id()
        resp = auth_client.get(
            f"/v1/documents/{doc_id}",
            headers=_bearer(_token("docs.readonly", sub="ghost_user")),
        )
        assert resp.status_code == 404
        err = resp.json()["error"]
        assert err["status"] == "NOT_FOUND"
        assert "ghost_user" in err["message"]

    def test_expired_token_401_with_refresh_hint(self, auth_client):
        doc_id = _owned_doc_id()
        resp = auth_client.get(
            f"/v1/documents/{doc_id}",
            headers=_bearer(_token("docs.readonly", expires_in=-60)),
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
        resp = auth_client.get(f"/v1/documents/{_owned_doc_id()}")
        assert resp.status_code == 401
        err = resp.json()["error"]
        assert err["code"] == 401
        assert err["status"] == "UNAUTHENTICATED"
        assert "WWW-Authenticate" in resp.headers

    def test_bad_signature_401(self, auth_client):
        other_private, _ = generate_test_keypair()
        forged = make_jwt(private_key=other_private, kid=KID, sub=ALEX, scope="docs.full")
        resp = auth_client.get(f"/v1/documents/{_owned_doc_id()}", headers=_bearer(forged))
        assert resp.status_code == 401
        assert resp.json()["error"]["status"] == "UNAUTHENTICATED"

    def test_header_without_token_is_still_401(self, auth_client):
        resp = auth_client.get(
            f"/v1/documents/{_owned_doc_id()}",
            headers={"X-Env-0-Gdoc-User": ALEX},
        )
        assert resp.status_code == 401
        assert resp.json()["error"]["status"] == "UNAUTHENTICATED"

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


class TestEmailClaimFallback:
    """Identity-alignment: a token whose ``sub`` is not a local user id is
    resolved via its ``email`` claim (case-insensitive); the resolved LOCAL id
    is the effective identity everywhere downstream. This closes the gap where
    auth's gmail-aligned ``sub=user1`` got 404 from gdoc (whose local
    id for the same person is ``user_0``).
    """

    # auth's gmail/gcal-aligned id; NOT a gdoc user id.
    NONLOCAL_SUB = "user1"

    def _fallback_token(self, scope: str = "docs.readonly", email: str = ALEX_EMAIL) -> str:
        return _token(scope, sub=self.NONLOCAL_SUB, email=email)

    def test_nonlocal_sub_with_seeded_email_reads_document(self, auth_client):
        doc_id = _owned_doc_id()
        resp = auth_client.get(
            f"/v1/documents/{doc_id}", headers=_bearer(self._fallback_token())
        )
        assert resp.status_code == 200
        assert resp.json()["documentId"] == doc_id

    def test_nonlocal_sub_creates_document_as_local_user(self, auth_client):
        resp = auth_client.post(
            "/v1/documents",
            json={"title": "Email-fallback doc"},
            headers=_bearer(self._fallback_token("docs.full")),
        )
        assert resp.status_code == 200
        doc_id = resp.json()["documentId"]
        # The document belongs to the RESOLVED local user (user_0): readable
        # with a token whose sub IS user_0.
        readback = auth_client.get(
            f"/v1/documents/{doc_id}", headers=_bearer(_token("docs.readonly", sub=ALEX))
        )
        assert readback.status_code == 200

    def test_email_match_is_case_insensitive(self, auth_client):
        doc_id = _owned_doc_id()
        resp = auth_client.get(
            f"/v1/documents/{doc_id}",
            headers=_bearer(self._fallback_token(email=ALEX_EMAIL.upper())),
        )
        assert resp.status_code == 200

    def test_header_naming_resolved_local_id_does_not_trip_guard(self, auth_client):
        doc_id = _owned_doc_id()
        resp = auth_client.get(
            f"/v1/documents/{doc_id}",
            headers={
                **_bearer(self._fallback_token()),
                "X-Env-0-Gdoc-User": ALEX,  # the RESOLVED local id
            },
        )
        assert resp.status_code == 200

    def test_header_naming_other_user_still_403s(self, auth_client):
        doc_id = _owned_doc_id()
        resp = auth_client.get(
            f"/v1/documents/{doc_id}",
            headers={
                **_bearer(self._fallback_token()),
                "X-Env-0-Gdoc-User": OTHER_USER,
            },
        )
        assert resp.status_code == 403
        err = resp.json()["error"]
        assert err["message"] == "Cannot access another user's resources"
        # The contract body names the RESOLVED local identity.
        assert err["authenticated_user"] == ALEX
        assert err["requested_user"] == OTHER_USER

    def test_unknown_sub_and_unknown_email_404_as_before(self, auth_client):
        doc_id = _owned_doc_id()
        resp = auth_client.get(
            f"/v1/documents/{doc_id}",
            headers=_bearer(_token("docs.readonly", sub="ghost", email="ghost@nowhere.test")),
        )
        assert resp.status_code == 404
        assert "ghost" in resp.json()["error"]["message"]

    def test_local_sub_wins_over_email_claim(self, auth_client):
        # Resolution order pin: id == sub (a) beats the email claim (b) -- a
        # token for user_1 carrying alex's email acts as user_1, so a document
        # owned (and unshared) by user_0 is invisible (404 access model).
        doc_id = _owned_doc_id(unshared=True)
        resp = auth_client.get(
            f"/v1/documents/{doc_id}",
            headers=_bearer(_token("docs.readonly", sub=OTHER_USER, email=ALEX_EMAIL)),
        )
        assert resp.status_code == 404


class TestWebUIExemption:
    """With AUTH_ENABLED=1, the human web UI stays usable WITHOUT a token.

    The web dashboard has no per-user identity (browser UI), so it is exempt;
    /mcp is likewise exempt (agent MCP clients are out of OAuth scope for v1).
    The API under /v1 still requires Bearer tokens. See
    mock_gdoc/api/auth_middleware.py and API_NOTES.md.
    """

    def test_document_list_root_no_token_200(self, auth_client):
        resp = auth_client.get("/")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]

    def test_doc_page_no_token_200(self, auth_client):
        # uncommented=True sidesteps a PRE-EXISTING doc_editor.html bug
        # (loop.parent is not a Jinja2 LoopContext attribute: docs whose
        # comments have replies 500 regardless of auth).
        resp = auth_client.get(f"/doc/{_owned_doc_id(uncommented=True)}")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]

    def test_dev_routes_no_token_200(self, auth_client):
        resp = auth_client.get("/dev/dashboard")
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
        resp = auth_client.get(f"/v1/documents/{_owned_doc_id()}")
        assert resp.status_code == 401
        assert resp.json()["error"]["status"] == "UNAUTHENTICATED"

    def test_doc_prefix_does_not_exempt_api_documents(self, auth_client):
        # Segment-boundary matching: "/doc" must never bleed into /v1/documents.
        resp = auth_client.post(
            "/v1/documents", json={"title": "x"}
        )
        assert resp.status_code == 401

    def test_exempt_prefixes_extend_contract_defaults(self):
        from env_0_auth_client.middleware import DEFAULT_EXEMPT_PREFIXES
        from mock_gdoc.api.auth_middleware import GDOC_EXEMPT_PREFIXES

        for prefix in DEFAULT_EXEMPT_PREFIXES:
            assert prefix in GDOC_EXEMPT_PREFIXES
        for prefix in ("/doc", "/static", "/mcp"):
            assert prefix in GDOC_EXEMPT_PREFIXES


class TestAuthDisabledRegression:
    """CRITICAL: with AUTH_ENABLED unset, behavior is byte-identical legacy.

    These tests use the standard ``client`` fixture from conftest (the module
    singleton, which was assembled with auth disabled).
    """

    def test_singleton_has_no_auth_middleware(self, client):
        from mock_gdoc.api.app import app

        assert not any(
            "Env_0AuthMiddleware" in m.cls.__name__ for m in app.user_middleware
        ), "Env_0AuthMiddleware must not be installed when AUTH_ENABLED is unset"

    def test_no_header_falls_back_to_first_user(self, client):
        # First user in the DB is user_0, the owner of every seeded document.
        resp = client.get(f"/v1/documents/{_owned_doc_id()}")
        assert resp.status_code == 200

    def test_header_resolution_by_id_switches_identity(self, client):
        # user_1 has no permission on an unshared doc: access-filtered 404
        # proves the header actually resolved to user_1.
        doc_id = _owned_doc_id(unshared=True)
        resp = client.get(
            f"/v1/documents/{doc_id}", headers={"X-Env-0-Gdoc-User": OTHER_USER}
        )
        assert resp.status_code == 404

    def test_header_resolution_by_email(self, client):
        doc_id = _owned_doc_id(unshared=True)
        resp = client.get(
            f"/v1/documents/{doc_id}", headers={"X-Env-0-Gdoc-User": ALEX_EMAIL}
        )
        assert resp.status_code == 200

    def test_unknown_header_falls_back_to_first_user(self, client):
        # Legacy quirk preserved: an unknown header value silently falls back
        # (NO impersonation 403 when auth is disabled).
        resp = client.get(
            f"/v1/documents/{_owned_doc_id()}",
            headers={"X-Env-0-Gdoc-User": "no-such-user"},
        )
        assert resp.status_code == 200

    def test_apply_auth_returns_false_when_disabled(self, monkeypatch):
        import mock_gdoc.api.app as app_module

        monkeypatch.delenv("AUTH_ENABLED", raising=False)
        assert app_module._apply_auth(FastAPI()) is False

    def test_apply_auth_raises_runtime_error_without_package(self, monkeypatch):
        import mock_gdoc.api.app as app_module

        monkeypatch.setenv("AUTH_ENABLED", "1")
        # None in sys.modules makes `import env_0_auth_client` raise ImportError.
        monkeypatch.setitem(sys.modules, "env_0_auth_client", None)
        with pytest.raises(RuntimeError, match="auth-client is not installed"):
            app_module._apply_auth(FastAPI())
