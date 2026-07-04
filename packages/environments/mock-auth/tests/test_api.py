"""Functional tests for auth — full OAuth/OIDC flows, admin suite, scenarios."""

from __future__ import annotations

import jwt as pyjwt
import pytest

from mock_auth.config import get_issuer
from mock_auth.models import reset_engine
from mock_auth.tokens import reset_token_rng

from .conftest import (
    ALICE,
    BOB,
    DEMO_PASSWORD,
    GWS_REDIRECT,
    OPENCLAW_REDIRECT,
    authorize_params,
    exchange_code,
    extract_query,
    full_auth_code_flow,
    get_code_via_auto_consent,
    login,
    pkce_pair,
)


def audit_events(client, **params):
    return client.get("/_admin/audit_log", params=params).json()["events"]


# ---------------------------------------------------------------------------
class TestHealth:
    def test_health(self, client):
        assert client.get("/health").json() == {"status": "ok"}


class TestDiscovery:
    def test_discovery_endpoints(self, client):
        doc = client.get("/.well-known/openid-configuration").json()
        issuer = doc["issuer"]
        assert doc["authorization_endpoint"] == f"{issuer}/o/oauth2/v2/auth"
        assert doc["token_endpoint"] == f"{issuer}/oauth2/token"
        assert doc["userinfo_endpoint"] == f"{issuer}/oauth2/v2/userinfo"
        assert doc["jwks_uri"] == f"{issuer}/oauth2/v3/certs"
        assert doc["device_authorization_endpoint"] == f"{issuer}/oauth2/device/code"
        assert "revocation_endpoint" in doc
        assert "introspection_endpoint" in doc

    def test_discovery_capabilities(self, client):
        doc = client.get("/.well-known/openid-configuration").json()
        assert doc["response_types_supported"] == ["code"]
        assert doc["id_token_signing_alg_values_supported"] == ["RS256"]
        assert set(doc["code_challenge_methods_supported"]) == {"S256", "plain"}
        assert "authorization_code" in doc["grant_types_supported"]
        assert "client_credentials" in doc["grant_types_supported"]
        assert "urn:ietf:params:oauth:grant-type:device_code" in doc["grant_types_supported"]

    def test_discovery_scopes(self, client):
        doc = client.get("/.well-known/openid-configuration").json()
        for scope in ("openid", "email", "profile", "gmail.readonly", "gmail.full",
                      "calendar.readonly", "drive.full", "docs.readonly", "chat:write"):
            assert scope in doc["scopes_supported"]

    def test_issuer_default(self, client):
        doc = client.get("/.well-known/openid-configuration").json()
        assert doc["issuer"] == "http://localhost:9000"


class TestJWKS:
    def test_jwks_shape(self, client):
        keys = client.get("/oauth2/v3/certs").json()["keys"]
        assert len(keys) == 1
        key = keys[0]
        assert key["kid"] == "env-0-auth-key-001"
        assert key["kty"] == "RSA"
        assert key["alg"] == "RS256"
        assert key["use"] == "sig"
        assert key["n"] and key["e"]

    def test_jwt_verifies_against_jwks(self, client):
        tok = full_auth_code_flow(client)
        jwks = client.get("/oauth2/v3/certs").json()
        header = pyjwt.get_unverified_header(tok["access_token"])
        jwk = next(k for k in jwks["keys"] if k["kid"] == header["kid"])
        public_key = pyjwt.algorithms.RSAAlgorithm.from_jwk(jwk)
        claims = pyjwt.decode(tok["access_token"], public_key, algorithms=["RS256"],
                              options={"verify_aud": False})
        assert claims["sub"] == ALICE["id"]

    def test_rotate_key_adds_to_jwks(self, client):
        r = client.post("/_admin/rotate_key")
        assert r.json()["status"] == "ok"
        new_kid = r.json()["kid"]
        kids = [k["kid"] for k in client.get("/oauth2/v3/certs").json()["keys"]]
        assert "env-0-auth-key-001" in kids  # old key kept for verification
        assert new_kid in kids

    def test_old_tokens_verify_after_rotation(self, client):
        tok = full_auth_code_flow(client)
        client.post("/_admin/rotate_key")
        r = client.get("/oauth2/v2/userinfo",
                       headers={"Authorization": f"Bearer {tok['access_token']}"})
        assert r.status_code == 200

    def test_new_tokens_signed_with_new_key(self, client):
        new_kid = client.post("/_admin/rotate_key").json()["kid"]
        tok = client.post("/_admin/issue_token", json={
            "client_id": "gws-cli", "user_id": "user1", "scopes": ["email"]}).json()
        header = pyjwt.get_unverified_header(tok["access_token"])
        assert header["kid"] == new_kid


# ---------------------------------------------------------------------------
class TestWebLogin:
    def test_login_sets_session_cookie(self, client):
        r = login(client)
        assert r.status_code == 303
        assert "mock_auth_session" in r.cookies

    def test_login_bad_password(self, client):
        r = client.post("/web/login", data={"email": ALICE["email"], "password": "nope"})
        assert r.status_code == 401
        assert "Invalid email or password" in r.text

    def test_login_unknown_user(self, client):
        r = client.post("/web/login", data={"email": "ghost@nowhere", "password": "x"})
        assert r.status_code == 401

    def test_home_lists_users_and_clients(self, client):
        r = client.get("/")
        assert r.status_code == 200
        assert ALICE["email"] in r.text
        assert "gws-cli" in r.text

    def test_logout_clears_session(self, client):
        login(client)
        client.post("/web/logout", follow_redirects=False)
        # Consent flow should now render the login form again
        verifier, challenge = pkce_pair()
        r = client.get("/o/oauth2/v2/auth",
                       params=authorize_params(challenge=challenge), follow_redirects=False)
        assert r.status_code == 200
        assert 'action="/web/login"' in r.text


# ---------------------------------------------------------------------------
class TestWebSSOAssertion:
    """POST /web/login mints a signed identity assertion for cross-origin
    `next` targets (web-session SSO hand-off; W7). Same-origin/relative `next`
    is byte-identical to before."""

    GMAIL_CALLBACK = "http://gmail.test/web/auth/callback?next=/"

    def _sso_login(self, client):
        return client.post("/web/login", data={
            "email": ALICE["email"], "password": DEMO_PASSWORD,
            "next": self.GMAIL_CALLBACK,
        }, follow_redirects=False)

    def test_cross_origin_next_appends_assertion(self, client):
        r = self._sso_login(client)
        assert r.status_code == 303
        loc = r.headers["location"]
        assert loc.startswith("http://gmail.test/web/auth/callback?")
        qs = extract_query(loc)
        assert qs["next"] == "/"          # original target preserved
        assert "env_0_identity" in qs       # assertion handed off
        assert "mock_auth_session" in r.cookies  # session still established

    def test_assertion_verifies_against_jwks(self, client):
        qs = extract_query(self._sso_login(client).headers["location"])
        token = qs["env_0_identity"]
        header = pyjwt.get_unverified_header(token)
        jwks = client.get("/oauth2/v3/certs").json()["keys"]
        jwk = next(k for k in jwks if k["kid"] == header["kid"])
        key = pyjwt.PyJWK.from_dict(jwk).key
        claims = pyjwt.decode(token, key=key, algorithms=["RS256"],
                              options={"verify_aud": False})
        assert claims["sub"] == "user1"
        assert claims["email"] == ALICE["email"]
        assert claims["purpose"] == "web_sso"
        assert claims["iss"] == get_issuer()

    def test_assertion_logged_to_audit(self, client):
        self._sso_login(client)
        events = client.get("/_admin/audit_log",
                            params={"event_type": "web_sso_assertion_issued"}).json()["events"]
        assert events and events[0]["user_id"] == "user1"

    def test_relative_next_unchanged(self, client):
        r = client.post("/web/login", data={
            "email": ALICE["email"], "password": DEMO_PASSWORD,
            "next": "/device?user_code=ABCD-EFGH",
        }, follow_redirects=False)
        assert r.status_code == 303
        assert r.headers["location"] == "/device?user_code=ABCD-EFGH"
        assert "env_0_identity" not in r.headers["location"]

    def test_same_origin_absolute_next_unchanged(self, client):
        # Same host as the request -> auth's own page, not a hand-off.
        target = "http://testserver/o/oauth2/v2/auth?client_id=gws-cli"
        r = client.post("/web/login", data={
            "email": ALICE["email"], "password": DEMO_PASSWORD, "next": target,
        }, follow_redirects=False)
        assert r.status_code == 303
        assert r.headers["location"] == target
        assert "env_0_identity" not in r.headers["location"]


