"""Shared dependencies for API routes."""

from __future__ import annotations

from fastapi import Header, HTTPException, Depends, Request
from sqlalchemy import func
from sqlalchemy.orm import Session

from mock_gdoc.models import get_session_factory, Document, Permission, User


class ImpersonationError(Exception):
    """Authenticated request named a user that is not the token's subject.

    gdoc has no userId path parameter; the X-Env-0-Gdoc-User and
    X-Mock-Gdoc-User headers are the explicit identity channel, so a header
    naming anyone but the token's sub is the impersonation analog of gmail's
    mismatching path userId.

    Handled in ``mock_gdoc.api.app`` with the auth contract 403 body
    (``env_0_auth_client.errors.impersonation_body``), deliberately NOT the
    Google error envelope used for HTTPException.
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
    request: Request,
    x_env_0_gdoc_user: str | None = Header(None),
    x_mock_gdoc_user: str | None = Header(None),
    db: Session = Depends(get_db),
) -> str:
    """Resolve the current user.

    With auth enabled (GdocEnv_0AuthMiddleware sets
    request.state.auth_user_id): the token is mapped to a LOCAL user via
    (a) id == token ``sub``, else (b) email == token ``email`` claim
    (case-insensitive), else (c) the legacy 404. The resolved LOCAL id is the
    effective identity. An X-Env-0-Gdoc-User or X-Mock-Gdoc-User header naming
    the token's ``sub`` or the resolved local user (by id or email) is
    redundant and allowed; a header naming ANYONE else raises the contract 403
    impersonation error (after reporting an impersonation_attempt event to
    auth) -- the header can never switch or bless an identity.

    With auth disabled (the default), legacy behavior is unchanged:
    X-Env-0-Gdoc-User / X-Mock-Gdoc-User header (id or email) -> first user in DB.
    """
    requested_user = x_env_0_gdoc_user or x_mock_gdoc_user
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
        allowed = {auth_user_id, effective_id}
        if user is not None:
            allowed.add(user.email)
        if requested_user and requested_user not in allowed:
            # The middleware cannot see header-vs-sub mismatches; report here.
            # env_0_auth_client is guaranteed importable: auth_user_id is only
            # ever set by Env_0AuthMiddleware.
            from env_0_auth_client import report_impersonation

            report_impersonation(
                effective_id,
                requested_user,
                client_id=getattr(request.state, "auth_client_id", None),
                scope=" ".join(getattr(request.state, "auth_scopes", None) or []),
            )
            raise ImpersonationError(effective_id, requested_user)
        if not user:
            raise HTTPException(404, f"User {auth_user_id!r} not found")
        return effective_id

    if requested_user:
        user = db.query(User).filter(
            (User.id == requested_user) | (User.email == requested_user)
        ).first()
        if user:
            return user.id

    # Fallback: first user
    user = db.query(User).first()
    if not user:
        raise HTTPException(404, "No users in database. Run `mock-gdoc seed` first.")
    return user.id


# ---------------------------------------------------------------------------
# Shared document access helpers
# ---------------------------------------------------------------------------

VALID_ROLES = {"owner", "writer", "commenter", "reader"}
VALID_ROLES_FOR_COMMENT = {"owner", "writer", "commenter"}


def get_user_permission(db: Session, document_id: str, user_id: str) -> Permission | None:
    """Return the permission record for a user on a document, or None."""
    return db.query(Permission).filter(
        Permission.document_id == document_id,
        Permission.user_id == user_id,
    ).first()


def _get_doc_and_perm(
    db: Session, document_id: str, user_id: str,
) -> tuple[Document, Permission | None]:
    """Load document and user's permission in at most two queries.

    Raises 404 if the document does not exist.
    """
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(404, f"Document '{document_id}' not found")
    perm = None if doc.user_id == user_id else get_user_permission(db, document_id, user_id)
    return doc, perm


def check_document_access(db: Session, document_id: str, user_id: str) -> Document:
    """Return the document if the user has any access (owner or permission).

    Raises 404 if not found or no access.
    """
    doc, perm = _get_doc_and_perm(db, document_id, user_id)
    if doc.user_id == user_id or perm:
        return doc
    raise HTTPException(404, f"Document '{document_id}' not found")


def check_document_owner(db: Session, document_id: str, user_id: str) -> Document:
    """Return the document if the user is the owner.

    Raises 403 if the user has access but isn't owner, 404 otherwise.
    """
    doc, perm = _get_doc_and_perm(db, document_id, user_id)
    if doc.user_id == user_id:
        return doc
    if perm:
        raise HTTPException(403, "Only the document owner can perform this action")
    raise HTTPException(404, f"Document '{document_id}' not found")


def check_write_access(db: Session, document_id: str, user_id: str) -> Document:
    """Return the document if the user can write (owner or writer role).

    Raises 403 if the user has access but not write permission, 404 otherwise.
    """
    doc, perm = _get_doc_and_perm(db, document_id, user_id)
    if doc.user_id == user_id:
        return doc
    if perm and perm.role == "writer":
        return doc
    if perm:
        raise HTTPException(403, "You do not have write access to this document")
    raise HTTPException(404, f"Document '{document_id}' not found")


def check_comment_permission(db: Session, document_id: str, user_id: str) -> Document:
    """Return the document if the user can create/resolve comments.

    Requires owner, writer, or commenter role.
    Raises 403 if access exists but role is insufficient, 404 otherwise.
    """
    doc, perm = _get_doc_and_perm(db, document_id, user_id)
    if doc.user_id == user_id:
        return doc
    if perm and perm.role in VALID_ROLES_FOR_COMMENT:
        return doc
    if perm:
        raise HTTPException(403, "Insufficient permission to comment on this document")
    raise HTTPException(404, f"Document '{document_id}' not found")
