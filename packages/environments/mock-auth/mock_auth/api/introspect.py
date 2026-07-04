"""Token introspection — RFC 7662.

Mock divergence: no client authentication is required to introspect (real
Google has no introspection endpoint at all; RFC 7662 requires resource-server
auth). Documented in API_NOTES.md.
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from mock_auth.api.deps import get_db
from mock_auth.api.errors import OAuthError
from mock_auth.audit import log_event, request_meta
from mock_auth.config import get_issuer
from mock_auth.models import AccessToken, RefreshToken
from mock_auth.tokens import decode_jwt_unverified, is_expired, sha256_hex

router = APIRouter()


def _iso_to_unix(iso_str: str) -> int | None:
    try:
        dt = datetime.fromisoformat(iso_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return int(dt.timestamp())
    except (ValueError, TypeError):
        return None


@router.post("/oauth2/introspect")
async def introspect(request: Request, db: Session = Depends(get_db)):
    form = await request.form()
    token = form.get("token")
    if not token:
        raise OAuthError("invalid_request", "Missing required parameter: token.",
                         hint="POST the token (access or refresh) as a form field.")

    token_hash = sha256_hex(token)

    # --- Access token (the raw token is the JWT) ---
    row = db.query(AccessToken).filter(AccessToken.token_hash == token_hash).first()
    if row is not None:
        active = (not row.revoked) and (not is_expired(row.expires_at))
        log_event(db, "token_introspected", client_id=row.client_id, user_id=row.user_id,
                  scope=row.scope,
                  details={"active": active, "jti": row.jti,
                           "reason": ("revoked" if row.revoked
                                      else "expired" if not active else "active")},
                  **request_meta(request))
        db.commit()
        if not active:
            return {"active": False}
        try:
            _, claims = decode_jwt_unverified(token)
        except Exception:
            claims = {}
        return {
            "active": True,
            "scope": row.scope,
            "client_id": row.client_id,
            "username": claims.get("email"),
            "sub": claims.get("sub", row.user_id),
            "aud": claims.get("aud", row.client_id),
            "iss": claims.get("iss", get_issuer()),
            "token_type": "Bearer",
            "exp": claims.get("exp", _iso_to_unix(row.expires_at)),
            "iat": claims.get("iat"),
            "jti": row.jti,
        }

    # --- Refresh token (opaque rt_...) ---
    rrow = db.query(RefreshToken).filter(RefreshToken.token_hash == token_hash).first()
    if rrow is not None:
        active = (not rrow.revoked) and (not is_expired(rrow.expires_at))
        log_event(db, "token_introspected", client_id=rrow.client_id, user_id=rrow.user_id,
                  scope=rrow.scope,
                  details={"active": active, "token_type": "refresh_token",
                           "reason": ("revoked" if rrow.revoked
                                      else "expired" if not active else "active")},
                  **request_meta(request))
        db.commit()
        if not active:
            return {"active": False}
        return {
            "active": True,
            "scope": rrow.scope,
            "client_id": rrow.client_id,
            "sub": rrow.user_id,
            "iss": get_issuer(),
            "token_type": "refresh_token",
            "exp": _iso_to_unix(rrow.expires_at),
        }

    log_event(db, "token_introspected",
              details={"active": False, "reason": "unknown token"},
              **request_meta(request))
    db.commit()
    return {"active": False}
