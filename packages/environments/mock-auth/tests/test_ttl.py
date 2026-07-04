"""Per-client access token TTL (oauth_clients.access_token_ttl) tests.

The TTL is honored by ALL grant types when set (overrides the 1h default), is
settable via seed scenarios (`_add_client(access_token_ttl=...)`), via the
`task:<name>` needles AUTH_CLIENTS dicts, and is overridable per call via
/_admin/issue_token's explicit expires_in.
"""

from __future__ import annotations

import jwt as pyjwt

from mock_auth.config import ACCESS_TOKEN_TTL

from .conftest import (
    GWS_REDIRECT,
    authorize_params,
    exchange_code,
    extract_query,
    full_auth_code_flow,
    pkce_pair,
)


def set_client_ttl(client_id: str, ttl: int | None):
    from mock_auth.models import OAuthClient, get_session_factory

    db = get_session_factory()()
    try:
        db.query(OAuthClient).filter(OAuthClient.client_id == client_id).update(
            {"access_token_ttl": ttl}, synchronize_session=False
        )
        db.commit()
    finally:
        db.close()


def claims_of(token: str) -> dict:
    return pyjwt.decode(token, options={"verify_signature": False, "verify_exp": False})


# ---------------------------------------------------------------------------
class TestPerClientTTL:
    def test_default_ttl_unchanged_when_unset(self, client):
        tok = full_auth_code_flow(client)
        assert tok["expires_in"] == ACCESS_TOKEN_TTL
        c = claims_of(tok["access_token"])
        assert c["exp"] - c["iat"] == ACCESS_TOKEN_TTL

    def test_auth_code_flow_honors_ttl_60(self, client):
        set_client_ttl("gws-cli", 60)
        tok = full_auth_code_flow(client)
        assert tok["expires_in"] == 60
        c = claims_of(tok["access_token"])
        assert c["exp"] - c["iat"] == 60

    def test_refresh_keeps_client_ttl(self, client):
        set_client_ttl("gws-cli", 60)
        tok = full_auth_code_flow(client)
        r = client.post("/oauth2/token", data={
            "grant_type": "refresh_token",
            "refresh_token": tok["refresh_token"],
            "client_id": "gws-cli",
        })
        assert r.status_code == 200, r.text
        refreshed = r.json()
        assert refreshed["expires_in"] == 60
        c = claims_of(refreshed["access_token"])
        assert c["exp"] - c["iat"] == 60

    def test_client_credentials_honors_ttl(self, client):
        set_client_ttl("openclaw-agent", 120)
        r = client.post("/oauth2/token", data={
            "grant_type": "client_credentials",
            "client_id": "openclaw-agent",
            "client_secret": "openclaw-secret",
            "scope": "gmail.readonly",
        })
        assert r.status_code == 200, r.text
        tok = r.json()
        assert tok["expires_in"] == 120
        c = claims_of(tok["access_token"])
        assert c["exp"] - c["iat"] == 120

    def test_device_flow_honors_ttl(self, client):
        set_client_ttl("gws-cli", 90)
        r = client.post("/oauth2/device/code",
                        data={"client_id": "gws-cli", "scope": "gmail.readonly"})
        dc = r.json()
        client.post("/_admin/approve_device",
                    json={"user_code": dc["user_code"], "user_id": "user1"})
        r = client.post("/oauth2/token", data={
            "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
            "device_code": dc["device_code"], "client_id": "gws-cli"})
        assert r.status_code == 200, r.text
        tok = r.json()
        assert tok["expires_in"] == 90
        c = claims_of(tok["access_token"])
        assert c["exp"] - c["iat"] == 90

    def test_admin_issue_token_defaults_to_client_ttl(self, client):
        set_client_ttl("gws-cli", 45)
        r = client.post("/_admin/issue_token", json={
            "client_id": "gws-cli", "user_id": "user1", "scopes": ["gmail.readonly"],
        })
        tok = r.json()
        assert tok["expires_in"] == 45
        c = claims_of(tok["access_token"])
        assert c["exp"] - c["iat"] == 45

    def test_admin_issue_token_explicit_expires_in_overrides_ttl(self, client):
        set_client_ttl("gws-cli", 45)
        r = client.post("/_admin/issue_token", json={
            "client_id": "gws-cli", "user_id": "user1",
            "scopes": ["gmail.readonly"], "expires_in": 7,
        })
        tok = r.json()
        assert tok["expires_in"] == 7
        c = claims_of(tok["access_token"])
        assert c["exp"] - c["iat"] == 7

    def test_zero_or_negative_ttl_falls_back_to_default(self, client):
        set_client_ttl("gws-cli", 0)
        tok = full_auth_code_flow(client)
        assert tok["expires_in"] == ACCESS_TOKEN_TTL

    def test_admin_clients_listing_exposes_ttl(self, client):
        set_client_ttl("gws-cli", 60)
        clients = client.get("/_admin/clients").json()["clients"]
        by_id = {c["client_id"]: c for c in clients}
        assert by_id["gws-cli"]["access_token_ttl"] == 60
        assert by_id["openclaw-agent"]["access_token_ttl"] is None


