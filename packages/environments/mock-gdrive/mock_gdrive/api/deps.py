"""Shared dependencies for API routes."""

from __future__ import annotations

from fastapi import Header, HTTPException, Depends, Request
from sqlalchemy import func
from sqlalchemy.orm import Session

from mock_gdrive.models import get_session_factory, User


class ImpersonationError(Exception):
    """Authenticated request named an identity that is not the token's subject.

    Gdrive has no ``{userId}`` path parameter (unlike gmail); the explicit
    identity mechanism is the legacy ``X-Mock-Drive-User`` header. Handled in
    ``mock_gdrive.api.app`` with the auth contract 403 body
    (``env_0_auth_client.errors.impersonation_body``), deliberately NOT the
    Drive error envelope used for HTTPException.
    """

    def __init__(self, authenticated_user: str, requested_user: str):
        super().__init__(
            f"Cannot access another user's resources "
            f"(authenticated as {authenticated_user!r}, requested {requested_user!r})"
        )
        self.authenticated_user = authenticated_user
        self.requested_user = requested_user


def get_db() -> Session:
    SessionLocal = get_session_factory()
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def resolve_user(
    request: Request,
    x_mock_drive_user: str | None = Header(None, alias="X-Mock-Drive-User"),
    authorization: str | None = Header(None),
    db: Session = Depends(get_db),
) -> User:
    """Resolve the current user.

    With auth enabled (Env_0AuthMiddleware sets request.state.auth_user_id):
    the token is mapped to a LOCAL user via (a) id == token ``sub``, else
    (b) email == token ``email`` claim (case-insensitive), else (c) the
    legacy 404. The resolved LOCAL user is the effective identity. The legacy
    ``Authorization: Bearer <user_id_or_email>`` convention is unreachable here
    (the Authorization header IS the verified JWT), and an ``X-Mock-Drive-User``
    header naming anyone other than the token's ``sub`` or the resolved local
    user (by id or email) raises the contract 403 impersonation error (after
    reporting an impersonation_attempt event to auth).

    With auth disabled (the default), legacy behavior is unchanged:
    1. X-Mock-Drive-User header (by ID or email)
    2. Authorization: Bearer <user_id_or_email>
    3. Fallback to first user in DB
    """
    auth_user_id = getattr(request.state, "auth_user_id", None)
    if auth_user_id is not None:
        user = db.query(User).filter(User.id == auth_user_id).first()
        if user is None:
            auth_email = (getattr(request.state, "auth_email", "") or "").strip()
            if auth_email:
                user = db.query(User).filter(
                    func.lower(User.email) == auth_email.lower()
                ).first()
        effective_id = user.id if user is not None else auth_user_id
        requested = x_mock_drive_user
        allowed = {auth_user_id, effective_id}
        if user is not None:
            allowed.add(user.email)
        if requested and requested not in allowed:
            # The middleware cannot see header-vs-sub mismatches; report here.
            # env_0_auth_client is guaranteed importable: auth_user_id is only
            # ever set by Env_0AuthMiddleware.
            from env_0_auth_client import report_impersonation

            report_impersonation(
                effective_id,
                requested,
                client_id=getattr(request.state, "auth_client_id", None),
                scope=" ".join(getattr(request.state, "auth_scopes", None) or []),
            )
            raise ImpersonationError(effective_id, requested)
        if not user:
            raise HTTPException(404, f"User {auth_user_id!r} not found")
        return user

    identifier = None

    if x_mock_drive_user:
        identifier = x_mock_drive_user
    elif authorization and authorization.startswith("Bearer "):
        identifier = authorization[7:].strip()

    if identifier:
        user = db.query(User).filter(
            (User.id == identifier) | (User.email == identifier)
        ).first()
        if user:
            return user
        raise HTTPException(401, f"User {identifier!r} not found")

    # Fallback: first user
    user = db.query(User).first()
    if not user:
        raise HTTPException(404, "No users in database. Run `mock-gdrive seed` first.")
    return user
