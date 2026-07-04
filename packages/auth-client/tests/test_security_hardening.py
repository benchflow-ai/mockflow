"""Adversarial tests: exempt-prefix path tricks, JWT alg confusion, JWKS
thundering herd, trailing-slash scope behavior, and TestClient+reporting
liveness (no deadlock)."""

import asyncio
import base64
import hashlib
import hmac
import json
import threading

import httpx
import pytest
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from fastapi.testclient import TestClient

from conftest import KID, bearer, build_app

from env_0_auth_client.jwks import JWKSCache
from env_0_auth_client.testing import jwks_for, make_jwt

MESSAGES_URL = "/gmail/v1/users/user_001/messages"


async def _raw_asgi_get(app, path: str, headers: list | None = None):
    """GET against the raw ASGI app with an un-normalized path."""
    scope = {
        "type": "http",
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": path,
        "raw_path": path.encode(),
        "root_path": "",
        "query_string": b"",
        "headers": headers or [],
        "server": ("testserver", 80),
        "client": ("testclient", 50000),
    }
    sent: list[dict] = []

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        sent.append(message)

    await app(scope, receive, send)
    status = next(m["status"] for m in sent if m["type"] == "http.response.start")
    body = b"".join(m.get("body", b"") for m in sent if m["type"] == "http.response.body")
    return status, body


# ---------------------------------------------------------------------------
class TestExemptPrefixPathTricks:
    def test_exact_and_subpath_still_exempt(self, client):
        assert client.get("/_admin/state").status_code == 200
        assert client.get("/health").status_code == 200

    def test_prefix_string_extension_not_exempt(self, client):
        # '/_adminX' must NOT ride the '/_admin' exemption.
        assert client.get("/_adminX").status_code == 401
        assert client.get("/_administrator/state").status_code == 401
        assert client.get("/healthz").status_code == 401

    def test_double_slash_not_exempt(self, client):
        # '//_admin/state' is not '/_admin/state' (different first segment).
        assert client.get("//_admin/state").status_code == 401

    def test_dot_segments_not_normalized_no_data_leak(self, app):
        # httpx/TestClient normalizes '..' client-side, so drive the raw ASGI
        # scope directly. '/_admin/../gmail/...' bypasses auth via the exempt
        # prefix, but Starlette does not normalize dot segments, so NO route
        # matches: the response must be a data-free 404, never message data.
        status, body = asyncio.run(
            _raw_asgi_get(app, "/_admin/../gmail/v1/users/user_001/messages"))
        assert status == 404
        assert b"auth_user_id" not in body

    def test_exempt_prefix_with_trailing_slash_config(self, jwks):
        app = build_app(jwks_static=jwks, exempt_prefixes=("/health/",))
        with TestClient(app) as client:
            assert client.get("/health").status_code == 200
            assert client.get("/healthz").status_code == 401


# ---------------------------------------------------------------------------
def _b64url(data: bytes) -> bytes:
    return base64.urlsafe_b64encode(data).rstrip(b"=")


def craft_token(header: dict, claims: dict, secret: bytes | None) -> str:
    """Hand-rolled JWT (HS256 when secret given, alg=none when None)."""
    signing_input = (_b64url(json.dumps(header, separators=(",", ":")).encode())
                     + b"." + _b64url(json.dumps(claims, separators=(",", ":")).encode()))
    if secret is None:
        return (signing_input + b".").decode()
    sig = _b64url(hmac.new(secret, signing_input, hashlib.sha256).digest())
    return (signing_input + b"." + sig).decode()


class TestJWTAlgAttacks:
    def _claims(self):
        import time
        now = int(time.time())
        return {
            "iss": "http://localhost:9000", "sub": "user_001", "aud": "gws-cli",
            "exp": now + 3600, "iat": now, "jti": "tok_" + "ab" * 12,
            "scope": "gmail.readonly", "email": "a@b.c", "client_id": "gws-cli",
        }

    def test_hs256_signed_with_public_key_pem_rejected(self, client, public_key):
        public_pem = public_key.public_bytes(Encoding.PEM, PublicFormat.SubjectPublicKeyInfo)
        token = craft_token({"alg": "HS256", "typ": "JWT", "kid": KID},
                            self._claims(), public_pem)
        resp = client.get(MESSAGES_URL, headers=bearer(token))
        assert resp.status_code == 401
        assert resp.json()["error"]["status"] == "UNAUTHENTICATED"

    def test_alg_none_rejected(self, client):
        token = craft_token({"alg": "none", "typ": "JWT", "kid": KID},
                            self._claims(), None)
        resp = client.get(MESSAGES_URL, headers=bearer(token))
        assert resp.status_code == 401

    def test_kid_spoof_attacker_key_rejected(self, client, other_keypair):
        # Valid kid in the header, but signed by an attacker's key.
        token = make_jwt(private_key=other_keypair[0], kid=KID, scope="gmail.full")
        resp = client.get(MESSAGES_URL, headers=bearer(token))
        assert resp.status_code == 401

    def test_token_without_scope_claim_403_not_500(self, client, private_key):
        token = make_jwt(private_key=private_key, kid=KID, scope="")
        resp = client.get(MESSAGES_URL, headers=bearer(token))
        assert resp.status_code == 403
        assert resp.json()["error"]["required_scopes"]