# ---------------------------------------------------------------------------
SYNTHETIC_NEEDLES = '''
"""Synthetic auth needles for the task: seed auto-discovery test."""

AUTH_USERS = [
    {"id": "user_900", "email": "taskuser@example.com", "display_name": "Task User",
     "given_name": "Task", "family_name": "User"},
]

AUTH_CLIENTS = [
    {"client_id": "task-short-ttl", "client_name": "Task Short TTL App",
     "client_type": "public",
     "redirect_uris": ["http://localhost:7777/cb"],
     "allowed_scopes": ["openid", "email", "gmail.readonly", "gmail.send"],
     "grant_types": ["authorization_code", "refresh_token"],
     "access_token_ttl": 60},
]

AUTH_CONSENTS = [
    {"user_id": "user_900", "client_id": "task-short-ttl",
     "scopes": ["openid", "email", "gmail.readonly"], "last_used_days_ago": 3},
]
'''


class TestTaskSeedAutoDiscovery:
    """End-to-end: a synthetic tasks/<name>/data/needles.py in a tmp TASKS_DIR
    is discovered, seeded via /_admin/seed scenario=task:<name>, and the
    AUTH_CLIENTS access_token_ttl is honored by the full auth-code flow."""

    def test_task_scenario_end_to_end(self, client, tmp_path, monkeypatch):
        tasks_dir = tmp_path / "tasks"
        data_dir = tasks_dir / "ttl-task" / "data"
        data_dir.mkdir(parents=True)
        (data_dir / "needles.py").write_text(SYNTHETIC_NEEDLES)
        monkeypatch.setenv("TASKS_DIR", str(tasks_dir))

        r = client.post("/_admin/seed", json={"scenario": "task:ttl-task"})
        assert r.status_code == 200, r.text
        info = r.json()
        assert info["scenario"] == "task:ttl-task"
        # NOTE: scenario extras shadow the totals in the seed response; the
        # "users"/"clients"/"consents" here are the NEEDLE counts.
        assert info["users"] == 1
        assert info["clients"] == 1
        assert info["consents"] == 1

        state = client.get("/_admin/state").json()
        assert len(state["users"]) == 3  # user1 + user2 (base) + user_900
        users = {u["id"]: u for u in state["users"]}
        assert "user_900" in users and users["user_900"]["email"] == "taskuser@example.com"
        assert {"user1", "user2"} <= set(users)  # base seed still present
        clients_by_id = {c["client_id"]: c for c in state["oauth_clients"]}
        task_client = clients_by_id["task-short-ttl"]
        assert task_client["access_token_ttl"] == 60
        assert task_client["client_type"] == "public"
        consents = [c for c in state["consent_records"]
                    if c["client_id"] == "task-short-ttl"]
        assert len(consents) == 1
        assert consents[0]["user_id"] == "user_900"
        assert "gmail.readonly" in consents[0]["granted_scopes"]
        assert consents[0]["last_used_at"] is not None

        # Full auth-code+PKCE flow as the task client: the seeded AUTH_CONSENTS
        # record auto-consents, and the issued JWT honors the 60s TTL.
        verifier, challenge = pkce_pair()
        r = client.get("/o/oauth2/v2/auth", params=authorize_params(
            "openid email gmail.readonly", client_id="task-short-ttl",
            redirect_uri="http://localhost:7777/cb", challenge=challenge,
            login_hint="taskuser@example.com"), follow_redirects=False)
        assert r.status_code == 302, r.text
        qs = extract_query(r.headers["location"])
        assert "code" in qs, qs

        tok = exchange_code(client, qs["code"], client_id="task-short-ttl",
                            redirect_uri="http://localhost:7777/cb", verifier=verifier)
        assert tok["expires_in"] == 60
        c = claims_of(tok["access_token"])
        assert c["exp"] - c["iat"] == 60
        assert c["sub"] == "user_900"
        assert c["aud"] == "task-short-ttl"

        # Refresh keeps the per-client TTL.
        r = client.post("/oauth2/token", data={
            "grant_type": "refresh_token", "refresh_token": tok["refresh_token"],
            "client_id": "task-short-ttl"})
        assert r.status_code == 200, r.text
        assert r.json()["expires_in"] == 60

    def test_task_scenario_without_auth_needles_falls_back_to_base(
            self, client, tmp_path, monkeypatch):
        tasks_dir = tmp_path / "tasks"
        data_dir = tasks_dir / "plain-task" / "data"
        data_dir.mkdir(parents=True)
        (data_dir / "needles.py").write_text("SOME_OTHER_NEEDLE = 1\n")
        monkeypatch.setenv("TASKS_DIR", str(tasks_dir))

        r = client.post("/_admin/seed", json={"scenario": "task:plain-task"})
        assert r.status_code == 200, r.text
        state = client.get("/_admin/state").json()
        assert {u["id"] for u in state["users"]} == {"user1", "user2"}  # base seed only

    def test_unknown_task_scenario_still_400s(self, client, tmp_path, monkeypatch):
        monkeypatch.setenv("TASKS_DIR", str(tmp_path / "tasks"))
        r = client.post("/_admin/seed", json={"scenario": "task:does-not-exist"})
        assert r.status_code == 400