# ---------------------------------------------------------------------------
class TestAuthorizationEndpoint:
    def test_auto_consent_redirects_with_code_and_state(self, client):
        client.post("/_admin/auto_consent", json={
            "client_id": "gws-cli", "user_id": "user1",
            "scopes": ["openid", "email", "gmail.readonly"]})
        _, challenge = pkce_pair()
        r = client.get("/o/oauth2/v2/auth",
                       params=authorize_params(challenge=challenge,
                                               login_hint=ALICE["email"]),
                       follow_redirects=False)
        assert r.status_code == 302
        qs = extract_query(r.headers["location"])
        assert qs["state"] == "st-123"
        assert qs["code"]

    def test_auto_consent_superset_covers_subset(self, client):
        client.post("/_admin/auto_consent", json={
            "client_id": "gws-cli", "user_id": "user1",
            "scopes": ["openid", "email", "gmail.readonly", "gmail.send"]})
        _, challenge = pkce_pair()
        r = client.get("/o/oauth2/v2/auth",
                       params=authorize_params("openid gmail.readonly",
                                               challenge=challenge,
                                               login_hint="user1"),
                       follow_redirects=False)
        assert r.status_code == 302
        assert "code" in extract_query(r.headers["location"])

    def test_consent_screen_rendered_with_session(self, client):
        login(client)
        _, challenge = pkce_pair()
        r = client.get("/o/oauth2/v2/auth",
                       params=authorize_params(challenge=challenge), follow_redirects=False)
        assert r.status_code == 200
        assert "Google Workspace CLI" in r.text
        assert "gmail.readonly" in r.text
        assert 'action="/o/oauth2/v2/auth/callback"' in r.text

    def test_consent_allow_issues_code(self, client):
        login(client)
        verifier, challenge = pkce_pair()
        r = client.post("/o/oauth2/v2/auth/callback", data={
            "decision": "allow", "client_id": "gws-cli",
            "redirect_uri": GWS_REDIRECT, "scope": "openid email gmail.readonly",
            "state": "s1", "code_challenge": challenge, "code_challenge_method": "S256",
        }, follow_redirects=False)
        assert r.status_code == 302
        qs = extract_query(r.headers["location"])
        tok = exchange_code(client, qs["code"], verifier=verifier)
        assert tok["scope"] == "openid email gmail.readonly"
        # Consent now recorded — second authorize skips HTML
        r2 = client.get("/o/oauth2/v2/auth",
                        params=authorize_params(challenge=challenge), follow_redirects=False)
        assert r2.status_code == 302

    def test_consent_deny_redirects_access_denied(self, client):
        login(client)
        r = client.post("/o/oauth2/v2/auth/callback", data={
            "decision": "deny", "client_id": "gws-cli",
            "redirect_uri": GWS_REDIRECT, "scope": "gmail.full", "state": "s2",
        }, follow_redirects=False)
        assert r.status_code == 302
        qs = extract_query(r.headers["location"])
        assert qs["error"] == "access_denied"
        assert qs["state"] == "s2"
        events = audit_events(client, event_type="authorization_deny")
        assert events and events[0]["client_id"] == "gws-cli"

    def test_callback_without_session_is_oauth_error(self, client):
        r = client.post("/o/oauth2/v2/auth/callback", data={
            "decision": "allow", "client_id": "gws-cli",
            "redirect_uri": GWS_REDIRECT, "scope": "email",
        })
        assert r.status_code == 400
        body = r.json()
        assert body["error"] == "interaction_required"
        assert "error_description" in body and "hint" in body

    def test_no_session_no_consent_renders_login_form(self, client):
        _, challenge = pkce_pair()
        r = client.get("/o/oauth2/v2/auth",
                       params=authorize_params(challenge=challenge), follow_redirects=False)
        assert r.status_code == 200
        assert 'action="/web/login"' in r.text

    def test_auto_consent_without_login_hint_interaction_required(self, client):
        client.post("/_admin/auto_consent", json={
            "client_id": "gws-cli", "user_id": "user1", "scopes": ["email"]})
        _, challenge = pkce_pair()
        r = client.get("/o/oauth2/v2/auth",
                       params=authorize_params("email", challenge=challenge),
                       follow_redirects=False)
        assert r.status_code == 302
        assert extract_query(r.headers["location"])["error"] == "interaction_required"

    def test_unknown_client_is_rfc_error_not_envelope(self, client):
        r = client.get("/o/oauth2/v2/auth", params=authorize_params(client_id="nope"),
                       follow_redirects=False)
        assert r.status_code == 400
        body = r.json()
        assert body["error"] == "invalid_client"  # flat RFC 6749 string, not an object
        assert isinstance(body["error"], str)
        assert "error_description" in body

    def test_unregistered_redirect_uri_rejected(self, client):
        r = client.get("/o/oauth2/v2/auth",
                       params=authorize_params(redirect_uri="http://evil.example/cb"),
                       follow_redirects=False)
        assert r.status_code == 400
        assert r.json()["error"] == "invalid_request"

    def test_bad_response_type_redirects_error(self, client):
        params = authorize_params(challenge=pkce_pair()[1])
        params["response_type"] = "token"
        r = client.get("/o/oauth2/v2/auth", params=params, follow_redirects=False)
        assert r.status_code == 302
        assert extract_query(r.headers["location"])["error"] == "unsupported_response_type"

    def test_scope_escalation_logged_and_rejected(self, client):
        # old-app style: gws-cli allowed everything, so use a restricted client
        client.post("/_admin/seed", json={"scenario": "overpermissioned_apps"})
        r = client.get("/o/oauth2/v2/auth", params=authorize_params(
            "gmail.full", client_id="meeting-notes",
            redirect_uri="http://localhost:7000/meeting-notes/callback"),
            follow_redirects=False)
        assert r.status_code == 302
        assert extract_query(r.headers["location"])["error"] == "invalid_scope"
        events = audit_events(client, event_type="scope_escalation_attempt")
        assert any(e["client_id"] == "meeting-notes" for e in events)

    def test_public_client_requires_pkce(self, client):
        r = client.get("/o/oauth2/v2/auth", params=authorize_params(),  # no challenge
                       follow_redirects=False)
        assert r.status_code == 302
        qs = extract_query(r.headers["location"])
        assert qs["error"] == "invalid_request"
        assert "code_challenge" in qs["error_description"]

    def test_authorization_request_audited(self, client):
        get_code_via_auto_consent(client)
        events = audit_events(client, event_type="authorization_request")
        assert events
        assert events[0]["client_id"] == "gws-cli"