# ---------------------------------------------------------------------------
class TestTrailingSlashScopeEnforcement:
    def test_trailing_slash_cannot_bypass_scope_check(self, client, private_key):
        # The slashed path has no FULL route match (auth-only pass), but the
        # router answers with a 307 redirect carrying no data; following it
        # re-enters the middleware where the scope check applies.
        low = make_jwt(private_key=private_key, kid=KID, scope="calendar.readonly")
        resp = client.get(MESSAGES_URL + "/", headers=bearer(low), follow_redirects=False)
        assert resp.status_code in (307, 404)
        if resp.status_code == 307:
            followed = client.get(MESSAGES_URL + "/", headers=bearer(low),
                                  follow_redirects=True)
            assert followed.status_code == 403

    def test_trailing_slash_with_proper_scope_succeeds(self, client, private_key):
        ok = make_jwt(private_key=private_key, kid=KID, scope="gmail.readonly")
        resp = client.get(MESSAGES_URL + "/", headers=bearer(ok), follow_redirects=True)
        assert resp.status_code in (200, 404)  # 200 via redirect, 404 if no redirect_slashes
        if resp.status_code == 200:
            assert resp.json()["auth_user_id"] == "user_001"


# ---------------------------------------------------------------------------
class TestJWKSThunderingHerd:
    def test_concurrent_cold_cache_single_fetch(self, public_key):
        calls = {"n": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            calls["n"] += 1
            return httpx.Response(200, json=jwks_for(public_key, kid=KID))

        cache = JWKSCache(auth_base_url="http://auth.test",
                          transport=httpx.MockTransport(handler), ttl=300)

        async def hammer():
            await asyncio.gather(*(cache.get_key(KID) for _ in range(16)))

        asyncio.run(hammer())
        assert calls["n"] == 1, f"thundering herd: {calls['n']} fetches for a cold cache"

    def test_unknown_kid_still_single_refetch(self, public_key):
        calls = {"n": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            calls["n"] += 1
            return httpx.Response(200, json=jwks_for(public_key, kid=KID))

        cache = JWKSCache(auth_base_url="http://auth.test",
                          transport=httpx.MockTransport(handler), ttl=300)

        async def go():
            await cache.get_key(KID)  # cold fetch (1)
            with pytest.raises(Exception):
                await cache.get_key("nope")  # exactly one refetch (2)

        asyncio.run(go())
        assert calls["n"] == 2


# ---------------------------------------------------------------------------
class TestReportingLiveness:
    """BaseHTTPMiddleware awaits report POSTs inline; ensure no deadlock or
    request failure under TestClient, including when the auth server is down."""

    def test_many_requests_with_reporting_on_no_hang(self, jwks, private_key,
                                                     report_capture):
        app = build_app(jwks_static=jwks)
        token = make_jwt(private_key=private_key, kid=KID, scope="gmail.readonly")
        with TestClient(app) as client:
            for _ in range(45):  # crosses two aggregation flush windows
                assert client.get(MESSAGES_URL, headers=bearer(token)).status_code == 200
        kinds = {e["json"]["event_type"] for e in report_capture}
        assert kinds == {"resource_access"}
        total = sum(e["json"]["details"]["count"] for e in report_capture)
        assert 0 < total <= 45

    def test_reporting_to_unreachable_auth_server_swallowed(self, monkeypatch,
                                                            jwks, private_key):
        # Reporting ON, no transport stub: real httpx POST to a closed port.
        monkeypatch.setenv("AUTH_REPORT", "1")
        monkeypatch.setenv("AUTH_URL", "http://127.0.0.1:9319")
        app = build_app(jwks_static=jwks, auth_base_url="http://127.0.0.1:9319")
        token = make_jwt(private_key=private_key, kid=KID, scope="gmail.readonly",
                         issuer="http://127.0.0.1:9319")
        with TestClient(app) as client:
            resp = client.get(MESSAGES_URL, headers=bearer(token))
        assert resp.status_code == 200  # connection-refused report is swallowed

    def test_concurrent_testclient_threads_no_deadlock(self, jwks, private_key,
                                                       report_capture):
        app = build_app(jwks_static=jwks)
        token = make_jwt(private_key=private_key, kid=KID, scope="gmail.readonly")
        statuses: list[int] = []
        lock = threading.Lock()

        def worker(client):
            for _ in range(5):
                code = client.get(MESSAGES_URL, headers=bearer(token)).status_code
                with lock:
                    statuses.append(code)

        with TestClient(app) as client:
            threads = [threading.Thread(target=worker, args=(client,)) for _ in range(4)]
            for t in threads:
                t.start()
            for t in threads:
                t.join(timeout=30)
            assert not any(t.is_alive() for t in threads), "deadlocked threads"
        assert statuses.count(200) == 20
