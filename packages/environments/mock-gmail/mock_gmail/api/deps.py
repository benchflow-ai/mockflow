"""Shared dependencies for API routes."""

from __future__ import annotations

from fastapi import Header, HTTPException, Depends, Request
from sqlalchemy import func
from sqlalchemy.orm import Session

from mock_gmail.models import get_session_factory, User


class ImpersonationError(Exception):
    """Authenticated request named a userId that is not the token's subject.

    Handled in ``mock_gmail.api.app`` with the auth contract 403 body
    (``env_0_auth_client.errors.impersonation_body``), deliberately NOT the
    Gmail error envelope used for HTTPException.
    """

    def __init__(self, authenticated_user: str, requested_user: str):
        super().__init__(
            f"Cannot access another user's resources "
            f"(authenticated as {authenticated_user!r}, requested {requested_user!r})"
        )
        self.authenticated_user = authenticated_user
        self.requested_user = requested_user


def get_db() -> Session:
    """Yield a DB session."""
    SessionLocal = get_session_factory()
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def resolve_user_id(
    userId: str,
    request: Request,
    x_env_0_gmail_user: str | None = Header(None),
    x_mock_gmail_user: str | None = Header(None),
    db: Session = Depends(get_db),
) -> str:
    """Resolve 'me' to the actual user ID.

    With auth enabled (Env_0AuthMiddleware sets request.state.auth_user_id):
    the token is mapped to a LOCAL user via (a) id == token ``sub``, else
    (b) email == token ``email`` claim (case-insensitive), else (c) the
    legacy 404. The resolved LOCAL id is the effective identity: 'me' resolves
    to it, and an explicit userId naming anyone other than the token's ``sub``
    or the resolved local user raises the contract 403 impersonation error
    (after reporting an impersonation_attempt event to auth).

    With auth disabled (the default), legacy behavior is unchanged:
    userId path param -> X-Env-0-Gmail-User / X-Mock-Gmail-User header -> first user in DB.
    """
    auth_user_id = getattr(request.state, "auth_user_id", None)
    if auth_user_id is not None:
        user = db.query(User).filter(User.id == auth_user_id).first()
        if user is None:
            auth_email = (getattr(request.state, "auth_email", "") or "").strip()
            if auth_email:
                user = db.query(User).filter(
                    func.lower(User.email_address) == auth_email.lower()
                ).first()
        effective_id = user.id if user is not None else auth_user_id
        if userId not in ("me", auth_user_id, effective_id):
            # The middleware cannot see path-vs-sub mismatches; report here.
            # env_0_auth_client is guaranteed importable: auth_user_id is only
            # ever set by Env_0AuthMiddleware.
            from env_0_auth_client import report_impersonation

            report_impersonation(
                effective_id,
                userId,
                client_id=getattr(request.state, "auth_client_id", None),
                scope=" ".join(getattr(request.state, "auth_scopes", None) or []),
            )
            raise ImpersonationError(effective_id, userId)
        if user is None:
            raise HTTPException(404, f"User {auth_user_id!r} not found")
        return effective_id

    if userId != "me":
        user = db.query(User).filter(User.id == userId).first()
        if not user:
            raise HTTPException(404, f"User {userId!r} not found")
        return userId

    header_user = x_env_0_gmail_user or x_mock_gmail_user
    if header_user:
        user = db.query(User).filter(
            (User.id == header_user) | (User.email_address == header_user)
        ).first()
        if user:
            return user.id

    # Fallback: first user
    user = db.query(User).first()
    if not user:
        raise HTTPException(404, "No users in database. Run `mock-mock-gmail seed` first.")
    return user.id
