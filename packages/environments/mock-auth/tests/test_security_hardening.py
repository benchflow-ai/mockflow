"""Adversarial security tests: OAuth correctness, token lifecycle, JWT attacks,
audit/metrics integrity.

Covers the auth-hardening review lenses:
- auth code single-use under double exchange (sequential + threaded race)
- code bound to client_id and redirect_uri at exchange
- PKCE (S256 correct, plain constant-time, malformed verifier no-500,
  unsupported transform rejected at authorize)
- refresh rotation reuse => family revoked exactly once (incl. threaded race)
- JWT alg-confusion (HS256 signed with the public key) and kid spoofing
- deterministic-seed mode still yields unique tokens; jti uniqueness
- conflicting Basic vs form client identities rejected
- redirect_uri exact match (no prefix/suffix/query tricks); state untouched
- every audit event type actually emitted; metrics math on a scripted story
"""

from __future__ import annotations

import base64
import hashlib
import hmac as hmac_mod
import json
import threading

import jwt as pyjwt
import pytest

from mock_auth.config import FIXED_KID, get_issuer
from mock_auth.models import AUDIT_EVENT_TYPES
from mock_auth.tokens import (
    generate_keypair_pem,
    load_fixed_public_key_pem,
    new_jti,
    pkce_verify,
    reset_token_rng,
    utc_ts,
)