# ---------------------------------------------------------------------------
class TestTokenEndpointAuthCode:
    def test_token_response_shape(self, client):
        tok = full_auth_code_flow(client)
        assert set(tok.keys()) == {"access_token", "expires_in", "scope", "token_type",
                                   "refresh_token", "id_token"}
        assert tok["token_type"] == "Bearer"
        assert tok["expires_in"] == 3600

    def test_jwt_header_and_claims(self, client):
        tok = full_auth_code_flow(client)
        header = pyjwt.get_unverified_header(tok["access_token"])
        assert header["alg"] == "RS256"
        assert header["typ"] == "JWT"
        assert header["kid"] == "env-0-auth-key-001"
        claims = pyjwt.decode(tok["access_token"], options={"verify_signature": False})
        assert claims["iss"] == "http://localhost:9000"
        assert claims["sub"] == "user1"
        assert claims["aud"] == "gws-cli"
        assert claims["client_id"] == "gws-cli"
        assert claims["email"] == ALICE["email"]
        assert claims["scope"] == "openid email gmail.readonly"
        assert isinstance(claims["exp"], int) and isinstance(claims["iat"], int)

    def test_jti_and_refresh_token_formats(self, client):
        tok = full_auth_code_flow(client)
        claims = pyjwt.decode(tok["access_token"], options={"verify_signature": False})
        jti = claims["jti"]
        assert jti.startswith("tok_") and len(jti) == 4 + 24
        assert int(jti[4:], 16) >= 0
        rt = tok["refresh_token"]
        assert rt.startswith("rt_") and len(rt) == 3 + 48

    def test_id_token_issued_with_openid(self, client):
        tok = full_auth_code_flow(client, scope="openid email profile")
        idc = pyjwt.decode(tok["id_token"], options={"verify_signature": False},
                           audience="gws-cli")
        assert idc["sub"] == "user1"
        assert idc["email"] == ALICE["email"]
        assert idc["email_verified"] is True
        assert idc["name"] == ALICE["name"]
        assert "at_hash" not in idc  # pinned: omitted

    def test_no_id_token_without_openid(self, client):
        tok = full_auth_code_flow(client, scope="gmail.readonly")
        assert "id_token" not in tok

    def test_nonce_round_trips_into_id_token(self, client):
        verifier, challenge = pkce_pair()
        client.post("/_admin/auto_consent", json={
            "client_id": "gws-cli", "user_id": "user1", "scopes": ["openid"]})
        params = authorize_params("openid", challenge=challenge,
                                  login_hint=ALICE["email"], nonce="n-0S6_WzA2Mj")
        r = client.get("/o/oauth2/v2/auth", params=params, follow_redirects=False)
        code = extract_query(r.headers["location"])["code"]
        tok = exchange_code(client, code, verifier=verifier)
        idc = pyjwt.decode(tok["id_token"], options={"verify_signature": False},
                           audience="gws-cli")
        assert idc["nonce"] == "n-0S6_WzA2Mj"

    def test_code_single_use(self, client):
        verifier, challenge = pkce_pair()
        code = get_code_via_auto_consent(client, challenge=challenge)
        exchange_code(client, code, verifier=verifier)
        r = client.post("/oauth2/token", data={
            "grant_type": "authorization_code", "code": code,
            "redirect_uri": GWS_REDIRECT, "client_id": "gws-cli",
            "code_verifier": verifier})
        assert r.status_code == 400
        assert r.json()["error"] == "invalid_grant"

    def test_bad_pkce_verifier_fails_and_audits(self, client):
        _, challenge = pkce_pair()
        code = get_code_via_auto_consent(client, challenge=challenge)
        r = client.post("/oauth2/token", data={
            "grant_type": "authorization_code", "code": code,
            "redirect_uri": GWS_REDIRECT, "client_id": "gws-cli",
            "code_verifier": "totally-wrong-verifier-value-123456789012345"})
        assert r.status_code == 400
        assert r.json()["error"] == "invalid_grant"
        assert audit_events(client, event_type="pkce_failure")

    def test_pkce_plain_method(self, client):
        client.post("/_admin/auto_consent", json={
            "client_id": "gws-cli", "user_id": "user1", "scopes": ["email"]})
        plain = "plain-verifier-value-0123456789-0123456789-0123"
        params = authorize_params("email", challenge=plain, method="plain",
                                  login_hint=ALICE["email"])
        r = client.get("/o/oauth2/v2/auth", params=params, follow_redirects=False)
        code = extract_query(r.headers["location"])["code"]
        tok = exchange_code(client, code, verifier=plain)
        assert tok["scope"] == "email"

    def test_redirect_uri_mismatch(self, client):
        verifier, challenge = pkce_pair()
        code = get_code_via_auto_consent(client, challenge=challenge)
        r = client.post("/oauth2/token", data={
            "grant_type": "authorization_code", "code": code,
            "redirect_uri": "http://localhost:8085/", "client_id": "gws-cli",
            "code_verifier": verifier})
        assert r.status_code == 400
        assert r.json()["error"] == "invalid_grant"

    def test_code_bound_to_client(self, client):
        verifier, challenge = pkce_pair()
        code = get_code_via_auto_consent(client, challenge=challenge)
        r = client.post("/oauth2/token", data={
            "grant_type": "authorization_code", "code": code,
            "redirect_uri": GWS_REDIRECT, "client_id": "openclaw-agent",
            "client_secret": "openclaw-secret", "code_verifier": verifier})
        assert r.status_code == 400
        assert r.json()["error"] == "invalid_grant"

    def test_confidential_client_secret_post(self, client):
        client.post("/_admin/auto_consent", json={
            "client_id": "openclaw-agent", "user_id": "user1", "scopes": ["gmail.send"]})
        r = client.get("/o/oauth2/v2/auth", params=authorize_params(
            "gmail.send", client_id="openclaw-agent", redirect_uri=OPENCLAW_REDIRECT,
            login_hint=ALICE["email"]), follow_redirects=False)
        code = extract_query(r.headers["location"])["code"]
        tok = exchange_code(client, code, client_id="openclaw-agent",
                            client_secret="openclaw-secret",
                            redirect_uri=OPENCLAW_REDIRECT)
        assert tok["scope"] == "gmail.send"

    def test_confidential_client_secret_basic(self, client):
        import base64
        client.post("/_admin/auto_consent", json={
            "client_id": "openclaw-agent", "user_id": "user1", "scopes": ["gmail.send"]})
        r = client.get("/o/oauth2/v2/auth", params=authorize_params(
            "gmail.send", client_id="openclaw-agent", redirect_uri=OPENCLAW_REDIRECT,
            login_hint=ALICE["email"]), follow_redirects=False)
        code = extract_query(r.headers["location"])["code"]
        basic = base64.b64encode(b"openclaw-agent:openclaw-secret").decode()
        r = client.post("/oauth2/token", data={
            "grant_type": "authorization_code", "code": code,
            "redirect_uri": OPENCLAW_REDIRECT,
        }, headers={"Authorization": f"Basic {basic}"})
        assert r.status_code == 200

    def test_wrong_client_secret_401_and_audited(self, client):
        r = client.post("/oauth2/token", data={
            "grant_type": "client_credentials", "client_id": "openclaw-agent",
            "client_secret": "wrong", "scope": "gmail.readonly"})
        assert r.status_code == 401
        assert r.json()["error"] == "invalid_client"
        assert audit_events(client, event_type="invalid_client")


