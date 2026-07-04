"""Tests for the user-facing /v1/myaccount surface and /_admin/revoke_at.

Covers: Bearer validation (mirrors userinfo), openid-scope gating, cross-user
isolation via two tokens (the token IS the identity), consent/app revocation
with family token revocation, per-session revocation reflected in
introspection + metrics, security-event feed, and scheduled revocation
(fires within tolerance, listable, cancellable).
"""

from __future__ import annotations

import time

import jwt as pyjwt

from tests.conftest import full_auth_code_flow


# --- helpers ---------------------------------------------------------------

def issue(client, user_id, scopes, *, client_id="gws-cli", expires_in=None,
          include_refresh=False):
    body = {"client_id": client_id, "user_id": user_id, "scopes": scopes,
            "include_refresh": include_refresh}
    if expires_in is not None:
        body["expires_in"] = expires_in
    r = client.post("/_admin/issue_token", json=body)
    assert r.status_code == 200, r.text
    return r.json()


def consent(client, user_id, client_id, scopes):
    r = client.post("/_admin/auto_consent", json={
        "client_id": client_id, "user_id": user_id, "scopes": scopes})
    assert r.status_code == 200, r.text


def auth(token):
    return {"Authorization": f"Bearer {token}"}


def jti_of(token):
    return pyjwt.decode(token, options={"verify_signature": False})["jti"]


def introspect(client, token):
    return client.post("/oauth2/introspect", data={"token": token}).json()


def audit_events(client, **params):
    return client.get("/_admin/audit_log", params=params).json()["events"]


def wait_for(predicate, timeout=5.0, interval=0.05):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return False


def user1_setup(client, *, include_refresh=True):
    """Consent + token for user1 on gws-cli (openid email gmail.readonly)."""
    scopes = ["openid", "email", "gmail.readonly"]
    consent(client, "user1", "gws-cli", scopes)
    return issue(client, "user1", scopes, include_refresh=include_refresh)


def user2_setup(client, *, include_refresh=False):
    scopes = ["openid", "email"]
    consent(client, "user2", "gws-cli", scopes)
    return issue(client, "user2", scopes, include_refresh=include_refresh)


# ---------------------------------------------------------------------------
class TestMyAccountBearerAuth:
    """Explicit Bearer validation — mirrors userinfo's behavior exactly."""

    def test_missing_token_401(self, client):
        r = client.get("/v1/myaccount/apps")
        assert r.status_code == 401
        body = r.json()["error"]
        assert body["code"] == 401 and body["status"] == "UNAUTHENTICATED"
        assert "www-authenticate" in {k.lower() for k in r.headers}

    def test_malformed_token_401(self, client):
        r = client.get("/v1/myaccount/sessions", headers=auth("not-a-jwt"))
        assert r.status_code == 401
        assert r.json()["error"]["status"] == "UNAUTHENTICATED"

    def test_expired_token_401_with_refresh_hint(self, client):
        tok = issue(client, "user1", ["openid"], expires_in=-10)
        r = client.get("/v1/myaccount/apps", headers=auth(tok["access_token"]))
        assert r.status_code == 401
        err = r.json()["error"]
        assert "expired at" in err["message"]
        assert "grant_type=refresh_token" in err["hint"]
        assert "/oauth2/token" in err["hint"]

    def test_revoked_token_401(self, client):
        tok = issue(client, "user1", ["openid"])
        client.post("/oauth2/revoke", data={"token": tok["access_token"]})
        r = client.get("/v1/myaccount/apps", headers=auth(tok["access_token"]))
        assert r.status_code == 401
        assert "revoked" in r.json()["error"]["message"].lower()

    def test_token_without_openid_403(self, client):
        tok = issue(client, "user1", ["gmail.readonly"])
        r = client.get("/v1/myaccount/apps", headers=auth(tok["access_token"]))
        assert r.status_code == 403
        err = r.json()["error"]
        assert err["status"] == "PERMISSION_DENIED"
        assert err["required_scopes"] == ["openid"]
        assert err["token_scopes"] == ["gmail.readonly"]

    def test_openid_scope_is_sufficient(self, client):
        tok = issue(client, "user1", ["openid"])
        for path in ("/v1/myaccount/apps", "/v1/myaccount/sessions",
                     "/v1/myaccount/security_events"):
            r = client.get(path, headers=auth(tok["access_token"]))
            assert r.status_code == 200, (path, r.text)
            assert r.json()["user_id"] == "user1"

    def test_unbound_client_credentials_token_403(self, client):
        r = client.post("/oauth2/token", data={
            "grant_type": "client_credentials", "client_id": "openclaw-agent",
            "client_secret": "openclaw-secret", "scope": "openid"})
        assert r.status_code == 200, r.text
        tok = r.json()["access_token"]
        r = client.get("/v1/myaccount/apps", headers=auth(tok))
        assert r.status_code == 403
        assert "not bound to a user" in r.json()["error"]["message"]

    def test_real_oauth_flow_token_works(self, client):
        tok = full_auth_code_flow(client)  # user1, gws-cli, openid email gmail.readonly
        r = client.get("/v1/myaccount/apps", headers=auth(tok["access_token"]))
        assert r.status_code == 200
        assert r.json()["user_id"] == "user1"
        assert [a["client_id"] for a in r.json()["apps"]] == ["gws-cli"]


