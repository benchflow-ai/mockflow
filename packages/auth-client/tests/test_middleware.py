"""Env_0AuthMiddleware behavior: 401/403 envelopes, bypasses, JWKS refetch, aud, state."""

import time
from datetime import datetime, timezone

import httpx
import jwt
import pytest
from conftest import KID, OTHER_KID, bearer, build_app
from fastapi.testclient import TestClient

from env_0_auth_client.testing import jwks_for, make_jwt

MESSAGES_URL = "/gmail/v1/users/user_001/messages"
SEND_URL = "/gmail/v1/users/user_001/messages/send"
PROFILE_URL = "/gmail/v1/users/user_001/profile"


class TestMissingAndInvalidTokens:
    def test_no_token_401(self, client):
        resp = client.get(MESSAGES_URL)
        assert resp.status_code == 401
        err = resp.json()["error"]
        assert err["code"] == 401
        assert err["status"] == "UNAUTHENTICATED"
        assert err["message"]
        assert err["hint"]
        assert resp.headers["WWW-Authenticate"].startswith('Bearer error="invalid_token"')

    def test_non_bearer_scheme_401(self, client):
        resp = client.get(MESSAGES_URL, headers={"Authorization": "Basic dXNlcjpwdw=="})
        assert resp.status_code == 401

    def test_garbage_token_401(self, client):
        resp = client.get(MESSAGES_URL, headers=bearer("not.a.jwt"))
        assert resp.status_code == 401
        assert resp.json()["error"]["status"] == "UNAUTHENTICATED"
        assert "WWW-Authenticate" in resp.headers

    def test_token_signed_by_wrong_key_401(self, client, other_keypair):
        # kid matches a published key, but the signature is from a different key
        token = make_jwt(private_key=other_keypair[0], kid=KID, scope="gmail.readonly")
        resp = client.get(MESSAGES_URL, headers=bearer(token))
        assert resp.status_code == 401

    def test_wrong_issuer_401(self, client, private_key):
        token = make_jwt(
            private_key=private_key, kid=KID, issuer="http://evil.example", scope="gmail.readonly"
        )
        resp = client.get(MESSAGES_URL, headers=bearer(token))
        assert resp.status_code == 401
        assert "issuer" in resp.json()["error"]["message"].lower()