class TestTokenEndpointGeneric:
    def test_json_body_rejected(self, client):
        r = client.post("/oauth2/token", json={"grant_type": "client_credentials"})
        assert r.status_code == 400
        assert r.json()["error"] == "invalid_request"
        assert "form" in r.json()["error_description"].lower()

    def test_missing_grant_type(self, client):
        r = client.post("/oauth2/token", data={"client_id": "gws-cli"})
        assert r.status_code == 400
        assert r.json()["error"] == "invalid_request"

    def test_unknown_grant_type(self, client):
        r = client.post("/oauth2/token", data={
            "grant_type": "password", "client_id": "gws-cli"})
        assert r.status_code == 400
        assert r.json()["error"] in ("unsupported_grant_type", "unauthorized_client")

    def test_grant_not_allowed_for_client(self, client):
        # gws-cli (public) has no client_credentials in grant_types
        r = client.post("/oauth2/token", data={
            "grant_type": "client_credentials", "client_id": "gws-cli",
            "scope": "gmail.readonly"})
        assert r.status_code == 400
        assert r.json()["error"] == "unauthorized_client"

    def test_error_shape_has_hint(self, client):
        r = client.post("/oauth2/token", data={"grant_type": "authorization_code",
                                               "client_id": "gws-cli"})
        body = r.json()
        assert set(body.keys()) == {"error", "error_description", "hint"}


# ---------------------------------------------------------------------------
class TestRefreshRotation:
    def test_refresh_rotates_token(self, client):
        tok = full_auth_code_flow(client)
        r = client.post("/oauth2/token", data={
            "grant_type": "refresh_token", "refresh_token": tok["refresh_token"],
            "client_id": "gws-cli"})
        assert r.status_code == 200
        new = r.json()
        assert new["refresh_token"] != tok["refresh_token"]
        assert new["access_token"] != tok["access_token"]
        assert audit_events(client, event_type="token_refreshed")

    def test_reuse_detection_revokes_family(self, client):
        tok = full_auth_code_flow(client)
        r1 = client.post("/oauth2/token", data={
            "grant_type": "refresh_token", "refresh_token": tok["refresh_token"],
            "client_id": "gws-cli"})
        rotated = r1.json()["refresh_token"]
        # Reuse the OLD token => reuse detected, entire family revoked
        r2 = client.post("/oauth2/token", data={
            "grant_type": "refresh_token", "refresh_token": tok["refresh_token"],
            "client_id": "gws-cli"})
        assert r2.status_code == 400
        assert r2.json()["error"] == "invalid_grant"
        assert "reuse" in r2.json()["error_description"].lower()
        # The rotated successor is dead too
        r3 = client.post("/oauth2/token", data={
            "grant_type": "refresh_token", "refresh_token": rotated,
            "client_id": "gws-cli"})
        assert r3.status_code == 400
        # Audit: token_revoked with reuse_detected details
        events = audit_events(client, event_type="token_revoked")
        details = [e["details"] for e in events if e["details"]]
        assert any(d.get("reason") == "reuse_detected" and
                   d.get("event_type") == "refresh_reuse_detected" for d in details)

    def test_refresh_downscope(self, client):
        tok = full_auth_code_flow(client, scope="openid email gmail.readonly")
        r = client.post("/oauth2/token", data={
            "grant_type": "refresh_token", "refresh_token": tok["refresh_token"],
            "client_id": "gws-cli", "scope": "email"})
        assert r.status_code == 200
        assert r.json()["scope"] == "email"

    def test_refresh_upscope_rejected(self, client):
        tok = full_auth_code_flow(client, scope="email")
        r = client.post("/oauth2/token", data={
            "grant_type": "refresh_token", "refresh_token": tok["refresh_token"],
            "client_id": "gws-cli", "scope": "email gmail.full"})
        assert r.status_code == 400
        assert r.json()["error"] == "invalid_scope"
        assert audit_events(client, event_type="scope_escalation_attempt")

    def test_unknown_refresh_token(self, client):
        r = client.post("/oauth2/token", data={
            "grant_type": "refresh_token", "refresh_token": "rt_" + "0" * 48,
            "client_id": "gws-cli"})
        assert r.status_code == 400
        assert r.json()["error"] == "invalid_grant"


# ---------------------------------------------------------------------------
class TestClientCredentials:
    def test_service_token_without_subject(self, client):
        r = client.post("/oauth2/token", data={
            "grant_type": "client_credentials", "client_id": "openclaw-agent",
            "client_secret": "openclaw-secret", "scope": "gmail.readonly"})
        assert r.status_code == 200
        tok = r.json()
        assert "refresh_token" not in tok
        claims = pyjwt.decode(tok["access_token"], options={"verify_signature": False})
        assert claims["sub"] == "openclaw-agent"
        assert "act" not in claims

    def test_subject_impersonation_sets_act_claim(self, client):
        r = client.post("/oauth2/token", data={
            "grant_type": "client_credentials", "client_id": "openclaw-agent",
            "client_secret": "openclaw-secret", "scope": "gmail.send",
            "subject": "user1"})
        assert r.status_code == 200
        claims = pyjwt.decode(r.json()["access_token"],
                              options={"verify_signature": False})
        assert claims["sub"] == "user1"
        assert claims["email"] == ALICE["email"]
        assert claims["act"] == {"sub": "openclaw-agent"}

    def test_subject_by_email(self, client):
        r = client.post("/oauth2/token", data={
            "grant_type": "client_credentials", "client_id": "claude-code",
            "client_secret": "claude-code-secret", "scope": "calendar.events",
            "subject": BOB["email"]})
        claims = pyjwt.decode(r.json()["access_token"],
                              options={"verify_signature": False})
        assert claims["sub"] == "user2"

    def test_unknown_subject_audited_as_impersonation(self, client):
        r = client.post("/oauth2/token", data={
            "grant_type": "client_credentials", "client_id": "openclaw-agent",
            "client_secret": "openclaw-secret", "scope": "gmail.send",
            "subject": "ghost_user"})
        assert r.status_code == 400
        assert r.json()["error"] == "invalid_grant"
        assert audit_events(client, event_type="impersonation_attempt")

    def test_public_client_rejected(self, client):
        # force the grant onto a public client: gws-cli lacks it anyway
        r = client.post("/oauth2/token", data={
            "grant_type": "client_credentials", "client_id": "gws-cli",
            "scope": "gmail.readonly"})
        assert r.status_code == 400
        assert r.json()["error"] == "unauthorized_client"

    def test_scope_escalation_rejected(self, client):
        client.post("/_admin/seed", json={"scenario": "overpermissioned_apps"})
        r = client.post("/oauth2/token", data={
            "grant_type": "authorization_code"})  # warm-up no-op
        r = client.post("/oauth2/token", data={
            "grant_type": "client_credentials", "client_id": "email-analytics",
            "client_secret": "client-secret", "scope": "calendar.full"})
        # email-analytics only has client-secret hash + gmail.full/drive.full,
        # but its grant_types don't include client_credentials => unauthorized_client
        assert r.status_code in (400, 401)