# ---------------------------------------------------------------------------
class TestMyAccountApps:

    def test_lists_consented_clients_with_fields(self, client):
        tok = user1_setup(client)
        consent(client, "user1", "claude-code", ["openid", "calendar.readonly"])
        r = client.get("/v1/myaccount/apps", headers=auth(tok["access_token"]))
        assert r.status_code == 200
        apps = {a["client_id"]: a for a in r.json()["apps"]}
        assert set(apps) == {"gws-cli", "claude-code"}

        gws = apps["gws-cli"]
        assert gws["client_name"] == "Google Workspace CLI"
        assert set(gws["granted_scopes"]) == {"openid", "email", "gmail.readonly"}
        assert gws["granted_at"]  # ISO timestamp
        assert "last_used_at" in gws
        assert gws["token_count"] == 1  # the one active token we issued

        cc = apps["claude-code"]
        assert cc["token_count"] == 0  # consent without tokens

    def test_token_count_tracks_active_tokens_only(self, client):
        tok = user1_setup(client)
        extra = issue(client, "user1", ["openid", "email"])
        expired = issue(client, "user1", ["openid"], expires_in=-10)  # noqa: F841
        r = client.get("/v1/myaccount/apps", headers=auth(tok["access_token"]))
        gws = r.json()["apps"][0]
        assert gws["token_count"] == 2  # expired one not counted

        client.post("/oauth2/revoke", data={"token": extra["access_token"]})
        r = client.get("/v1/myaccount/apps", headers=auth(tok["access_token"]))
        assert r.json()["apps"][0]["token_count"] == 1  # revoked one dropped

    def test_cross_user_isolation(self, client):
        user1_setup(client)
        consent(client, "user1", "claude-code", ["openid"])
        tok2 = user2_setup(client)
        r = client.get("/v1/myaccount/apps", headers=auth(tok2["access_token"]))
        assert r.status_code == 200
        body = r.json()
        assert body["user_id"] == "user2"
        # user2 sees ONLY user2's consent — none of user1's
        assert [a["client_id"] for a in body["apps"]] == ["gws-cli"]
        assert set(body["apps"][0]["granted_scopes"]) == {"openid", "email"}


