"""User-facing account security surface — /v1/myaccount/* (Bearer-protected).

The user-facing replacement for poking /_admin: agents inspect and revoke
their OWN consents, sessions, and security events with their own access token.

Authentication: explicit Bearer validation exactly like userinfo
(mock_auth.api.bearer) — auth runs no auth middleware on itself, so these
endpoints validate the JWT (signature/exp/iss/revocation) per request.

Authorization model (documented, pinned):
- The token IS the identity. There are no userId parameters anywhere; every
  query is filtered by the validated `sub` claim. A token for user A can never
  see or mutate user B's data — cross-user lookups 404 as if absent.
- Scope `openid` is SUFFICIENT (and required). Any user-bound token whose
  scope includes `openid` may manage the account; no extra account-management
  scope exists in the catalog.
- Pure client_credentials tokens (no subject) are rejected with 403 — they
  have no account to manage.

Errors use the pinned resource-server envelope
{"error": {code, status, message, hint, ...}} (BearerError), incl. RFC-style
404s for unknown consents/sessions.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from mock_auth.api.bearer import authenticate_bearer, require_scopes, require_user
from mock_auth.api.deps import get_db
from mock_auth.api.errors import BearerError
from mock_auth.audit import log_event, request_meta
from mock_auth.models import (
    AccessToken,
    AuthAuditLog,
    ConsentRecord,
    OAuthClient,
    RefreshToken,
    User,
)
from mock_auth.revocation import revoke_client_consent
from mock_auth.scopes import parse_scope
from mock_auth.tokens import is_expired

router = APIRouter(prefix="/v1/myaccount", tags=["myaccount"])

REQUIRED_SCOPES = {"openid"}


def _current_user(request: Request, db: Session) -> tuple[User, dict]:
    """Validate the Bearer token and resolve the acting user.

    Mirrors userinfo: 401 (missing/malformed/expired/revoked/bad-issuer),
    403 (missing `openid` scope, or token not bound to a user).
    """
    claims, _row = authenticate_bearer(request, db, where="myaccount")
    require_scopes(claims, REQUIRED_SCOPES)
    user = require_user(db, claims)
    return user, claims


def _not_found(message: str, hint: str) -> BearerError:
    return BearerError(404, "NOT_FOUND", message, hint=hint)


# --- Consented apps ---

@router.get("/apps")
def list_apps(request: Request, db: Session = Depends(get_db)):
    """Clients the token's user has (actively) consented to."""
    user, _claims = _current_user(request, db)
    rows = (
        db.query(ConsentRecord, OAuthClient)
        .join(OAuthClient, OAuthClient.client_id == ConsentRecord.client_id)
        .filter(ConsentRecord.user_id == user.id,
                ConsentRecord.revoked_at.is_(None))
        .order_by(OAuthClient.client_id)
        .all()
    )
    apps = []
    for consent, client in rows:
        token_count = (
            db.query(AccessToken)
            .filter(AccessToken.user_id == user.id,
                    AccessToken.client_id == client.client_id,
                    AccessToken.revoked == False)  # noqa: E712
            .all()
        )
        active = sum(1 for t in token_count if not is_expired(t.expires_at))
        apps.append({
            "client_id": client.client_id,
            "client_name": client.client_name,
            "granted_scopes": parse_scope(consent.granted_scopes),
            "granted_at": consent.created_at,
            "last_used_at": consent.last_used_at,
            "token_count": active,
        })
    return {"apps": apps, "user_id": user.id}