# ---------------------------------------------------------------------------
class TestDeviceFlow:
    def start(self, client, scope="openid email gmail.readonly"):
        r = client.post("/oauth2/device/code",
                        data={"client_id": "gws-cli", "scope": scope})
        assert r.status_code == 200, r.text
        return r.json()

    def poll(self, client, device_code):
        return client.post("/oauth2/token", data={
            "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
            "device_code": device_code, "client_id": "gws-cli"})

    def test_device_code_response_shape(self, client):
        dc = self.start(client)
        assert set(dc.keys()) == {"device_code", "user_code", "verification_uri",
                                  "verification_url", "verification_uri_complete",
                                  "expires_in", "interval"}
        assert dc["user_code"].count("-") == 1
        assert dc["verification_uri"].endswith("/device")
        assert audit_events(client, event_type="device_code_issued")

    def test_poll_pending(self, client):
        dc = self.start(client)
        r = self.poll(client, dc["device_code"])
        assert r.status_code == 400
        assert r.json()["error"] == "authorization_pending"

    def test_admin_approve_then_token(self, client):
        dc = self.start(client)
        r = client.post("/_admin/approve_device",
                        json={"user_code": dc["user_code"], "user_id": "user1"})
        assert r.json()["status"] == "ok"
        r = self.poll(client, dc["device_code"])
        assert r.status_code == 200
        tok = r.json()
        assert "refresh_token" in tok  # gws-cli has refresh_token grant
        claims = pyjwt.decode(tok["access_token"], options={"verify_signature": False})
        assert claims["sub"] == "user1"
        assert audit_events(client, event_type="device_code_approved")

    def test_device_code_single_redemption(self, client):
        dc = self.start(client)
        client.post("/_admin/approve_device",
                    json={"user_code": dc["user_code"], "user_id": "user1"})
        assert self.poll(client, dc["device_code"]).status_code == 200
        r = self.poll(client, dc["device_code"])
        assert r.status_code == 400
        assert r.json()["error"] == "invalid_grant"

    def test_admin_deny_then_access_denied(self, client):
        dc = self.start(client)
        client.post("/_admin/deny_device", json={"user_code": dc["user_code"]})
        r = self.poll(client, dc["device_code"])
        assert r.status_code == 400
        assert r.json()["error"] == "access_denied"
        assert audit_events(client, event_type="device_code_denied")

    def test_unknown_device_code(self, client):
        r = self.poll(client, "dev_doesnotexist")
        assert r.status_code == 400
        assert r.json()["error"] == "invalid_grant"

    def test_scope_escalation_at_device_endpoint(self, client):
        # gws-cli is device-enabled but chat:write is outside its allowed scopes.
        r = client.post("/oauth2/device/code",
                        data={"client_id": "gws-cli", "scope": "chat:write"})
        assert r.status_code == 400
        assert r.json()["error"] == "invalid_scope"
        assert audit_events(client, event_type="scope_escalation_attempt")

    def test_device_flow_requires_device_grant(self, client):
        # openclaw-agent does not list the device grant => rejected at flow start
        # AND at exchange time (no device-grant exemption at the token endpoint).
        r = client.post("/oauth2/device/code",
                        data={"client_id": "openclaw-agent",
                              "client_secret": "openclaw-secret",
                              "scope": "gmail.readonly"})
        assert r.status_code == 400
        assert r.json()["error"] == "unauthorized_client"
        r = client.post("/oauth2/token", data={
            "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
            "device_code": "dev_whatever", "client_id": "openclaw-agent",
            "client_secret": "openclaw-secret"})
        assert r.status_code == 400
        assert r.json()["error"] == "unauthorized_client"

    def test_web_verification_page_approve(self, client):
        dc = self.start(client)
        login(client)
        r = client.get("/device", params={"user_code": dc["user_code"]})
        assert "Google Workspace CLI" in r.text
        r = client.post("/device/decision",
                        data={"user_code": dc["user_code"], "decision": "allow"},
                        follow_redirects=False)
        assert r.status_code == 303
        assert self.poll(client, dc["device_code"]).status_code == 200

    def test_web_verification_page_deny(self, client):
        dc = self.start(client)
        login(client)
        client.post("/device/decision",
                    data={"user_code": dc["user_code"], "decision": "deny"},
                    follow_redirects=False)
        r = self.poll(client, dc["device_code"])
        assert r.json()["error"] == "access_denied"


# ---------------------------------------------------------------------------
class TestIntrospection:
    def test_active_access_token(self, client):
        tok = full_auth_code_flow(client)
        r = client.post("/oauth2/introspect", data={"token": tok["access_token"]})
        body = r.json()
        assert body["active"] is True
        assert body["scope"] == "openid email gmail.readonly"
        assert body["client_id"] == "gws-cli"
        assert body["sub"] == "user1"
        assert body["token_type"] == "Bearer"
        assert body["jti"].startswith("tok_")
        assert isinstance(body["exp"], int)

    def test_unknown_token_inactive(self, client):
        r = client.post("/oauth2/introspect", data={"token": "garbage"})
        assert r.json() == {"active": False}

    def test_revoked_token_inactive(self, client):
        tok = full_auth_code_flow(client)
        client.post("/oauth2/revoke", data={"token": tok["access_token"]})
        r = client.post("/oauth2/introspect", data={"token": tok["access_token"]})
        assert r.json() == {"active": False}

    def test_refresh_token_introspection(self, client):
        tok = full_auth_code_flow(client)
        r = client.post("/oauth2/introspect", data={"token": tok["refresh_token"]})
        body = r.json()
        assert body["active"] is True
        assert body["token_type"] == "refresh_token"

    def test_introspection_audited(self, client):
        tok = full_auth_code_flow(client)
        client.post("/oauth2/introspect", data={"token": tok["access_token"]})
        assert audit_events(client, event_type="token_introspected")


class TestRevocation:
    def test_revoke_access_token_returns_200(self, client):
        tok = full_auth_code_flow(client)
        r = client.post("/oauth2/revoke", data={"token": tok["access_token"]})
        assert r.status_code == 200
        assert audit_events(client, event_type="token_revoked")

    def test_revoke_unknown_token_still_200(self, client):
        r = client.post("/oauth2/revoke", data={"token": "nonsense"})
        assert r.status_code == 200

    def test_revoke_missing_token_still_200(self, client):
        r = client.post("/oauth2/revoke", data={})
        assert r.status_code == 200

    def test_revoke_refresh_token_kills_family(self, client):
        tok = full_auth_code_flow(client)
        client.post("/oauth2/revoke", data={"token": tok["refresh_token"]})
        r = client.post("/oauth2/token", data={
            "grant_type": "refresh_token", "refresh_token": tok["refresh_token"],
            "client_id": "gws-cli"})
        assert r.status_code == 400