# ---------------------------------------------------------------------------
class TestMyAccountAppRevoke:

    def test_revoke_kills_consent_and_tokens(self, client):
        gws_tok = user1_setup(client, include_refresh=True)
        consent(client, "user1", "claude-code", ["openid"])
        cc_tok = issue(client, "user1", ["openid"], client_id="claude-code")

        # use the claude-code token to revoke the gws-cli grant
        r = client.post("/v1/myaccount/apps/gws-cli/revoke",
                        headers=auth(cc_tok["access_token"]))
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["status"] == "ok"
        assert body["revoked_access_tokens"] == 1
        assert body["revoked_refresh_tokens"] == 1

        # introspection reflects it (access token + refresh family)
        assert introspect(client, gws_tok["access_token"]) == {"active": False}
        assert introspect(client, gws_tok["refresh_token"]) == {"active": False}

        # consent gone from the user-facing list AND the admin list
        r = client.get("/v1/myaccount/apps", headers=auth(cc_tok["access_token"]))
        assert [a["client_id"] for a in r.json()["apps"]] == ["claude-code"]
        admin = client.get("/_admin/clients", params={"user_id": "user1"}).json()
        assert "gws-cli" not in [c["client_id"] for c in admin["clients"]]

        # audited
        ev = audit_events(client, event_type="consent_revoked",
                          client_id="gws-cli", user_id="user1")
        assert ev and ev[0]["details"]["via"] == "myaccount"
        assert ev[0]["details"]["partial"] is False

    def test_revoked_refresh_token_cannot_refresh(self, client):
        gws_tok = user1_setup(client, include_refresh=True)
        cc_tok = issue(client, "user1", ["openid"], client_id="claude-code")
        client.post("/v1/myaccount/apps/gws-cli/revoke",
                    headers=auth(cc_tok["access_token"]))
        r = client.post("/oauth2/token", data={
            "grant_type": "refresh_token",
            "refresh_token": gws_tok["refresh_token"], "client_id": "gws-cli"})
        assert r.status_code == 400
        assert r.json()["error"] == "invalid_grant"

    def test_second_revoke_404(self, client):
        user1_setup(client)
        cc_tok = issue(client, "user1", ["openid"], client_id="claude-code")
        consent(client, "user1", "claude-code", ["openid"])
        assert client.post("/v1/myaccount/apps/gws-cli/revoke",
                           headers=auth(cc_tok["access_token"])).status_code == 200
        r = client.post("/v1/myaccount/apps/gws-cli/revoke",
                        headers=auth(cc_tok["access_token"]))
        assert r.status_code == 404
        err = r.json()["error"]
        assert err["status"] == "NOT_FOUND" and "gws-cli" in err["message"]

    def test_unknown_client_404(self, client):
        tok = user1_setup(client)
        r = client.post("/v1/myaccount/apps/no-such-app/revoke",
                        headers=auth(tok["access_token"]))
        assert r.status_code == 404

    def test_cross_user_cannot_revoke_others_consent(self, client):
        user1_setup(client)
        consent(client, "user1", "claude-code", ["openid"])
        tok2 = user2_setup(client)
        # user1 consented to claude-code; user2 did not → 404 for user2's token
        r = client.post("/v1/myaccount/apps/claude-code/revoke",
                        headers=auth(tok2["access_token"]))
        assert r.status_code == 404
        # user1's consent is untouched
        admin = client.get("/_admin/clients", params={"user_id": "user1"}).json()
        assert "claude-code" in [c["client_id"] for c in admin["clients"]]

    def test_self_revocation_kills_own_token(self, client):
        tok = user1_setup(client)
        r = client.post("/v1/myaccount/apps/gws-cli/revoke",
                        headers=auth(tok["access_token"]))
        assert r.status_code == 200  # allowed; the token dies with the grant
        r = client.get("/v1/myaccount/apps", headers=auth(tok["access_token"]))
        assert r.status_code == 401
        assert "revoked" in r.json()["error"]["message"].lower()