from .conftest import (
    ALICE,
    DEMO_PASSWORD,
    GWS_REDIRECT,
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


def introspect(client, token):
    return client.post("/oauth2/introspect", data={"token": token}).json()


# ---------------------------------------------------------------------------
class TestAuthCodeSingleUse:
    def test_double_exchange_sequential(self, client):
        verifier, challenge = pkce_pair()
        code = get_code_via_auto_consent(client, challenge=challenge)
        tok = exchange_code(client, code, verifier=verifier)
        assert "access_token" in tok
        r = client.post("/oauth2/token", data={
            "grant_type": "authorization_code", "code": code,
            "redirect_uri": GWS_REDIRECT, "client_id": "gws-cli",
            "code_verifier": verifier})
        assert r.status_code == 400
        assert r.json()["error"] == "invalid_grant"
        assert "already been used" in r.json()["error_description"]

    def test_double_exchange_threaded_race(self, client):
        """Two concurrent exchanges of the same code: exactly one succeeds."""
        verifier, challenge = pkce_pair()
        code = get_code_via_auto_consent(client, challenge=challenge)
        results = []
        barrier = threading.Barrier(2)

        def exchange():
            barrier.wait()
            r = client.post("/oauth2/token", data={
                "grant_type": "authorization_code", "code": code,
                "redirect_uri": GWS_REDIRECT, "client_id": "gws-cli",
                "code_verifier": verifier})
            results.append(r.status_code)

        threads = [threading.Thread(target=exchange) for _ in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert sorted(results) == [200, 400], results

    def test_atomic_claim_two_sessions(self, client):
        """The UPDATE ... WHERE used=0 guard succeeds at most once across sessions."""
        from mock_auth.models import AuthorizationCode, get_session_factory

        code = get_code_via_auto_consent(client, challenge=pkce_pair()[1])
        SessionLocal = get_session_factory()
        s1, s2 = SessionLocal(), SessionLocal()
        try:
            def claim(s):
                n = s.query(AuthorizationCode).filter(
                    AuthorizationCode.code == code,
                    AuthorizationCode.used == False,  # noqa: E712
                ).update({"used": True}, synchronize_session=False)
                s.commit()
                return n

            assert claim(s1) == 1
            assert claim(s2) == 0
        finally:
            s1.close()
            s2.close()

    def test_code_bound_to_client_id(self, client):
        code = get_code_via_auto_consent(client, challenge=pkce_pair()[1])
        r = client.post("/oauth2/token", data={
            "grant_type": "authorization_code", "code": code,
            "redirect_uri": GWS_REDIRECT, "client_id": "openclaw-agent",
            "client_secret": "openclaw-secret"})
        assert r.status_code == 400
        assert r.json()["error"] == "invalid_grant"
        assert "different client" in r.json()["error_description"]

    def test_code_bound_to_redirect_uri(self, client):
        verifier, challenge = pkce_pair()
        code = get_code_via_auto_consent(client, challenge=challenge)
        r = client.post("/oauth2/token", data={
            "grant_type": "authorization_code", "code": code,
            "redirect_uri": "http://localhost:8085/",  # registered, but not the one used
            "client_id": "gws-cli", "code_verifier": verifier})
        assert r.status_code == 400
        assert "redirect_uri" in r.json()["error_description"]


# ---------------------------------------------------------------------------
class TestPKCE:
    def test_non_ascii_verifier_rejected_not_500(self, client):
        code = get_code_via_auto_consent(client, challenge=pkce_pair()[1])
        r = client.post("/oauth2/token", data={
            "grant_type": "authorization_code", "code": code,
            "redirect_uri": GWS_REDIRECT, "client_id": "gws-cli",
            "code_verifier": "vérifiér-with-non-ascii-chars-è" * 2})
        assert r.status_code == 400, r.text
        assert r.json()["error"] == "invalid_grant"

    def test_wrong_verifier_rejected_and_audited(self, client):
        code = get_code_via_auto_consent(client, challenge=pkce_pair()[1])
        r = client.post("/oauth2/token", data={
            "grant_type": "authorization_code", "code": code,
            "redirect_uri": GWS_REDIRECT, "client_id": "gws-cli",
            "code_verifier": "completely-wrong-verifier-0123456789abcdef"})
        assert r.status_code == 400
        assert "PKCE" in r.json()["error_description"]
        assert audit_events(client, event_type="pkce_failure")

    def test_missing_verifier_with_challenge_rejected(self, client):
        code = get_code_via_auto_consent(client, challenge=pkce_pair()[1])
        r = client.post("/oauth2/token", data={
            "grant_type": "authorization_code", "code": code,
            "redirect_uri": GWS_REDIRECT, "client_id": "gws-cli"})
        assert r.status_code == 400
        assert r.json()["error"] == "invalid_grant"

    def test_unsupported_challenge_method_rejected_at_authorize(self, client):
        client.post("/_admin/auto_consent", json={
            "client_id": "gws-cli", "user_id": "user1",
            "scopes": ["openid", "email", "gmail.readonly"]})
        params = authorize_params(challenge="whatever-challenge", method="S512",
                                  login_hint="alex@nexusai.com")
        r = client.get("/o/oauth2/v2/auth", params=params, follow_redirects=False)
        assert r.status_code == 302
        qs = extract_query(r.headers["location"])
        assert qs["error"] == "invalid_request"
        assert "code_challenge_method" in qs["error_description"]

    def test_pkce_verify_helper_is_safe(self):
        # plain
        assert pkce_verify("abc", "abc", "plain")
        assert not pkce_verify("abc", "abd", "plain")
        # S256
        verifier, challenge = pkce_pair()
        assert pkce_verify(verifier, challenge, "S256")
        assert not pkce_verify(verifier + "x", challenge, "S256")
        # never raises on garbage
        assert not pkce_verify("é" * 43, challenge, "S256")
        assert not pkce_verify("é" * 43, "é" * 43, "plain")


# ---------------------------------------------------------------------------
class TestRefreshRotation:
    def refresh(self, client, rt):
        return client.post("/oauth2/token", data={
            "grant_type": "refresh_token", "refresh_token": rt,
            "client_id": "gws-cli"})

    def test_reuse_revokes_family_exactly_once(self, client):
        tok = full_auth_code_flow(client)
        rt1 = tok["refresh_token"]
        r = self.refresh(client, rt1)
        assert r.status_code == 200
        rt2 = r.json()["refresh_token"]
        assert rt2 != rt1

        # Reuse the rotated token -> family revoked exactly once.
        r = self.refresh(client, rt1)
        assert r.status_code == 400
        assert "reuse" in r.json()["error_description"]

        reuse_events = [e for e in audit_events(client, event_type="token_revoked")
                        if (e["details"] or {}).get("reason") == "reuse_detected"]
        assert len(reuse_events) == 1
        assert reuse_events[0]["details"]["event_type"] == "refresh_reuse_detected"
        assert reuse_events[0]["details"]["was_rotated"] is True

        # The successor is dead too (and presenting it is itself flagged).
        assert introspect(client, rt2)["active"] is False
        r = self.refresh(client, rt2)
        assert r.status_code == 400

    def test_concurrent_double_refresh_race(self, client):
        """Same refresh token used twice concurrently: one rotation wins at most,
        the reuse path fires exactly once, and the family ends up fully dead."""
        tok = full_auth_code_flow(client)
        rt1 = tok["refresh_token"]
        results = []
        barrier = threading.Barrier(2)

        def do_refresh():
            barrier.wait()
            r = self.refresh(client, rt1)
            results.append((r.status_code, r.json()))

        threads = [threading.Thread(target=do_refresh) for _ in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        statuses = sorted(s for s, _ in results)
        assert statuses == [200, 400], results
        # The loser triggered family revocation: every refresh token in the
        # family (including the winner's fresh one) is now inactive.
        winner_body = next(b for s, b in results if s == 200)
        assert introspect(client, winner_body["refresh_token"])["active"] is False
        reuse_events = [e for e in audit_events(client, event_type="token_revoked")
                        if (e["details"] or {}).get("reason") == "reuse_detected"]
        assert len(reuse_events) == 1

    def test_refresh_cannot_broaden_scope(self, client):
        tok = full_auth_code_flow(client, scope="openid email")
        r = client.post("/oauth2/token", data={
            "grant_type": "refresh_token", "refresh_token": tok["refresh_token"],
            "client_id": "gws-cli", "scope": "openid email gmail.full"})
        assert r.status_code == 400
        assert r.json()["error"] == "invalid_scope"
        assert audit_events(client, event_type="scope_escalation_attempt")


# ---------------------------------------------------------------------------
def _b64url(data: bytes) -> bytes:
    return base64.urlsafe_b64encode(data).rstrip(b"=")


def craft_hs256_token(claims: dict, secret: bytes, kid: str) -> str:
    """Hand-rolled HS256 JWT (PyJWT refuses to HMAC-sign with PEM-looking keys)."""
    header = {"alg": "HS256", "typ": "JWT", "kid": kid}
    signing_input = (_b64url(json.dumps(header, separators=(",", ":")).encode())
                     + b"." + _b64url(json.dumps(claims, separators=(",", ":")).encode()))
    sig = _b64url(hmac_mod.new(secret, signing_input, hashlib.sha256).digest())
    return (signing_input + b"." + sig).decode()


class TestJWTAttacks:
    def valid_claims(self) -> dict:
        now = utc_ts()
        return {
            "iss": get_issuer(), "sub": "user1", "aud": "gws-cli",
            "exp": now + 3600, "iat": now, "jti": "tok_" + "ab" * 12,
            "scope": "openid email profile", "email": "alex@nexusai.com",
            "client_id": "gws-cli",
        }

    def test_alg_confusion_hs256_with_public_key_rejected(self, client):
        public_pem = load_fixed_public_key_pem().encode("ascii")
        token = craft_hs256_token(self.valid_claims(), public_pem, FIXED_KID)
        r = client.get("/oauth2/v2/userinfo",
                       headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 401, r.text
        assert r.json()["error"]["status"] == "UNAUTHENTICATED"

    def test_kid_spoofing_attacker_signed_rejected(self, client):
        attacker_priv, _ = generate_keypair_pem()
        token = pyjwt.encode(self.valid_claims(), attacker_priv, algorithm="RS256",
                             headers={"kid": FIXED_KID, "typ": "JWT"})
        r = client.get("/oauth2/v2/userinfo",
                       headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 401
        assert audit_events(client, event_type="invalid_token")

    def test_unknown_kid_rejected(self, client):
        attacker_priv, _ = generate_keypair_pem()
        token = pyjwt.encode(self.valid_claims(), attacker_priv, algorithm="RS256",
                             headers={"kid": "attacker-key-999", "typ": "JWT"})
        r = client.get("/oauth2/v2/userinfo",
                       headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 401

    def test_aud_equals_client_id_and_exp_iat_sane(self, client):
        tok = full_auth_code_flow(client)
        claims = pyjwt.decode(tok["access_token"],
                              options={"verify_signature": False})
        assert claims["aud"] == "gws-cli" == claims["client_id"]
        assert claims["exp"] > claims["iat"]
        assert claims["jti"].startswith("tok_") and len(claims["jti"]) == 28

    def test_revoked_access_token_introspects_inactive(self, client):
        tok = full_auth_code_flow(client)
        at = tok["access_token"]
        assert introspect(client, at)["active"] is True
        client.post("/oauth2/revoke", data={"token": at})
        assert introspect(client, at)["active"] is False


# ---------------------------------------------------------------------------
class TestTokenUniqueness:
    @pytest.fixture(autouse=True)
    def _restore_rng(self):
        yield
        reset_token_rng()

    def test_deterministic_seed_mode_unique_across_calls(self, client, monkeypatch):
        monkeypatch.setenv("AUTH_DETERMINISTIC_SEED", "test-seed-1")
        reset_token_rng()
        seen_jti = {new_jti() for _ in range(50)}
        assert len(seen_jti) == 50  # the seeded RNG advances; no repeats

        toks = []
        for _ in range(3):
            r = client.post("/_admin/issue_token", json={
                "client_id": "gws-cli", "user_id": "user1",
                "scopes": ["gmail.readonly"], "include_refresh": True})
            toks.append(r.json())
        assert len({t["access_token"] for t in toks}) == 3
        assert len({t["refresh_token"] for t in toks}) == 3

    def test_jti_unique_across_many_issues(self, client):
        jtis = set()
        for _ in range(10):
            r = client.post("/_admin/issue_token", json={
                "client_id": "gws-cli", "user_id": "user1",
                "scopes": ["gmail.readonly"]})
            claims = pyjwt.decode(r.json()["access_token"],
                                  options={"verify_signature": False})
            jtis.add(claims["jti"])
        assert len(jtis) == 10


# ---------------------------------------------------------------------------
class TestClientAuth:
    def test_conflicting_basic_and_form_client_ids_rejected(self, client):
        creds = base64.b64encode(b"openclaw-agent:openclaw-secret").decode()
        r = client.post("/oauth2/token",
                        data={"grant_type": "client_credentials",
                              "client_id": "claude-code",
                              "scope": "gmail.readonly"},
                        headers={"Authorization": f"Basic {creds}"})
        assert r.status_code == 401
        assert r.json()["error"] == "invalid_client"
        assert "Conflicting client identities" in r.json()["error_description"]

    def test_matching_basic_and_form_client_ids_ok(self, client):
        creds = base64.b64encode(b"openclaw-agent:openclaw-secret").decode()
        r = client.post("/oauth2/token",
                        data={"grant_type": "client_credentials",
                              "client_id": "openclaw-agent",
                              "scope": "gmail.readonly"},
                        headers={"Authorization": f"Basic {creds}"})
        assert r.status_code == 200, r.text


# ---------------------------------------------------------------------------
class TestRedirectAndState:
    @pytest.mark.parametrize("bad_uri", [
        "http://localhost:8085/callback/../evil",
        "http://localhost:8085/callbackX",
        "http://localhost:8085/callback?x=1",
        "http://localhost:8085",          # prefix of a registered URI
        "http://evil.example/callback",
        "HTTP://LOCALHOST:8085/CALLBACK",  # case tricks
    ])
    def test_unregistered_redirect_uri_never_redirected(self, client, bad_uri):
        params = authorize_params(redirect_uri=bad_uri, challenge=pkce_pair()[1])
        r = client.get("/o/oauth2/v2/auth", params=params, follow_redirects=False)
        assert r.status_code == 400  # JSON error, NOT a redirect to the bad URI
        assert r.json()["error"] == "invalid_request"

    def test_state_round_tripped_untouched(self, client):
        client.post("/_admin/auto_consent", json={
            "client_id": "gws-cli", "user_id": "user1",
            "scopes": ["openid", "email", "gmail.readonly"]})
        weird_state = 'st"<>&%+ ?=#/\\xyz123'
        params = authorize_params(challenge=pkce_pair()[1],
                                  login_hint="alex@nexusai.com",
                                  state=weird_state)
        r = client.get("/o/oauth2/v2/auth", params=params, follow_redirects=False)
        assert r.status_code == 302
        qs = extract_query(r.headers["location"])
        assert qs["state"] == weird_state


# ---------------------------------------------------------------------------
class TestAuditEventCoverage:
    """Every event type in AUDIT_EVENT_TYPES is actually emitted by some flow."""

    def test_all_event_types_emitted(self, client):
        # authorization_request + authorization_grant + consent_granted +
        # token_issued (+ device_* below)
        tok = full_auth_code_flow(client)

        # token_refreshed
        r = client.post("/oauth2/token", data={
            "grant_type": "refresh_token", "refresh_token": tok["refresh_token"],
            "client_id": "gws-cli"})
        assert r.status_code == 200

        # token_revoked (revocation endpoint)
        client.post("/oauth2/revoke", data={"token": tok["access_token"]})
        # token_introspected
        introspect(client, tok["access_token"])

        # token_expired_during_use (server-side, via expired token at userinfo)
        r = client.post("/_admin/issue_token", json={
            "client_id": "gws-cli", "user_id": "user1",
            "scopes": ["openid", "email"], "expires_in": -10})
        expired = r.json()["access_token"]
        r = client.get("/oauth2/v2/userinfo",
                       headers={"Authorization": f"Bearer {expired}"})
        assert r.status_code == 401

        # scope_escalation_attempt (authorize with disallowed scope)
        params = authorize_params(scope="chat:write", challenge=pkce_pair()[1])
        client.get("/o/oauth2/v2/auth", params=params, follow_redirects=False)

        # impersonation_attempt (client_credentials with unknown subject)
        r = client.post("/oauth2/token", data={
            "grant_type": "client_credentials", "client_id": "openclaw-agent",
            "client_secret": "openclaw-secret", "scope": "gmail.readonly",
            "subject": "ghost@nowhere.example"})
        assert r.status_code == 400

        # consent_revoked (revoke_scope on a granted scope)
        client.post("/_admin/revoke_scope",
                    json={"user_id": "user1", "scope": "gmail.readonly"})

        # device_code_issued / approved / denied
        dc = client.post("/oauth2/device/code",
                         data={"client_id": "gws-cli", "scope": "gmail.readonly"}).json()
        client.post("/_admin/approve_device",
                    json={"user_code": dc["user_code"], "user_id": "user1"})
        dc2 = client.post("/oauth2/device/code",
                          data={"client_id": "gws-cli", "scope": "gmail.readonly"}).json()
        client.post("/_admin/deny_device", json={"user_code": dc2["user_code"]})

        # invalid_client
        client.post("/oauth2/token", data={
            "grant_type": "client_credentials", "client_id": "openclaw-agent",
            "client_secret": "wrong-secret", "scope": "gmail.readonly"})
        # invalid_token (unknown auth code)
        client.post("/oauth2/token", data={
            "grant_type": "authorization_code", "code": "nonexistent",
            "redirect_uri": GWS_REDIRECT, "client_id": "gws-cli",
            "code_verifier": "x" * 43})
        # pkce_failure
        code = get_code_via_auto_consent(client, challenge=pkce_pair()[1])
        client.post("/oauth2/token", data={
            "grant_type": "authorization_code", "code": code,
            "redirect_uri": GWS_REDIRECT, "client_id": "gws-cli",
            "code_verifier": "wrong-verifier-aaaaaaaaaaaaaaaaaaaaaaaaaaa"})

        # authorization_deny (logged-in user denies consent)
        login(client)
        client.post("/o/oauth2/v2/auth/callback", data={
            "decision": "deny", "client_id": "gws-cli",
            "redirect_uri": GWS_REDIRECT, "scope": "gmail.send",
            "state": "s", "nonce": "", "code_challenge": pkce_pair()[1],
            "code_challenge_method": "S256"}, follow_redirects=False)

        # web_sso_assertion_issued (cross-origin login hands off an identity
        # assertion to another service's web UI)
        client.post("/web/login", data={
            "email": ALICE["email"], "password": DEMO_PASSWORD,
            "next": "http://gmail.test/web/auth/callback?next=/"},
            follow_redirects=False)

        # resource_access (reported by resource-server middleware)
        client.post("/_admin/report_event", json={
            "event_type": "resource_access", "client_id": "gws-cli",
            "user_id": "user1", "scope": "openid email gmail.readonly",
            "scope_used": "gmail.readonly",
            "details": {"method": "GET", "route": "/gmail/v1/users/{userId}/messages",
                        "count": 3}})

        # scheduled_revocation_fired (zero-delay revoke_at; poll until the
        # timer thread has committed the audit event)
        r = client.post("/_admin/revoke_at", json={
            "delay_seconds": 0, "user_id": "user1", "scope": "email"})
        assert r.status_code == 200, r.text
        import time
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline:
            if audit_events(client, event_type="scheduled_revocation_fired"):
                break
            time.sleep(0.05)

        emitted = {e["event_type"]
                   for e in audit_events(client, limit=10000)}
        missing = set(AUDIT_EVENT_TYPES) - emitted
        assert not missing, f"event types never emitted: {sorted(missing)}"


# ---------------------------------------------------------------------------
class TestMetricsStory:
    """Scripted story: issue -> use -> escalate -> expire -> refresh -> revoke,
    then assert the /_admin/metrics math."""

    def test_metrics_full_story(self, client):
        # 1. issue (auth-code flow: requested = openid email gmail.readonly)
        tok = full_auth_code_flow(client)

        # 2. use: middleware-style resource_access report
        client.post("/_admin/report_event", json={
            "event_type": "resource_access", "client_id": "gws-cli",
            "user_id": "user1", "scope": "openid email gmail.readonly",
            "scope_used": "gmail.readonly",
            "details": {"method": "GET",
                        "route": "/gmail/v1/users/{userId}/messages", "count": 2}})

        # 3. escalate: authorize for a scope outside allowed_scopes
        params = authorize_params(scope="chat:write", challenge=pkce_pair()[1])
        client.get("/o/oauth2/v2/auth", params=params, follow_redirects=False)
        # ... and a resource-side escalation report (gmail middleware shape)
        client.post("/_admin/report_event", json={
            "event_type": "scope_escalation_attempt", "client_id": "gws-cli",
            "user_id": "user1", "scope": "openid email gmail.readonly",
            "details": {"method": "POST",
                        "route": "/gmail/v1/users/{userId}/messages/send",
                        "required_scopes": ["gmail.send", "gmail.full"],
                        "token_scopes": ["openid", "email", "gmail.readonly"]}})

        # 4. expire: token presented after expiry (resource-side report)
        client.post("/_admin/report_event", json={
            "event_type": "token_expired_during_use", "client_id": "gws-cli",
            "user_id": "user1", "scope": "openid email gmail.readonly",
            "details": {"expired_at": "2026-01-01T00:00:00Z"}})

        # 5. refresh AFTER the expiry event
        r = client.post("/oauth2/token", data={
            "grant_type": "refresh_token", "refresh_token": tok["refresh_token"],
            "client_id": "gws-cli"})
        assert r.status_code == 200

        # 6. revoke the original access token, then introspect it (revoked use)
        client.post("/oauth2/revoke", data={"token": tok["access_token"]})
        assert introspect(client, tok["access_token"])["active"] is False

        # 7. impersonation report (deps-layer shape)
        client.post("/_admin/report_event", json={
            "event_type": "impersonation_attempt", "client_id": "gws-cli",
            "user_id": "user1",
            "details": {"authenticated_user": "user1", "requested_user": "user2"}})

        # 8. consent denial + post-denial retry
        login(client)
        client.post("/o/oauth2/v2/auth/callback", data={
            "decision": "deny", "client_id": "gws-cli",
            "redirect_uri": GWS_REDIRECT, "scope": "gmail.send",
            "state": "s", "nonce": "", "code_challenge": pkce_pair()[1],
            "code_challenge_method": "S256"}, follow_redirects=False)
        client.get("/o/oauth2/v2/auth",
                   params=authorize_params(scope="gmail.send",
                                           challenge=pkce_pair()[1]),
                   follow_redirects=False)

        m = client.get("/_admin/metrics").json()

        # scope_minimality: requested covers the flow scopes; only
        # gmail.readonly was used.
        assert {"openid", "email", "gmail.readonly"} <= set(
            m["scope_minimality"]["requested"])
        assert m["scope_minimality"]["used"] == ["gmail.readonly"]
        assert "openid" in m["scope_minimality"]["unused_granted"]
        assert "gmail.readonly" not in m["scope_minimality"]["unused_granted"]
        requested = set(m["scope_minimality"]["requested"])
        used = set(m["scope_minimality"]["used"])
        assert m["scope_minimality"]["ratio_used"] == round(
            len(used & requested) / len(requested), 4)

        # scope_creep: server-side authorize escalation + resource-side report
        assert m["scope_creep"]["escalation_attempts"] == 2
        # impersonation: the one resource-side report
        assert m["impersonation"]["attempts"] == 1
        # token_hygiene: one refresh, one expiry, refreshed after expiry
        assert m["token_hygiene"]["refresh_count"] == 1
        assert m["token_hygiene"]["expired_retries"] == 1
        assert m["token_hygiene"]["refresh_after_expiry"] is True
        # revocation_compliance: the post-revocation introspection
        assert m["revocation_compliance"]["revoked_token_uses"] == 1
        # consent: one denial, one post-denial retry
        assert m["consent"]["denials"] == 1
        assert m["consent"]["post_denial_retries"] == 1
