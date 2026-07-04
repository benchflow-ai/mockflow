"""Integration tests for optional AUTH_ENABLED behavior."""

from __future__ import annotations

import importlib

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from env_0_auth_client.testing import generate_test_keypair, jwks_for, make_jwt
from mock_gmail.models import init_db, reset_engine

KID = "test-key-001"
PRIVATE_KEY, PUBLIC_KEY = generate_test_keypair()
JWKS = jwks_for(PUBLIC_KEY, kid=KID)

ALICE = "user1"
ALICE_EMAIL = "alex@nexusai.com"


def _token(scope: str = "", sub: str = ALICE, **kwargs) -> str:
    return make_jwt(private_key=PRIVATE_KEY, kid=KID, sub=sub, scope=scope, **kwargs)


def _bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def auth_app(monkeypatch):
    """Fresh app instance with Env_0AuthMiddleware and static offline JWKS."""
    for var in ("AUTH_ENABLED", "AUTH_INTROSPECT", "AUTH_ISSUER", "AUTH_URL"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("AUTH_REPORT", "0")

    import mock_gmail.api.app as app_module

    app_module = importlib.reload(app_module)
    monkeypatch.setenv("AUTH_ENABLED", "1")
    assert app_module._apply_auth(app_module.app, jwks_static=JWKS) is True

    yield app_module.app

    monkeypatch.delenv("AUTH_ENABLED", raising=False)
    importlib.reload(app_module)


@pytest.fixture
def auth_client(auth_app, seeded_db):
    reset_engine()
    init_db(seeded_db)
    with TestClient(auth_app) as c:
        yield c
    reset_engine()


def test_every_gmail_route_has_scope_map_entry():
    from mock_gmail.api.app import app
    from mock_gmail.auth_scopes import GMAIL_PREFIX, SCOPE_MAP

    registered = set()
    for route in app.routes:
        if isinstance(route, APIRoute) and route.path.startswith(GMAIL_PREFIX):
            for method in route.methods:
                if method not in ("HEAD", "OPTIONS"):
                    registered.add((method, route.path))

    assert registered
    assert not (registered - set(SCOPE_MAP))
    assert not (set(SCOPE_MAP) - registered)


def test_valid_token_lists_messages(auth_client):
    resp = auth_client.get(
        "/gmail/v1/users/me/messages",
        headers=_bearer(_token("gmail.readonly")),
    )
    assert resp.status_code == 200
    assert resp.json()["messages"]


def test_no_token_401_when_auth_enabled(auth_client):
    resp = auth_client.get("/gmail/v1/users/me/messages")
    assert resp.status_code == 401
    assert resp.json()["error"]["status"] == "UNAUTHENTICATED"
    assert "WWW-Authenticate" in resp.headers


def test_nonlocal_sub_resolves_by_email_claim(auth_client):
    resp = auth_client.get(
        "/gmail/v1/users/me/profile",
        headers=_bearer(_token("gmail.readonly", sub="user_001", email=ALICE_EMAIL)),
    )
    assert resp.status_code == 200
    assert resp.json()["emailAddress"] == ALICE_EMAIL


def test_auth_disabled_does_not_require_bearer(client):
    resp = client.get("/gmail/v1/users/me/profile")
    assert resp.status_code == 200
    assert resp.json()["emailAddress"] == ALICE_EMAIL