# ---------------------------------------------------------------------------
class TestMyAccountSessions:

    def test_lists_own_sessions_with_fields(self, client):
        tok = user1_setup(client, include_refresh=True)
        extra = issue(client, "user1", ["openid", "email"])
        other = user2_setup(client)

        r = client.get("/v1/myaccount/sessions", headers=auth(tok["access_token"]))
        assert r.status_code == 200
        body = r.json()
        jtis = {s["jti"] for s in body["sessions"]}
        assert {jti_of(tok["access_token"]), jti_of(extra["access_token"])} <= jtis
        assert jti_of(other["access_token"]) not in jtis  # isolation

        s = next(x for x in body["sessions"] if x["jti"] == jti_of(tok["access_token"]))
        assert s["client_id"] == "gws-cli"
        assert set(s["scope"]) == {"openid", "email", "gmail.readonly"}
        assert s["issued_at"] and s["expires_at"]
        assert s["revoked"] is False and s["expired"] is False and s["active"] is True

        assert len(body["refresh_tokens"]) == 1
        rt = body["refresh_tokens"][0]
        assert rt["client_id"] == "gws-cli" and rt["revoked"] is False

    def test_revoke_session_reflected_everywhere(self, client):
        tok = user1_setup(client)
        victim = issue(client, "user1", ["openid", "gmail.readonly"])
        victim_jti = jti_of(victim["access_token"])

        r = client.post(f"/v1/myaccount/sessions/{victim_jti}/revoke",
                        headers=auth(tok["access_token"]))
        assert r.status_code == 200
        assert r.json() == {"status": "ok", "jti": victim_jti,
                            "revoked": True, "already_revoked": False}

        # introspection
        assert introspect(client, victim["access_token"]) == {"active": False}
        # session list
        r = client.get("/v1/myaccount/sessions", headers=auth(tok["access_token"]))
        s = next(x for x in r.json()["sessions"] if x["jti"] == victim_jti)
        assert s["revoked"] is True and s["active"] is False
        # the acting token itself is untouched
        me = next(x for x in r.json()["sessions"]
                  if x["jti"] == jti_of(tok["access_token"]))
        assert me["active"] is True
        # audit
        ev = audit_events(client, event_type="token_revoked", user_id="user1")
        assert any(e["details"].get("jti") == victim_jti
                   and e["details"].get("via") == "myaccount" for e in ev)
        # using the revoked token now 401s and counts in metrics
        r = client.get("/oauth2/v2/userinfo", headers=auth(victim["access_token"]))
        assert r.status_code == 401
        metrics = client.get("/_admin/metrics").json()
        # introspection of revoked + invalid_token(reason=revoked) both count
        assert metrics["revocation_compliance"]["revoked_token_uses"] >= 2

    def test_revoke_is_idempotent(self, client):
        tok = user1_setup(client)
        victim = issue(client, "user1", ["openid"])
        victim_jti = jti_of(victim["access_token"])
        h = auth(tok["access_token"])
        assert client.post(f"/v1/myaccount/sessions/{victim_jti}/revoke",
                           headers=h).json()["already_revoked"] is False
        r = client.post(f"/v1/myaccount/sessions/{victim_jti}/revoke", headers=h)
        assert r.status_code == 200 and r.json()["already_revoked"] is True

    def test_unknown_jti_404(self, client):
        tok = user1_setup(client)
        r = client.post("/v1/myaccount/sessions/tok_000000000000000000000000/revoke",
                        headers=auth(tok["access_token"]))
        assert r.status_code == 404
        assert r.json()["error"]["status"] == "NOT_FOUND"

    def test_cross_user_revoke_404_and_harmless(self, client):
        tok1 = user1_setup(client)
        tok2 = user2_setup(client)
        target = jti_of(tok1["access_token"])
        # user2 cannot revoke user1's session — indistinguishable from missing
        r = client.post(f"/v1/myaccount/sessions/{target}/revoke",
                        headers=auth(tok2["access_token"]))
        assert r.status_code == 404
        # user1's token is still alive
        assert introspect(client, tok1["access_token"])["active"] is True

    def test_include_revoked_filter(self, client):
        tok = user1_setup(client)
        victim = issue(client, "user1", ["openid"])
        victim_jti = jti_of(victim["access_token"])
        h = auth(tok["access_token"])
        client.post(f"/v1/myaccount/sessions/{victim_jti}/revoke", headers=h)
        r = client.get("/v1/myaccount/sessions",
                       params={"include_revoked": "false"}, headers=h)
        assert victim_jti not in {s["jti"] for s in r.json()["sessions"]}


# ---------------------------------------------------------------------------
class TestMyAccountSecurityEvents:

    def test_shows_own_events_only(self, client):
        tok1 = user1_setup(client)
        tok2 = user2_setup(client)
        # generate a user1-attributed security event
        victim = issue(client, "user1", ["openid"])
        client.post(f"/v1/myaccount/sessions/{jti_of(victim['access_token'])}/revoke",
                    headers=auth(tok1["access_token"]))

        r = client.get("/v1/myaccount/security_events",
                       headers=auth(tok1["access_token"]))
        assert r.status_code == 200
        events = r.json()["events"]
        assert events, "user1 should have events"
        assert all(e["user_id"] == "user1" for e in events)
        types = {e["event_type"] for e in events}
        assert {"token_issued", "token_revoked", "consent_granted"} <= types

        r = client.get("/v1/myaccount/security_events",
                       headers=auth(tok2["access_token"]))
        assert all(e["user_id"] == "user2" for e in r.json()["events"])
        assert "token_revoked" not in {e["event_type"] for e in r.json()["events"]}

    def test_event_type_filter_and_limit(self, client):
        tok = user1_setup(client)
        h = auth(tok["access_token"])
        r = client.get("/v1/myaccount/security_events",
                       params={"event_type": "token_issued"}, headers=h)
        events = r.json()["events"]
        assert events and all(e["event_type"] == "token_issued" for e in events)
        r = client.get("/v1/myaccount/security_events",
                       params={"limit": 1}, headers=h)
        assert len(r.json()["events"]) == 1


