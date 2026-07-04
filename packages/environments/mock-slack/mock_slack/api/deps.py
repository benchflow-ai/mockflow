"""Shared dependencies for API routes."""

from __future__ import annotations

import base64
from typing import Literal

from fastapi import Depends, Header, Request
from sqlalchemy import func
from sqlalchemy.orm import Session

from mock_slack.models import get_session_factory


class ImpersonationError(Exception):
    """Authenticated request named a user that is not the token's subject.

    Handled in ``mock_slack.api.app`` with the auth contract 403 body
    (``env_0_auth_client.errors.impersonation_body``), deliberately NOT the
    Slack ``{"ok": false, "error": ...}`` envelope used for HTTPException.
    """

    def __init__(self, authenticated_user: str, requested_user: str):
        super().__init__(
            f"Cannot access another user's resources "
            f"(authenticated as {authenticated_user!r}, requested {requested_user!r})"
        )
        self.authenticated_user = authenticated_user
        self.requested_user = requested_user


def resolve_auth_local_id(request: Request, db: Session) -> str | None:
    """Map a verified auth token to a LOCAL slack user id.

    Returns None when auth is disabled (no token state). Resolution order
    (identity-alignment): (a) SlackUser whose id == token ``sub``; (b) else
    SlackUser whose email matches the token's ``email`` claim
    (case-insensitive); (c) else the raw ``sub`` unchanged (legacy behavior:
    every route already handles unknown user ids gracefully).
    """
    auth_user_id = getattr(request.state, "auth_user_id", None)
    if auth_user_id is None:
        return None
    from mock_slack.models import SlackUser

    user = db.query(SlackUser).filter(SlackUser.id == auth_user_id).first()
    if user is None:
        auth_email = (getattr(request.state, "auth_email", "") or "").strip()
        if auth_email:
            user = db.query(SlackUser).filter(
                func.lower(SlackUser.email) == auth_email.lower()
            ).first()
    return user.id if user is not None else auth_user_id


def guard_impersonation(request: Request, requested_user_id: str | None, db: Session) -> None:
    """Raise the contract 403 when an authenticated caller tries to ACT AS
    another user (e.g. ``users.profile.set`` with an explicit foreign
    ``user``).

    Slack's API surface has no ``{userId}`` path params -- the token implies
    the actor -- so unlike gmail this guard only applies to the few
    endpoints that accept an explicit acting-user override. Plain directory
    READS of other users (users.info, users.getPresence, ...) are legitimate
    Slack functionality and are NOT impersonation.

    No-op when auth is disabled, when no explicit user was named, or when the
    named user matches the token's ``sub`` or the RESOLVED local id (the
    email-claim fallback identity, see ``resolve_auth_local_id``).
    """
    auth_user_id = getattr(request.state, "auth_user_id", None)
    if auth_user_id is None or not requested_user_id or requested_user_id == auth_user_id:
        return
    local_id = resolve_auth_local_id(request, db)
    if requested_user_id == local_id:
        return
    # The middleware cannot see body/query user-vs-sub mismatches; report
    # here. env_0_auth_client is guaranteed importable: auth_user_id is only
    # ever set by Env_0AuthMiddleware.
    from env_0_auth_client import report_impersonation

    report_impersonation(
        local_id,
        requested_user_id,
        client_id=getattr(request.state, "auth_client_id", None),
        scope=" ".join(getattr(request.state, "auth_scopes", None) or []),
    )
    raise ImpersonationError(local_id, requested_user_id)


def encode_cursor(payload: str) -> str:
    """Encode a cursor payload to base64, matching real Slack cursor format."""
    return base64.b64encode(payload.encode()).decode()


def decode_cursor(cursor: str) -> str | None:
    """Decode a base64 cursor, returning the payload or None if invalid."""
    try:
        return base64.b64decode(cursor.encode()).decode()
    except Exception:
        return None


def get_db() -> Session:
    """Yield a DB session."""
    SessionLocal = get_session_factory()
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def resolve_workspace_id(
    x_mock_slack_workspace: str | None = Header(None),
) -> str:
    """Resolve workspace ID from header or return default.

    Priority: X-Mock-Slack-Workspace header -> 'workspace_001'
    """
    if x_mock_slack_workspace:
        return x_mock_slack_workspace
    return "workspace_001"


def resolve_current_user_id(
    request: Request,
    authorization: str | None = Header(None),
    db: Session = Depends(get_db),
    workspace_id: str = Depends(resolve_workspace_id),
) -> str:
    """Return the user ID associated with the current token.

    With auth enabled (Env_0AuthMiddleware sets request.state.auth_user_id):
    the verified token IS the caller's identity -- legacy xoxb-/xoxp- prefix
    sniffing never runs. The token is mapped to a LOCAL slack user id via
    ``resolve_auth_local_id``: (a) id == ``sub``; (b) else email == the
    token's ``email`` claim (case-insensitive); (c) else the raw ``sub``
    as-is (Slack's token-implies-identity model has no 'me' alias to resolve
    and every route already handles unknown user ids gracefully).

    With auth disabled (the default), legacy behavior is unchanged:
    Bot token (xoxb-) → B01MOCKBOT (the bot app user).
    User token (xoxp-) → first non-bot user in the workspace.
    """
    local_id = resolve_auth_local_id(request, db)
    if local_id is not None:
        return local_id

    from mock_slack.models import SlackUser
    token = (authorization or "").removeprefix("Bearer ").strip()
    if token not in {"mock-user-token", "mock-user"} and not token.startswith("xoxp-"):
        return "B01MOCKBOT"
    user = (
        db.query(SlackUser)
        .filter(
            SlackUser.workspace_id == workspace_id,
            SlackUser.is_bot == False,
            SlackUser.id != "USLACKBOT",  # Slackbot is is_bot=False per real API; skip it
        )
        .first()
    )
    return user.id if user else ""


def resolve_token_type(
    request: Request,
    authorization: str | None = Header(None),
    db: Session = Depends(get_db),
) -> Literal["bot", "user"]:
    """Determine token type from Authorization header.

    With auth enabled, the verified token's RESOLVED local identity
    decides (``resolve_auth_local_id``: sub, else email-claim fallback): an
    identity whose SlackUser row has ``is_bot=True`` (e.g. B01MOCKBOT) is a
    bot token, anything else is a user token (auth subs are user
    identities, so unknown identities default to 'user'). Without this, JWTs
    -- which carry no xoxb-/xoxp- prefix -- would always be treated as bot
    tokens, changing response shapes (last_read) and breaking user-token-only
    methods (search.messages).

    With auth disabled (the default), legacy behavior is unchanged:
    xoxb-* => bot token, xoxp-* => user token. Sanitized public test tokens
    are also accepted. Defaults to 'bot' when no token is provided.
    """
    local_id = resolve_auth_local_id(request, db)
    if local_id is not None:
        from mock_slack.models import SlackUser

        user = db.query(SlackUser).filter(SlackUser.id == local_id).first()
        return "bot" if (user is not None and user.is_bot) else "user"

    if authorization:
        token = authorization.removeprefix("Bearer ").strip()
        if token in {"mock-user-token", "mock-user"} or token.startswith("xoxp-"):
            return "user"
    return "bot"
