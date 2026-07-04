"""Shared dependencies for API routes."""

from __future__ import annotations

from fastapi import Header, HTTPException, Depends, Request
from sqlalchemy import func
from sqlalchemy.orm import Session

from mock_gcal.models import User, get_session_factory


class ImpersonationError(Exception):
    """Authenticated request named a userId that is not the token's subject.

    Handled in ``mock_gcal.api.app`` with the auth contract 403 body
    (``env_0_auth_client.errors.impersonation_body``), deliberately NOT the
    Google Calendar error envelope used for HTTPException.
    """

    def __init__(self, authenticated_user: str, requested_user: str):
        super().__init__(
            f"Cannot access another user's resources "
            f"(authenticated as {authenticated_user!r}, requested {requested_user!r})"
        )
        self.authenticated_user = authenticated_user
        self.requested_user = requested_user


def _auth_effective_user(request: Request, db: Session) -> User | None:
    """Map the verified token to a LOCAL user (auth-enabled path).

    Resolution order (identity-alignment): (a) local user whose id == token
    ``sub``; (b) else local user whose email matches the token's ``email``
    claim (case-insensitive); (c) else None (callers keep the existing
    not-found behavior). Only called when ``request.state.auth_user_id`` is
    set, i.e. when Env_0AuthMiddleware verified a Bearer token. Legacy identity
    headers are deliberately never consulted here.
    """
    auth_user_id = request.state.auth_user_id
    user = db.query(User).filter(User.id == auth_user_id).first()
    if user is None:
        auth_email = (getattr(request.state, "auth_email", "") or "").strip()
        if auth_email:
            user = db.query(User).filter(
                func.lower(User.email_address) == auth_email.lower()
            ).first()
    return user


def _auth_resolved_user_id(request: Request, db: Session) -> str:
    """Resolve (with email-claim fallback) and 404-check the token identity."""
    user = _auth_effective_user(request, db)
    if not user:
        raise HTTPException(404, f"User {request.state.auth_user_id!r} not found")
    return user.id


def get_db() -> Session:
    """Yield a DB session."""
    SessionLocal = get_session_factory()
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _resolve_header_user(
    db: Session,
    x_env_0_gcal_user: str | None,
    x_mock_gcal_user: str | None = None,
) -> str | None:
    candidate = x_env_0_gcal_user or x_mock_gcal_user
    if candidate:
        user = db.query(User).filter(
            (User.id == candidate) | (User.email_address == candidate)
        ).first()
        if user:
            return user.id
    return None


def resolve_user_id(
    userId: str,
    request: Request,
    x_env_0_gcal_user: str | None = Header(None),
    x_mock_gcal_user: str | None = Header(None),
    db: Session = Depends(get_db),
) -> str:
    """Resolve 'me' to the actual user ID.

    With auth enabled (Env_0AuthMiddleware sets request.state.auth_user_id):
    the token is mapped to a LOCAL user via (a) id == token ``sub``, else
    (b) email == token ``email`` claim (case-insensitive), else (c) the
    legacy 404. The resolved LOCAL id is the effective identity: 'me' resolves
    to it, and an explicit userId naming anyone other than the token's ``sub``
    or the resolved local user raises the contract 403 impersonation error
    (after reporting an impersonation_attempt event to auth). Identity
    headers are ignored.

    With auth disabled (the default), legacy behavior is unchanged:
    userId path param -> X-Env-0-Gcal-User / X-Mock-Gcal-User header -> first
    user in DB.
    """
    auth_user_id = getattr(request.state, "auth_user_id", None)
    if auth_user_id is not None:
        user = _auth_effective_user(request, db)
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

    resolved = _resolve_header_user(db, x_env_0_gcal_user, x_mock_gcal_user)
    if resolved:
        return resolved

    # Fallback: first user
    user = db.query(User).first()
    if not user:
        raise HTTPException(404, "No users in database. Run `mock-gcal seed` first.")
    return user.id


def resolve_actor_user_id(
    request: Request,
    x_env_0_gcal_user: str | None = Header(None),
    x_mock_gcal_user: str | None = Header(None),
    db: Session = Depends(get_db),
) -> str:
    """Resolve actor for endpoints without userId path params.

    With auth enabled, the actor is ALWAYS the token's ``sub`` (no path
    userId exists, so no impersonation is possible); identity headers are
    ignored. With auth disabled, legacy header/first-user behavior is
    unchanged.
    """
    if getattr(request.state, "auth_user_id", None) is not None:
        return _auth_resolved_user_id(request, db)

    resolved = _resolve_header_user(db, x_env_0_gcal_user, x_mock_gcal_user)
    if resolved:
        return resolved

    # Fallback: first user
    user = db.query(User).first()
    if not user:
        raise HTTPException(404, "No users in database. Run `mock-gcal seed` first.")
    return user.id