# ---------------------------------------------------------------------------
class TestRevokeAt:
    """Scheduled revocation: POST/GET /_admin/revoke_at + cancel."""

    def _fired(self, client, job_id):
        def check():
            jobs = {j["job_id"]: j for j in
                    client.get("/_admin/revoke_at").json()["jobs"]}
            return jobs.get(job_id, {}).get("status") == "fired"
        return check

    def test_scope_mode_fires_within_tolerance(self, client):
        tok = user1_setup(client)
        t0 = time.monotonic()
        r = client.post("/_admin/revoke_at", json={
            "delay_seconds": 0.75, "user_id": "user1", "scope": "gmail.readonly"})
        assert r.status_code == 200, r.text
        job = r.json()["job"]
        assert job["status"] == "pending" and job["scope"] == "gmail.readonly"
        assert job["fire_at"] > job["scheduled_at"]

        # not yet fired: token still active immediately after scheduling
        assert introspect(client, tok["access_token"])["active"] is True

        assert wait_for(self._fired(client, job["job_id"]), timeout=5.0)
        elapsed = time.monotonic() - t0
        assert 0.5 <= elapsed <= 5.0  # fired after the delay, within tolerance

        # token carrying the scope is revoked; consent lost the scope
        assert introspect(client, tok["access_token"]) == {"active": False}
        admin = client.get("/_admin/clients", params={"user_id": "user1"}).json()
        gws = next(c for c in admin["clients"] if c["client_id"] == "gws-cli")
        assert "gmail.readonly" not in gws["granted_scopes"]

        # audit + job bookkeeping
        ev = audit_events(client, event_type="scheduled_revocation_fired")
        assert ev and ev[0]["user_id"] == "user1"
        assert ev[0]["details"]["job_id"] == job["job_id"]
        assert ev[0]["details"]["result"]["revoked_tokens"] == 1
        jobs = {j["job_id"]: j for j in client.get("/_admin/revoke_at").json()["jobs"]}
        fired = jobs[job["job_id"]]
        assert fired["fired_at"] and fired["result"]["revoked_tokens"] == 1

    def test_all_mode_revokes_everything_for_user(self, client):
        tok = user1_setup(client, include_refresh=True)
        consent(client, "user1", "claude-code", ["openid"])
        cc = issue(client, "user1", ["openid"], client_id="claude-code")
        bystander = user2_setup(client)

        r = client.post("/_admin/revoke_at", json={
            "delay_seconds": 0.1, "user_id": "user1", "all": True})
        job = r.json()["job"]
        assert wait_for(self._fired(client, job["job_id"]), timeout=5.0)

        assert introspect(client, tok["access_token"]) == {"active": False}
        assert introspect(client, tok["refresh_token"]) == {"active": False}
        assert introspect(client, cc["access_token"]) == {"active": False}
        # both consents revoked
        admin = client.get("/_admin/clients", params={"user_id": "user1"}).json()
        assert admin["clients"] == []
        # user2 untouched (isolation)
        assert introspect(client, bystander["access_token"])["active"] is True

        jobs = {j["job_id"]: j for j in client.get("/_admin/revoke_at").json()["jobs"]}
        result = jobs[job["job_id"]]["result"]
        assert result["consents_revoked"] == 2
        assert result["revoked_access_tokens"] == 2
        assert result["revoked_refresh_tokens"] == 1

    def test_client_id_scopes_the_blast_radius(self, client):
        gws = user1_setup(client)
        consent(client, "user1", "claude-code", ["openid"])
        cc = issue(client, "user1", ["openid"], client_id="claude-code")
        r = client.post("/_admin/revoke_at", json={
            "delay_seconds": 0.1, "user_id": "user1",
            "client_id": "gws-cli", "all": True})
        job = r.json()["job"]
        assert wait_for(self._fired(client, job["job_id"]), timeout=5.0)
        assert introspect(client, gws["access_token"]) == {"active": False}
        assert introspect(client, cc["access_token"])["active"] is True
        admin = client.get("/_admin/clients", params={"user_id": "user1"}).json()
        assert [c["client_id"] for c in admin["clients"]] == ["claude-code"]

    def test_cancel_prevents_firing(self, client):
        tok = user1_setup(client)
        r = client.post("/_admin/revoke_at", json={
            "delay_seconds": 5, "user_id": "user1", "scope": "gmail.readonly"})
        job = r.json()["job"]

        r = client.post(f"/_admin/revoke_at/{job['job_id']}/cancel")
        assert r.status_code == 200
        assert r.json()["job"]["status"] == "cancelled"

        time.sleep(0.3)
        assert introspect(client, tok["access_token"])["active"] is True
        assert audit_events(client, event_type="scheduled_revocation_fired") == []
        # idempotent re-cancel
        assert client.post(f"/_admin/revoke_at/{job['job_id']}/cancel").status_code == 200

    def test_cancel_unknown_404_and_fired_409(self, client):
        user1_setup(client)
        assert client.post("/_admin/revoke_at/rvk_nope/cancel").status_code == 404
        r = client.post("/_admin/revoke_at", json={
            "delay_seconds": 0, "user_id": "user1", "scope": "email"})
        job = r.json()["job"]
        assert wait_for(self._fired(client, job["job_id"]), timeout=5.0)
        assert client.post(f"/_admin/revoke_at/{job['job_id']}/cancel").status_code == 409

    def test_validation_errors(self, client):
        # neither scope nor all
        r = client.post("/_admin/revoke_at",
                        json={"delay_seconds": 1, "user_id": "user1"})
        assert r.status_code == 400
        # both scope and all
        r = client.post("/_admin/revoke_at", json={
            "delay_seconds": 1, "user_id": "user1", "scope": "email", "all": True})
        assert r.status_code == 400
        # unknown user / client
        r = client.post("/_admin/revoke_at", json={
            "delay_seconds": 1, "user_id": "ghost", "scope": "email"})
        assert r.status_code == 404
        r = client.post("/_admin/revoke_at", json={
            "delay_seconds": 1, "user_id": "user1", "client_id": "ghost-app",
            "scope": "email"})
        assert r.status_code == 404
        # negative delay rejected by schema
        r = client.post("/_admin/revoke_at", json={
            "delay_seconds": -1, "user_id": "user1", "scope": "email"})
        assert r.status_code == 400
        # nothing got scheduled
        assert client.get("/_admin/revoke_at").json()["jobs"] == []

    def test_seed_cancels_pending_jobs(self, client):
        user1_setup(client)
        r = client.post("/_admin/revoke_at", json={
            "delay_seconds": 30, "user_id": "user1", "scope": "email"})
        job_id = r.json()["job"]["job_id"]
        client.post("/_admin/seed", json={"scenario": "default"})
        jobs = {j["job_id"]: j for j in client.get("/_admin/revoke_at").json()["jobs"]}
        assert jobs[job_id]["status"] == "cancelled"

    def test_myaccount_sees_scheduled_revocation(self, client):
        """End-to-end: the user-facing surface reflects a fired scheduled job."""
        tok = user1_setup(client)
        sacrificial = issue(client, "user1", ["openid", "gmail.send"])
        r = client.post("/_admin/revoke_at", json={
            "delay_seconds": 0.1, "user_id": "user1", "scope": "gmail.send"})
        job = r.json()["job"]
        assert wait_for(self._fired(client, job["job_id"]), timeout=5.0)

        h = auth(tok["access_token"])  # untouched (no gmail.send)
        r = client.get("/v1/myaccount/sessions", headers=h)
        s = next(x for x in r.json()["sessions"]
                 if x["jti"] == jti_of(sacrificial["access_token"]))
        assert s["revoked"] is True
        ev = client.get("/v1/myaccount/security_events",
                        params={"event_type": "scheduled_revocation_fired"},
                        headers=h).json()["events"]
        assert ev and ev[0]["details"]["job_id"] == job["job_id"]