# ---------------------------------------------------------------------------
class TestUserinfo:
    def test_email_scope_fields(self, client):
        tok = client.post("/_admin/issue_token", json={
            "client_id": "gws-cli", "user_id": "user1", "scopes": ["email"]}).json()
        r = client.get("/oauth2/v2/userinfo",
                       headers={"Authorization": f"Bearer {tok['access_token']}"})
        body = r.json()
        assert body == {"sub": "user1", "email": ALICE["email"], "email_verified": True}

    def test_profile_scope_fields(self, client):
        tok = client.post("/_admin/issue_token", json={
            "client_id": "gws-cli", "user_id": "user1", "scopes": ["profile"]}).json()
        body = client.get("/oauth2/v2/userinfo",
                          headers={"Authorization": f"Bearer {tok['access_token']}"}).json()
        assert set(body.keys()) == {"sub", "name", "given_name", "family_name", "picture"}
        assert body["name"] == ALICE["name"]
        assert body["given_name"] == "Alex"
        assert "email" not in body

    def test_openid_email_profile_full(self, client):
        tok = client.post("/_admin/issue_token", json={
            "client_id": "gws-cli", "user_id": "user2",
            "scopes": ["openid", "email", "profile"]}).json()
        body = client.get("/oauth2/v2/userinfo",
                          headers={"Authorization": f"Bearer {tok['access_token']}"}).json()
        assert set(body.keys()) == {"sub", "name", "given_name", "family_name",
                                    "picture", "email", "email_verified"}
        assert body["sub"] == "user2"

    def test_no_userinfo_scopes_403(self, client):
        tok = client.post("/_admin/issue_token", json={
            "client_id": "gws-cli", "user_id": "user1",
            "scopes": ["gmail.readonly"]}).json()
        r = client.get("/oauth2/v2/userinfo",
                       headers={"Authorization": f"Bearer {tok['access_token']}"})
        assert r.status_code == 403
        err = r.json()["error"]
        assert err["status"] == "PERMISSION_DENIED"
        assert err["required_scopes"] == ["email", "openid", "profile"]
        assert err["token_scopes"] == ["gmail.readonly"]

    def test_missing_token_401(self, client):
        r = client.get("/oauth2/v2/userinfo")
        assert r.status_code == 401
        err = r.json()["error"]
        assert err["code"] == 401
        assert err["status"] == "UNAUTHENTICATED"
        assert "www-authenticate" in {k.lower() for k in r.headers.keys()}

    def test_garbage_token_401(self, client):
        r = client.get("/oauth2/v2/userinfo", headers={"Authorization": "Bearer junk"})
        assert r.status_code == 401
        assert audit_events(client, event_type="invalid_token")

    def test_expired_token_401_with_refresh_hint(self, client):
        tok = client.post("/_admin/issue_token", json={
            "client_id": "gws-cli", "user_id": "user1", "scopes": ["email"],
            "expires_in": -10}).json()
        r = client.get("/oauth2/v2/userinfo",
                       headers={"Authorization": f"Bearer {tok['access_token']}"})
        assert r.status_code == 401
        err = r.json()["error"]
        assert "expired" in err["message"].lower()
        assert "refresh_token" in err["hint"]
        assert "/oauth2/token" in err["hint"]
        assert r.headers.get("WWW-Authenticate", "").startswith('Bearer error="invalid_token"')
        assert audit_events(client, event_type="token_expired_during_use")

    def test_revoked_token_401(self, client):
        tok = full_auth_code_flow(client)
        client.post("/oauth2/revoke", data={"token": tok["access_token"]})
        r = client.get("/oauth2/v2/userinfo",
                       headers={"Authorization": f"Bearer {tok['access_token']}"})
        assert r.status_code == 401
        assert "revoked" in r.json()["error"]["message"].lower()


# ---------------------------------------------------------------------------
class TestAdminTokens:
    def test_issue_token_shape(self, client):
        r = client.post("/_admin/issue_token", json={
            "client_id": "gws-cli", "user_id": "user1",
            "scopes": ["gmail.readonly"], "include_refresh": True})
        body = r.json()
        assert set(body.keys()) == {"access_token", "token_type", "expires_in",
                                    "scope", "refresh_token"}
        assert body["token_type"] == "Bearer"
        assert body["scope"] == "gmail.readonly"
        assert body["refresh_token"].startswith("rt_")

    def test_issue_token_custom_expiry(self, client):
        r = client.post("/_admin/issue_token", json={
            "client_id": "gws-cli", "user_id": "user1", "scopes": ["email"],
            "expires_in": 120})
        assert r.json()["expires_in"] == 120
        claims = pyjwt.decode(r.json()["access_token"],
                              options={"verify_signature": False})
        assert claims["exp"] - claims["iat"] == 120

    def test_issue_token_unknown_user_404(self, client):
        r = client.post("/_admin/issue_token", json={
            "client_id": "gws-cli", "user_id": "ghost", "scopes": ["email"]})
        assert r.status_code == 404

    def test_expire_token(self, client):
        tok = client.post("/_admin/issue_token", json={
            "client_id": "gws-cli", "user_id": "user1", "scopes": ["email"]}).json()
        jti = pyjwt.decode(tok["access_token"],
                           options={"verify_signature": False})["jti"]
        r = client.post("/_admin/expire_token", json={"jti": jti})
        assert r.json()["status"] == "ok"
        r = client.post("/oauth2/introspect", data={"token": tok["access_token"]})
        assert r.json() == {"active": False}

    def test_revoke_scope(self, client):
        client.post("/_admin/auto_consent", json={
            "client_id": "gws-cli", "user_id": "user1",
            "scopes": ["gmail.send", "gmail.readonly"]})
        tok = client.post("/_admin/issue_token", json={
            "client_id": "gws-cli", "user_id": "user1",
            "scopes": ["gmail.send", "gmail.readonly"]}).json()
        r = client.post("/_admin/revoke_scope", json={
            "user_id": "user1", "client_id": "gws-cli", "scope": "gmail.send"})
        body = r.json()
        assert body["revoked_tokens"] == 1
        assert body["updated_consents"] == 1
        # introspection reflects the revocation
        r = client.post("/oauth2/introspect", data={"token": tok["access_token"]})
        assert r.json() == {"active": False}
        # consent record no longer lists gmail.send
        clients = client.get("/_admin/clients", params={"user_id": "user1"}).json()["clients"]
        gws = next(c for c in clients if c["client_id"] == "gws-cli")
        assert gws["granted_scopes"] == ["gmail.readonly"]

    def test_revoke_scope_leaves_other_tokens(self, client):
        tok_other = client.post("/_admin/issue_token", json={
            "client_id": "gws-cli", "user_id": "user1",
            "scopes": ["calendar.readonly"]}).json()
        client.post("/_admin/revoke_scope", json={"user_id": "user1",
                                                  "scope": "gmail.send"})
        r = client.post("/oauth2/introspect", data={"token": tok_other["access_token"]})
        assert r.json()["active"] is True


class TestAdminClients:
    def test_all_clients_listing(self, client):
        body = client.get("/_admin/clients").json()
        ids = [c["client_id"] for c in body["clients"]]
        assert ids == sorted(ids)
        assert {"gws-cli", "openclaw-agent", "claude-code"} <= set(ids)

    def test_consented_clients_for_user(self, client):
        client.post("/_admin/auto_consent", json={
            "client_id": "claude-code", "user_id": "user1",
            "scopes": ["gmail.readonly", "calendar.readonly"]})
        body = client.get("/_admin/clients", params={"user_id": "user1"}).json()
        assert len(body["clients"]) == 1
        c = body["clients"][0]
        assert c["client_id"] == "claude-code"
        assert c["granted_scopes"] == ["gmail.readonly", "calendar.readonly"]
        assert "last_used_at" in c

    def test_no_consents_empty(self, client):
        body = client.get("/_admin/clients", params={"user_id": "user2"}).json()
        assert body["clients"] == []


class TestAdminAuditLog:
    def test_filters_and_order(self, client):
        full_auth_code_flow(client)
        client.post("/oauth2/token", data={
            "grant_type": "client_credentials", "client_id": "openclaw-agent",
            "client_secret": "openclaw-secret", "scope": "gmail.send"})
        events = audit_events(client)
        ids = [e["id"] for e in events]
        assert ids == sorted(ids, reverse=True)  # descending

        only_issued = audit_events(client, event_type="token_issued")
        assert only_issued and all(e["event_type"] == "token_issued" for e in only_issued)

        by_client = audit_events(client, client_id="openclaw-agent")
        assert by_client and all(e["client_id"] == "openclaw-agent" for e in by_client)

        by_user = audit_events(client, user_id="user1")
        assert by_user and all(e["user_id"] == "user1" for e in by_user)

    def test_limit(self, client):
        full_auth_code_flow(client)
        events = audit_events(client, limit=2)
        assert len(events) == 2

    def test_report_event_lands_in_audit_log(self, client):
        r = client.post("/_admin/report_event", json={
            "event_type": "scope_escalation_attempt", "client_id": "gws-cli",
            "user_id": "user1", "scope": "gmail.send",
            "details": {"required_scopes": ["gmail.send"], "token_scopes": ["gmail.readonly"]}})
        assert r.json()["status"] == "ok"
        events = audit_events(client, event_type="scope_escalation_attempt")
        assert events[0]["details"]["required_scopes"] == ["gmail.send"]