class TestExpiredToken:
    def test_expired_401_body_includes_expiry_and_refresh_hint(self, client, private_key):
        token = make_jwt(private_key=private_key, kid=KID, scope="gmail.readonly", expires_in=-60)
        exp = jwt.decode(token, options={"verify_signature": False})["exp"]
        expected_iso = datetime.fromtimestamp(exp, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        resp = client.get(MESSAGES_URL, headers=bearer(token))
        assert resp.status_code == 401
        err = resp.json()["error"]
        assert err["status"] == "UNAUTHENTICATED"
        assert expected_iso in err["message"]
        assert "/oauth2/token" in err["hint"]
        assert "grant_type=refresh_token" in err["hint"]
        assert resp.headers["WWW-Authenticate"].startswith('Bearer error="invalid_token"')


class TestScopeEnforcement:
    def test_wrong_scope_403_lists_required_and_token_scopes(self, client, private_key):
        token = make_jwt(private_key=private_key, kid=KID, scope="openid gmail.readonly")
        resp = client.post(SEND_URL, headers=bearer(token))
        assert resp.status_code == 403
        err = resp.json()["error"]
        assert err["code"] == 403
        assert err["status"] == "PERMISSION_DENIED"
        assert err["required_scopes"] == ["gmail.send", "gmail.full"]
        assert err["token_scopes"] == ["openid", "gmail.readonly"]
        assert err["hint"]

    def test_or_logic_any_listed_scope_grants(self, client, private_key):
        for scope in ("gmail.send", "gmail.full"):
            token = make_jwt(private_key=private_key, kid=KID, scope=scope)
            resp = client.post(SEND_URL, headers=bearer(token))
            assert resp.status_code == 200, scope

    def test_scope_map_miss_is_auth_only(self, client, private_key):
        # /profile is not in the scope map: any valid token passes, no scope needed
        token = make_jwt(private_key=private_key, kid=KID, scope="openid")
        resp = client.get(PROFILE_URL, headers=bearer(token))
        assert resp.status_code == 200

    def test_scope_map_miss_still_requires_auth(self, client):
        assert client.get(PROFILE_URL).status_code == 401


class TestOkPathState:
    def test_request_state_fields_set(self, client, private_key):
        token = make_jwt(
            private_key=private_key,
            kid=KID,
            sub="user_001",
            client_id="gws-cli",
            scope="openid email gmail.readonly",
        )
        resp = client.get(MESSAGES_URL, headers=bearer(token))
        assert resp.status_code == 200
        data = resp.json()
        assert data["auth_user_id"] == "user_001"
        assert data["auth_email"] == "user_001@clawsbench.local"  # make_jwt default
        assert data["auth_scopes"] == ["openid", "email", "gmail.readonly"]
        assert data["auth_client_id"] == "gws-cli"
        assert data["auth_jti"].startswith("tok_") and len(data["auth_jti"]) == 28
        assert isinstance(data["auth_token_exp"], int)
        assert data["auth_token_exp"] > time.time()

    def test_auth_email_set_from_email_claim(self, client, private_key):
        token = make_jwt(
            private_key=private_key,
            kid=KID,
            sub="user_001",
            scope="gmail.readonly",
            email="alex@nexusai.com",
        )
        resp = client.get(MESSAGES_URL, headers=bearer(token))
        assert resp.status_code == 200
        assert resp.json()["auth_email"] == "alex@nexusai.com"

    def test_auth_email_empty_string_when_claim_absent(self, client, private_key):
        # make_jwt always adds an email claim; mint a env-0-auth-shaped token
        # WITHOUT one directly to pin the empty-string default.
        now = int(time.time())
        claims = {
            "iss": "http://localhost:9000",
            "sub": "user_001",
            "aud": "gws-cli",
            "exp": now + 3600,
            "iat": now,
            "jti": "tok_" + "0" * 24,
            "scope": "gmail.readonly",
            "client_id": "gws-cli",
        }
        token = jwt.encode(claims, private_key, algorithm="RS256", headers={"kid": KID})
        resp = client.get(MESSAGES_URL, headers=bearer(token))
        assert resp.status_code == 200
        assert resp.json()["auth_email"] == ""


class TestBypasses:
    def test_exempt_prefixes_bypass(self, client):
        assert client.get("/_admin/state").status_code == 200
        assert client.get("/health").status_code == 200

    def test_options_bypass(self, client):
        resp = client.options(MESSAGES_URL)
        assert resp.status_code != 401  # reaches the app (405: no OPTIONS handler)

    def test_custom_exempt_prefixes(self, jwks):
        app = build_app(jwks_static=jwks, exempt_prefixes=("/gmail/v1/users/user_001/profile",))
        with TestClient(app) as client:
            assert client.get(PROFILE_URL).status_code == 200
            assert client.get("/health").status_code == 401  # no longer exempt


class TestJwksRefetch:
    def test_unknown_kid_triggers_single_refetch(self, keypair, other_keypair):
        jwks_v1 = jwks_for(keypair[1], kid=KID)
        jwks_v2 = {"keys": jwks_v1["keys"] + jwks_for(other_keypair[1], kid=OTHER_KID)["keys"]}
        state = {"jwks": jwks_v1}
        calls = {"n": 0}

        def jwks_source():
            calls["n"] += 1
            return state["jwks"]

        app = build_app(jwks_static=jwks_source)
        with TestClient(app) as client:
            # 1st fetch: cache primed with v1
            token1 = make_jwt(private_key=keypair[0], kid=KID, scope="gmail.readonly")
            assert client.get(MESSAGES_URL, headers=bearer(token1)).status_code == 200
            assert calls["n"] == 1

            # Known kid within TTL: served from cache, no refetch
            assert client.get(MESSAGES_URL, headers=bearer(token1)).status_code == 200
            assert calls["n"] == 1

            # Key rotation: new kid unknown to the cache -> exactly one refetch, then OK
            state["jwks"] = jwks_v2
            token2 = make_jwt(private_key=other_keypair[0], kid=OTHER_KID, scope="gmail.readonly")
            assert client.get(MESSAGES_URL, headers=bearer(token2)).status_code == 200
            assert calls["n"] == 2

            # Truly unknown kid: one refetch then 401
            ghost = make_jwt(private_key=keypair[0], kid="kid-ghost", scope="gmail.readonly")
            resp = client.get(MESSAGES_URL, headers=bearer(ghost))
            assert resp.status_code == 401
            assert calls["n"] == 3

    def test_ttl_zero_refetches_every_request(self, keypair):
        calls = {"n": 0}

        def jwks_source():
            calls["n"] += 1
            return jwks_for(keypair[1], kid=KID)

        app = build_app(jwks_static=jwks_source, jwks_ttl=0)
        with TestClient(app) as client:
            token = make_jwt(private_key=keypair[0], kid=KID, scope="gmail.readonly")
            client.get(MESSAGES_URL, headers=bearer(token))
            client.get(MESSAGES_URL, headers=bearer(token))
            assert calls["n"] == 2


class TestAudience:
    def test_aud_ignored_by_default(self, client, private_key):
        token = make_jwt(
            private_key=private_key, kid=KID, scope="gmail.readonly", audience="some-other-app"
        )
        assert client.get(MESSAGES_URL, headers=bearer(token)).status_code == 200

    def test_aud_enforced_when_audience_set(self, jwks, private_key):
        app = build_app(jwks_static=jwks, audience="gws-cli")
        with TestClient(app) as client:
            good = make_jwt(private_key=private_key, kid=KID, scope="gmail.readonly", client_id="gws-cli")
            assert client.get(MESSAGES_URL, headers=bearer(good)).status_code == 200

            bad = make_jwt(private_key=private_key, kid=KID, scope="gmail.readonly", audience="evil-app")
            resp = client.get(MESSAGES_URL, headers=bearer(bad))
            assert resp.status_code == 401
            assert "audience" in resp.json()["error"]["message"].lower()


class TestIntrospection:
    @pytest.mark.parametrize("active,expected_status", [(True, 200), (False, 401)])
    def test_introspection_result_enforced(self, monkeypatch, jwks, private_key, active, expected_status):
        monkeypatch.setenv("AUTH_INTROSPECT", "1")
        seen = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append(str(request.url))
            return httpx.Response(200, json={"active": active})

        app = build_app(jwks_static=jwks, introspect_transport=httpx.MockTransport(handler))
        with TestClient(app) as client:
            token = make_jwt(private_key=private_key, kid=KID, scope="gmail.readonly")
            resp = client.get(MESSAGES_URL, headers=bearer(token))
            assert resp.status_code == expected_status
            assert seen and seen[0].endswith("/oauth2/introspect")

    def test_introspection_cached_10s(self, monkeypatch, jwks, private_key):
        monkeypatch.setenv("AUTH_INTROSPECT", "1")
        calls = {"n": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            calls["n"] += 1
            return httpx.Response(200, json={"active": True})

        app = build_app(jwks_static=jwks, introspect_transport=httpx.MockTransport(handler))
        with TestClient(app) as client:
            token = make_jwt(private_key=private_key, kid=KID, scope="gmail.readonly")
            client.get(MESSAGES_URL, headers=bearer(token))
            client.get(MESSAGES_URL, headers=bearer(token))
            assert calls["n"] == 1
