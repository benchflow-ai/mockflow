"""Pytest fixtures for auth (gmail conftest pattern)."""

from __future__ import annotations

import base64
import hashlib

import pytest
from fastapi.testclient import TestClient

from mock_auth.models import init_db, reset_engine
from mock_auth.seed.generator import seed_database


@pytest.fixture
def db_path(tmp_path):
    """Temporary database path."""
    path = str(tmp_path / "test.db")
    yield path
    from mock_auth import scheduler
    scheduler.clear()  # no scheduled-revocation timers may leak across tests
    reset_engine()


@pytest.fixture
def seeded_db(db_path):
    """Seed a temporary database."""
    reset_engine()
    seed_database(scenario="default", seed=42, db_path=db_path)
    return db_path


@pytest.fixture
def client(seeded_db):
    """FastAPI test client with seeded database."""
    reset_engine()
    init_db(seeded_db)
    from mock_auth.api.app import app
    with TestClient(app) as c:
        yield c
    reset_engine()


# --- Shared helpers ---

DEMO_PASSWORD = "password123"
ALICE = {"id": "user1", "email": "alex@nexusai.com", "name": "Alex Chen"}
BOB = {"id": "user2", "email": "colleague@example.com", "name": "Jordan Rivera"}

GWS_REDIRECT = "http://localhost:8085/callback"
OPENCLAW_REDIRECT = "http://localhost:8765/callback"


def login(client: TestClient, email: str = ALICE["email"], password: str = DEMO_PASSWORD):
    """POST /web/login; the TestClient session keeps the cookie."""
    return client.post("/web/login", data={"email": email, "password": password},
                       follow_redirects=False)


def pkce_pair(verifier: str = "test-verifier-string-with-enough-entropy-0123456789"):
    challenge = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode("ascii")).digest()
    ).rstrip(b"=").decode("ascii")
    return verifier, challenge


def authorize_params(scope: str = "openid email gmail.readonly", *,
                     client_id: str = "gws-cli", redirect_uri: str = GWS_REDIRECT,
                     state: str = "st-123", challenge: str | None = None,
                     method: str = "S256", login_hint: str | None = None,
                     nonce: str | None = None) -> dict:
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": scope,
        "state": state,
    }
    if challenge:
        params["code_challenge"] = challenge
        params["code_challenge_method"] = method
    if login_hint:
        params["login_hint"] = login_hint
    if nonce:
        params["nonce"] = nonce
    return params


def extract_query(location: str) -> dict:
    from urllib.parse import parse_qs, urlparse
    return {k: v[0] for k, v in parse_qs(urlparse(location).query).items()}


def get_code_via_auto_consent(client: TestClient, scope: str = "openid email gmail.readonly",
                              *, client_id: str = "gws-cli",
                              redirect_uri: str = GWS_REDIRECT,
                              user_id: str = "user1",
                              login_hint: str = "alex@nexusai.com",
                              challenge: str | None = None) -> str:
    client.post("/_admin/auto_consent", json={
        "client_id": client_id, "user_id": user_id, "scopes": scope.split(),
    })
    if challenge is None and client_id == "gws-cli":
        challenge = pkce_pair()[1]
    r = client.get("/o/oauth2/v2/auth",
                   params=authorize_params(scope, client_id=client_id,
                                           redirect_uri=redirect_uri,
                                           challenge=challenge, login_hint=login_hint),
                   follow_redirects=False)
    assert r.status_code == 302, r.text
    qs = extract_query(r.headers["location"])
    assert "code" in qs, qs
    return qs["code"]


def exchange_code(client: TestClient, code: str, *, client_id: str = "gws-cli",
                  client_secret: str | None = None, redirect_uri: str = GWS_REDIRECT,
                  verifier: str | None = None) -> dict:
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri,
        "client_id": client_id,
    }
    if client_secret:
        data["client_secret"] = client_secret
    if verifier:
        data["code_verifier"] = verifier
    r = client.post("/oauth2/token", data=data)
    assert r.status_code == 200, r.text
    return r.json()


def full_auth_code_flow(client: TestClient, scope: str = "openid email gmail.readonly") -> dict:
    verifier, challenge = pkce_pair()
    code = get_code_via_auto_consent(client, scope, challenge=challenge)
    return exchange_code(client, code, verifier=verifier)