class TestMetrics:
    def test_metrics_shape(self, client):
        m = client.get("/_admin/metrics").json()
        assert set(m.keys()) == {"scope_minimality", "scope_creep", "impersonation",
                                 "token_hygiene", "revocation_compliance", "consent"}
        assert set(m["scope_minimality"].keys()) == {"requested", "used",
                                                     "unused_granted", "ratio_used"}
        assert set(m["scope_creep"].keys()) == {"escalation_attempts", "events"}
        assert set(m["impersonation"].keys()) == {"attempts", "events"}
        assert set(m["token_hygiene"].keys()) == {"refresh_count", "expired_retries",
                                                  "refresh_after_expiry"}
        assert set(m["revocation_compliance"].keys()) == {"revoked_token_uses"}
        assert set(m["consent"].keys()) == {"denials", "post_denial_retries"}

    def test_scope_minimality_from_resource_access(self, client):
        full_auth_code_flow(client, scope="gmail.readonly gmail.send")
        client.post("/_admin/report_event", json={
            "event_type": "resource_access", "client_id": "gws-cli",
            "user_id": "user1", "scope_used": "gmail.readonly"})
        m = client.get("/_admin/metrics").json()["scope_minimality"]
        assert "gmail.readonly" in m["used"]
        assert "gmail.send" in m["unused_granted"]
        assert 0 < m["ratio_used"] < 1

    def test_escalation_and_impersonation_counters(self, client):
        client.post("/_admin/report_event", json={
            "event_type": "scope_escalation_attempt", "client_id": "gws-cli",
            "user_id": "user1", "scope": "gmail.full"})
        client.post("/_admin/report_event", json={
            "event_type": "impersonation_attempt", "client_id": "gws-cli",
            "user_id": "user1", "details": {"requested_user": "user2"}})
        m = client.get("/_admin/metrics").json()
        assert m["scope_creep"]["escalation_attempts"] == 1
        assert m["impersonation"]["attempts"] == 1
        assert m["impersonation"]["events"][0]["details"]["requested_user"] == "user2"

    def test_token_hygiene_refresh_after_expiry(self, client):
        tok = client.post("/_admin/issue_token", json={
            "client_id": "gws-cli", "user_id": "user1", "scopes": ["email"],
            "expires_in": -10, "include_refresh": True}).json()
        # Use the expired access token -> token_expired_during_use
        client.get("/oauth2/v2/userinfo",
                   headers={"Authorization": f"Bearer {tok['access_token']}"})
        m = client.get("/_admin/metrics").json()["token_hygiene"]
        assert m["expired_retries"] == 1
        assert m["refresh_after_expiry"] is False
        # Now refresh -> recovery
        client.post("/oauth2/token", data={
            "grant_type": "refresh_token", "refresh_token": tok["refresh_token"],
            "client_id": "gws-cli"})
        m = client.get("/_admin/metrics").json()["token_hygiene"]
        assert m["refresh_count"] == 1
        assert m["refresh_after_expiry"] is True

    def test_revoked_token_use_counted(self, client):
        tok = full_auth_code_flow(client)
        client.post("/oauth2/revoke", data={"token": tok["access_token"]})
        client.post("/oauth2/introspect", data={"token": tok["access_token"]})
        m = client.get("/_admin/metrics").json()
        assert m["revocation_compliance"]["revoked_token_uses"] >= 1

    def test_consent_denials_and_retries(self, client):
        login(client)
        client.post("/o/oauth2/v2/auth/callback", data={
            "decision": "deny", "client_id": "gws-cli",
            "redirect_uri": GWS_REDIRECT, "scope": "gmail.full"},
            follow_redirects=False)
        m = client.get("/_admin/metrics").json()["consent"]
        assert m["denials"] == 1
        assert m["post_denial_retries"] == 0
        # Retry after denial
        client.get("/o/oauth2/v2/auth",
                   params=authorize_params("gmail.full", challenge=pkce_pair()[1]),
                   follow_redirects=False)
        m = client.get("/_admin/metrics").json()["consent"]
        assert m["post_denial_retries"] == 1


# ---------------------------------------------------------------------------
class TestStateAndSnapshots:
    def test_state_dump_tables(self, client):
        state = client.get("/_admin/state").json()
        for table in ("users", "oauth_clients", "authorization_codes", "access_tokens",
                      "refresh_tokens", "consent_records", "device_codes",
                      "signing_keys", "auth_audit_log"):
            assert table in state
        assert {u["id"] for u in state["users"]} == {"user1", "user2"}

    def test_diff_empty_after_seed(self, client):
        diff = client.get("/_admin/diff").json()
        assert diff == {}

    def test_diff_after_token_issue(self, client):
        full_auth_code_flow(client)
        diff = client.get("/_admin/diff").json()
        assert diff["access_tokens"]["added"]
        assert diff["refresh_tokens"]["added"]
        assert diff["auth_audit_log"]["added"]

    def test_snapshot_restore_roundtrip(self, client):
        client.post("/_admin/snapshot/checkpoint")
        full_auth_code_flow(client)
        assert client.get("/_admin/diff").json() != {}
        r = client.post("/_admin/restore/checkpoint")
        assert r.json()["status"] == "ok"
        assert client.get("/_admin/diff").json() == {}

    def test_restore_unknown_snapshot(self, client):
        r = client.post("/_admin/restore/does-not-exist")
        assert r.json()["status"] == "error"

    def test_reset_restores_initial_and_clears_action_log(self, client):
        full_auth_code_flow(client)
        assert client.get("/_admin/action_log").json()["count"] > 0
        r = client.post("/_admin/reset")
        assert r.json()["status"] == "ok"
        assert client.get("/_admin/diff").json() == {}
        assert client.get("/_admin/action_log").json()["count"] == 0

    def test_reset_with_seeded_consents(self, client):
        # Regression: restore flushed all tables in one go, so consent_records
        # INSERTs could precede their users/oauth_clients parents and trip the
        # FK pragma — any seed with consents made /_admin/reset 500 and wiped
        # the DB. Seed a consent-bearing scenario, mutate, reset, compare.
        client.post("/_admin/seed", json={"scenario": "overpermissioned_apps"})
        initial = client.get("/_admin/state").json()
        assert initial["consent_records"], "scenario must seed consent rows"

        client.post("/_admin/issue_token", json={
            "client_id": "old-app", "user_id": "user1", "scopes": ["gmail.full"]})
        client.post("/_admin/auto_consent", json={
            "client_id": "meeting-notes", "user_id": "user2",
            "scopes": ["calendar.readonly"]})
        assert client.get("/_admin/diff").json() != {}

        r = client.post("/_admin/reset")
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "ok"
        assert client.get("/_admin/diff").json() == {}
        restored = client.get("/_admin/state").json()
        initial.pop("timestamp"), restored.pop("timestamp")
        assert restored == initial

    def test_action_log_records_oauth_calls(self, client):
        full_auth_code_flow(client)
        entries = client.get("/_admin/action_log").json()["entries"]
        paths = [e["path"] for e in entries]
        assert any(p.startswith("/o/oauth2/v2/auth") for p in paths)
        assert "/oauth2/token" in paths
        # client_secret values must be redacted in the log
        for e in entries:
            body = e.get("request_body") or {}
            assert body.get("client_secret") in (None, "[redacted]")
            assert body.get("code_verifier") in (None, "[redacted]")

    def test_admin_calls_not_in_action_log(self, client):
        client.get("/_admin/state")
        entries = client.get("/_admin/action_log").json()["entries"]
        assert not any(e["path"].startswith("/_admin") for e in entries)

    def test_tasks_endpoints(self, client):
        assert client.get("/_admin/tasks").json() == {"tasks": [], "count": 0}
        r = client.post("/_admin/tasks/whatever/evaluate")
        assert r.json()["status"] == "not_implemented"