@router.post("/apps/{client_id}/revoke")
def revoke_app(client_id: str, request: Request, db: Session = Depends(get_db)):
    """De-authorize a client for the token's user: revokes the consent record
    AND all of that client's active access/refresh tokens for the user (family
    revocation). Revoking the client this very token belongs to works — the
    token dies with it (subsequent calls 401)."""
    user, _claims = _current_user(request, db)
    result = revoke_client_consent(db, user.id, client_id, via="myaccount")
    if not result["consent_revoked"]:
        db.rollback()
        raise _not_found(
            f"No active consent for client {client_id!r}.",
            "GET /v1/myaccount/apps lists clients you can revoke. Another "
            "user's consents are not visible to this token.",
        )
    db.commit()
    return {
        "status": "ok",
        "client_id": client_id,
        "revoked_access_tokens": result["revoked_access_tokens"],
        "revoked_refresh_tokens": result["revoked_refresh_tokens"],
    }


# --- Sessions (tokens) ---

@router.get("/sessions")
def list_sessions(request: Request,
                  include_revoked: bool = Query(True),
                  db: Session = Depends(get_db)):
    """The user's access tokens ("sessions", revocable by jti) and refresh-token
    families. Set include_revoked=false to list only live entries."""
    user, _claims = _current_user(request, db)

    q = db.query(AccessToken).filter(AccessToken.user_id == user.id)
    if not include_revoked:
        q = q.filter(AccessToken.revoked == False)  # noqa: E712
    sessions = []
    for t in q.order_by(AccessToken.created_at.desc(), AccessToken.jti).all():
        expired = is_expired(t.expires_at)
        sessions.append({
            "jti": t.jti,
            "client_id": t.client_id,
            "scope": parse_scope(t.scope),
            "issued_at": t.created_at,
            "expires_at": t.expires_at,
            "revoked": t.revoked,
            "expired": expired,
            "active": (not t.revoked) and (not expired),
        })

    rq = db.query(RefreshToken).filter(RefreshToken.user_id == user.id)
    if not include_revoked:
        rq = rq.filter(RefreshToken.revoked == False)  # noqa: E712
    refresh = [{
        "family_id": r.family_id,
        "client_id": r.client_id,
        "scope": parse_scope(r.scope),
        "issued_at": r.created_at,
        "expires_at": r.expires_at,
        "revoked": r.revoked,
        "rotated": r.replaced_by is not None,
    } for r in rq.order_by(RefreshToken.created_at.desc()).all()]

    return {"sessions": sessions, "refresh_tokens": refresh, "user_id": user.id}


@router.post("/sessions/{jti}/revoke")
def revoke_session(jti: str, request: Request, db: Session = Depends(get_db)):
    """Revoke one of the user's own access tokens by jti. Another user's jti
    404s (indistinguishable from nonexistent). Idempotent on already-revoked."""
    user, _claims = _current_user(request, db)
    row = db.query(AccessToken).filter(
        AccessToken.jti == jti,
        AccessToken.user_id == user.id,
    ).first()
    if row is None:
        raise _not_found(
            f"No session with jti {jti!r}.",
            "GET /v1/myaccount/sessions lists your sessions; you cannot see "
            "or revoke another user's sessions.",
        )
    if row.revoked:
        return {"status": "ok", "jti": jti, "revoked": True, "already_revoked": True}
    row.revoked = True
    log_event(db, "token_revoked", client_id=row.client_id, user_id=user.id,
              scope=row.scope,
              details={"reason": "user_session_revoke", "via": "myaccount",
                       "jti": jti},
              **request_meta(request))
    db.commit()
    return {"status": "ok", "jti": jti, "revoked": True, "already_revoked": False}


# --- Security events ---

@router.get("/security_events")
def security_events(request: Request,
                    event_type: str | None = Query(None),
                    limit: int = Query(50, ge=1, le=1000),
                    db: Session = Depends(get_db)):
    """Recent audit events for the token's user (the audit log filtered to
    user_id == sub; events not attributed to a user are never shown)."""
    user, _claims = _current_user(request, db)
    q = db.query(AuthAuditLog).filter(AuthAuditLog.user_id == user.id)
    if event_type:
        q = q.filter(AuthAuditLog.event_type == event_type)
    events = q.order_by(AuthAuditLog.id.desc()).limit(limit).all()
    return {"events": [e.to_dict() for e in events], "user_id": user.id}
