"""Shared fixtures: RSA keypairs, a gmail-shaped dummy FastAPI app, report capture."""

import json

import httpx
import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from env_0_auth_client import Env_0AuthMiddleware, reporting
from env_0_auth_client.testing import generate_test_keypair, jwks_for, make_jwt

KID = "test-key-001"
OTHER_KID = "test-key-002"

# Gmail-shaped scope map (OR logic), as a real gmail retrofit would define.
SCOPE_MAP = {
    ("GET", "/gmail/v1/users/{userId}/messages"): ["gmail.readonly", "gmail.modify", "gmail.full"],
    ("GET", "/gmail/v1/users/{userId}/messages/{messageId}"): ["gmail.readonly", "gmail.modify", "gmail.full"],
    ("POST", "/gmail/v1/users/{userId}/messages/send"): ["gmail.send", "gmail.full"],
    ("POST", "/gmail/v1/users/{userId}/labels"): ["gmail.labels", "gmail.full"],
}


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    """Default every test to a hermetic env: reporting OFF, no stray AUTH_* vars."""
    monkeypatch.setenv("AUTH_REPORT", "0")
    for var in (
        "AUTH_ENABLED",
        "AUTH_URL",
        "AUTH_ISSUER",
        "AUTH_INTROSPECT",
        "AUTH_JWKS_TTL",
    ):
        monkeypatch.delenv(var, raising=False)
    yield
    reporting.set_transport(None)


@pytest.fixture(scope="session")
def keypair():
    return generate_test_keypair()


@pytest.fixture(scope="session")
def other_keypair():
    return generate_test_keypair()


@pytest.fixture(scope="session")
def private_key(keypair):
    return keypair[0]


@pytest.fixture(scope="session")
def public_key(keypair):
    return keypair[1]


@pytest.fixture
def jwks(public_key):
    return jwks_for(public_key, kid=KID)


def build_app(**middleware_kwargs) -> FastAPI:
    """Dummy FastAPI app with gmail-shaped routes + exempt/admin routes."""
    app = FastAPI()

    @app.get("/gmail/v1/users/{userId}/messages")
    def list_messages(userId: str, request: Request):
        return {
            "userId": userId,
            "auth_user_id": getattr(request.state, "auth_user_id", None),
            "auth_email": getattr(request.state, "auth_email", None),
            "auth_scopes": getattr(request.state, "auth_scopes", None),
            "auth_client_id": getattr(request.state, "auth_client_id", None),
            "auth_jti": getattr(request.state, "auth_jti", None),
            "auth_token_exp": getattr(request.state, "auth_token_exp", None),
        }

    @app.get("/gmail/v1/users/{userId}/messages/{messageId}")
    def get_message(userId: str, messageId: str):
        return {"id": messageId}

    @app.post("/gmail/v1/users/{userId}/messages/send")
    def send_message(userId: str):
        return {"id": "msg_sent_001", "threadId": "thread_001"}

    @app.get("/gmail/v1/users/{userId}/profile")  # NOT in the scope map -> auth-only
    def get_profile(userId: str):
        return {"emailAddress": "alice@clawsbench.local"}

    @app.get("/_admin/state")
    def admin_state():
        return {"users": {}}

    @app.get("/health")
    def health():
        return {"status": "ok"}

    middleware_kwargs.setdefault("scope_map", SCOPE_MAP)
    app.add_middleware(Env_0AuthMiddleware, **middleware_kwargs)
    return app


@pytest.fixture
def app(jwks):
    return build_app(jwks_static=jwks)


@pytest.fixture
def client(app):
    with TestClient(app) as c:
        yield c


@pytest.fixture
def token(private_key):
    """Valid token with read scopes for user_001 / gws-cli."""
    return make_jwt(private_key=private_key, kid=KID, scope="openid email gmail.readonly")


def bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def report_capture(monkeypatch):
    """Turn reporting ON and capture every report POST via a stub httpx transport."""
    monkeypatch.setenv("AUTH_REPORT", "1")
    captured: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append({"url": str(request.url), "json": json.loads(request.content)})
        return httpx.Response(200, json={"status": "ok"})

    reporting.set_transport(httpx.MockTransport(handler))
    yield captured
    reporting.set_transport(None)