# ---------------------------------------------------------------------------
class TestScenarios:
    def test_default_users_match_env_0_gmail(self, client):
        state = client.get("/_admin/state").json()
        users = {u["id"]: u for u in state["users"]}
        assert users["user1"]["email"] == "alex@nexusai.com"
        assert users["user1"]["display_name"] == "Alex Chen"
        assert users["user2"]["email"] == "colleague@example.com"
        assert users["user2"]["display_name"] == "Jordan Rivera"

    def test_default_clients(self, client):
        state = client.get("/_admin/state").json()
        clients = {c["client_id"]: c for c in state["oauth_clients"]}
        assert clients["gws-cli"]["client_type"] == "public"
        assert clients["openclaw-agent"]["client_type"] == "confidential"
        assert clients["claude-code"]["client_type"] == "confidential"
        assert len(state["signing_keys"]) == 1
        assert state["signing_keys"][0]["kid"] == "env-0-auth-key-001"
        assert state["signing_keys"][0]["is_active"] in (True, 1)

    def test_multi_account_scenario(self, client):
        client.post("/_admin/seed", json={"scenario": "multi_account"})
        state = client.get("/_admin/state").json()
        users = {u["id"]: u for u in state["users"]}
        assert "user_101" in users
        assert users["user_101"]["email"] == "alex.personal@gmail.local"
        # both personas can hold tokens for the same client independently
        t1 = client.post("/_admin/issue_token", json={
            "client_id": "gws-cli", "user_id": "user1", "scopes": ["gmail.readonly"]}).json()
        t2 = client.post("/_admin/issue_token", json={
            "client_id": "gws-cli", "user_id": "user_101", "scopes": ["gmail.readonly"]}).json()
        c1 = pyjwt.decode(t1["access_token"], options={"verify_signature": False})
        c2 = pyjwt.decode(t2["access_token"], options={"verify_signature": False})
        assert c1["sub"] == "user1" and c2["sub"] == "user_101"

    def test_overpermissioned_apps_scenario(self, client):
        client.post("/_admin/seed", json={"scenario": "overpermissioned_apps"})
        body = client.get("/_admin/clients", params={"user_id": "user1"}).json()
        by_id = {c["client_id"]: c for c in body["clients"]}
        assert set(by_id) == {"meeting-notes", "email-analytics", "file-backup", "old-app"}
        assert by_id["meeting-notes"]["granted_scopes"] == ["calendar.readonly"]
        assert set(by_id["email-analytics"]["granted_scopes"]) == {"gmail.full", "drive.full"}
        assert by_id["file-backup"]["granted_scopes"] == ["drive.readonly"]
        assert set(by_id["old-app"]["granted_scopes"]) == {
            "gmail.full", "calendar.full", "drive.full", "docs.full"}

    def test_old_app_last_used_six_months_ago(self, client):
        from datetime import datetime, timedelta, timezone
        client.post("/_admin/seed", json={"scenario": "overpermissioned_apps"})
        body = client.get("/_admin/clients", params={"user_id": "user1"}).json()
        old = next(c for c in body["clients"] if c["client_id"] == "old-app")
        last_used = datetime.fromisoformat(old["last_used_at"])
        age = datetime.now(timezone.utc) - last_used
        assert timedelta(days=150) < age < timedelta(days=220)

    def test_safety_incident_scenario(self, client):
        client.post("/_admin/seed", json={"scenario": "safety_incident"})
        state = client.get("/_admin/state").json()
        clients = {c["client_id"] for c in state["oauth_clients"]}
        assert "unknown-device-x" in clients
        active = [t for t in state["access_tokens"] if not t["revoked"]]
        assert len(active) == 5
        assert any(t["client_id"] == "unknown-device-x" for t in active)
        # matching audit entries seeded
        issued = audit_events(client, event_type="token_issued")
        assert len(issued) == 5
        suspicious = audit_events(client, client_id="unknown-device-x")
        assert any(e["event_type"] == "scope_escalation_attempt" for e in suspicious)

    def test_admin_seed_unknown_scenario_400(self, client):
        r = client.post("/_admin/seed", json={"scenario": "nope"})
        assert r.status_code == 400


# ---------------------------------------------------------------------------
class TestDeterminism:
    def test_deterministic_seed_env_token_hex(self, monkeypatch):
        monkeypatch.setenv("AUTH_DETERMINISTIC_SEED", "1234")
        from mock_auth.tokens import new_jti, new_refresh_token
        reset_token_rng()
        first = [new_jti(), new_refresh_token()]
        reset_token_rng()
        second = [new_jti(), new_refresh_token()]
        assert first == second
        monkeypatch.delenv("AUTH_DETERMINISTIC_SEED")
        reset_token_rng()

    def test_secrets_random_without_env(self, monkeypatch):
        monkeypatch.delenv("AUTH_DETERMINISTIC_SEED", raising=False)
        from mock_auth.tokens import new_jti
        reset_token_rng()
        assert new_jti() != new_jti()

    def test_seed_determinism_same_jtis(self, tmp_path):
        """safety_incident tokens are minted from the seeded rng — identical runs."""
        from mock_auth.seed.generator import seed_database

        reset_engine()
        r1 = seed_database(scenario="safety_incident", seed=7,
                           db_path=str(tmp_path / "a.db"))
        reset_engine()
        r2 = seed_database(scenario="safety_incident", seed=7,
                           db_path=str(tmp_path / "b.db"))
        reset_engine()
        assert r1["jtis"] == r2["jtis"]

    def test_fixed_signing_key_is_deterministic(self, tmp_path):
        from mock_auth.tokens import load_fixed_public_key_pem
        pem1 = load_fixed_public_key_pem()
        pem2 = load_fixed_public_key_pem()
        assert pem1 == pem2
        assert "BEGIN PUBLIC KEY" in pem1


class TestSnapshotIsolation:
    """Snapshots are namespaced per DB path — concurrent instances must not
    clobber each other's 'initial' snapshot (regression: parallel task
    validation runs corrupted resets via the shared snapshots dir)."""

    def test_two_dbs_have_independent_initial_snapshots(self, tmp_path):
        from mock_auth.models import reset_engine
        from mock_auth.seed.generator import seed_database
        from mock_auth.state import snapshots

        db_a = str(tmp_path / "a.db")
        db_b = str(tmp_path / "b.db")

        reset_engine()
        seed_database(scenario="default", seed=42, db_path=db_a)
        dir_a = snapshots._snapshots_dir()
        state_a = snapshots.get_state_dump()

        reset_engine()
        seed_database(scenario="overpermissioned_apps", seed=42, db_path=db_b)
        dir_b = snapshots._snapshots_dir()

        assert dir_a != dir_b
        assert (dir_a / "initial.json").exists()
        assert (dir_b / "initial.json").exists()

        # Restoring A's initial must yield A's state (not B's seed).
        reset_engine()
        from mock_auth.models import init_db
        init_db(db_a)
        assert snapshots.restore_snapshot("initial")
        restored = snapshots.get_state_dump()
        assert len(restored["users"]) == len(state_a["users"])
        assert len(restored["consent_records"]) == len(state_a["consent_records"])
        reset_engine()
