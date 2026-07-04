"""Shared dependencies: DB session, web session user, OAuth client authentication."""

from __future__ import annotations

import base64
import binascii

import bcrypt
from fastapi import Request
from sqlalchemy.orm import Session

from mock_auth.api.errors import OAuthError
from mock_auth.audit import log_event, request_meta
from mock_auth.models import OAuthClient, User, get_session_factory
from mock_auth.web.sessions import SESSION_COOKIE, get_session_user_id


def get_db() -> Session:
    SessionLocal = get_session_factory()
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_web_user(request: Request, db: Session) -> User | None:
    """Resolve the logged-in user from the mock_auth_session cookie."""
    sid = request.cookies.get(SESSION_COOKIE)
    user_id = get_session_user_id(sid)
    if not user_id:
        return None
    return db.query(User).filter(User.id == user_id, User.is_active == True).first()  # noqa: E712


def check_password(plain: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), password_hash.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def _basic_auth_credentials(request: Request) -> tuple[str, str] | None:
    header = request.headers.get("authorization", "")
    if not header.lower().startswith("basic "):
        return None
    try:
        decoded = base64.b64decode(header[6:]).decode("utf-8")
        client_id, _, secret = decoded.partition(":")
        return client_id, secret
    except (binascii.Error, UnicodeDecodeError, ValueError):
        return None


def authenticate_client(
    request: Request,
    db: Session,
    form_client_id: str | None,
    form_client_secret: str | None,
) -> OAuthClient:
    """Authenticate an OAuth client via client_secret_post or client_secret_basic.

    Public clients (client_type='public') need no secret. Raises OAuthError
    invalid_client (401) on failure and logs an `invalid_client` audit event.
    """
    client_id = form_client_id
    client_secret = form_client_secret
    basic = _basic_auth_credentials(request)

    def _fail(desc: str, hint: str):
        log_event(db, "invalid_client", client_id=client_id, details={"reason": desc},
                  **request_meta(request))
        db.commit()
        raise OAuthError(
            "invalid_client", desc, hint=hint, status_code=401,
            headers={"WWW-Authenticate": 'Basic realm="auth"'},
        )

    if basic is not None:
        # RFC 6749 §2.3: a request must not use two client identities. Reject
        # a form client_id that contradicts the Basic-auth client_id instead
        # of silently preferring one of them.
        if form_client_id and basic[0] and form_client_id != basic[0]:
            _fail(
                "Conflicting client identities: HTTP Basic client_id and form "
                "client_id differ.",
                "Authenticate as exactly one client (client_secret_basic OR "
                "client_secret_post, with a single client_id).",
            )
        client_id = client_id or basic[0]
        client_secret = client_secret if client_secret is not None else basic[1]

    if not client_id:
        _fail("Client authentication failed: no client_id provided.",
              "Pass client_id (and client_secret for confidential clients) in the form body, "
              "or use HTTP Basic auth.")

    client = db.query(OAuthClient).filter(
        OAuthClient.client_id == client_id,
        OAuthClient.is_active == True,  # noqa: E712
    ).first()
    if client is None:
        _fail(f"Unknown client: {client_id!r}.",
              "Check the client_id against the seeded oauth_clients (see /_admin/state).")

    if client.client_type == "public":
        return client

    if not client_secret or not check_password(client_secret, client.client_secret):
        _fail(f"Invalid client_secret for client {client_id!r}.",
              "Confidential clients must authenticate with their client_secret "
              "(client_secret_post or client_secret_basic).")

    return client
