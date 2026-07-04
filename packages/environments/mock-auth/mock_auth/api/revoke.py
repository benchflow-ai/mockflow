"""Token revocation — RFC 7009. Always returns 200 (never reveals token existence)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from mock_auth.api.deps import get_db
from mock_auth.audit import log_event, request_meta
from mock_auth.models import AccessToken, RefreshToken
from mock_auth.tokens import sha256_hex

router = APIRouter()


@router.post("/oauth2/revoke")
async def revoke(request: Request, db: Session = Depends(get_db)):
    form = await request.form()
    token = form.get("token")
    if not token:
        # RFC 7009: invalid submissions still get 200 unless unsupported_token_type.
        return {}

    token_hash = sha256_hex(token)

    row = db.query(AccessToken).filter(AccessToken.token_hash == token_hash).first()
    if row is not None:
        if not row.revoked:
            row.revoked = True
            log_event(db, "token_revoked", client_id=row.client_id, user_id=row.user_id,
                      scope=row.scope,
                      details={"reason": "revocation_endpoint", "token_type": "access_token",
                               "jti": row.jti},
                      **request_meta(request))
            db.commit()
        return {}

    rrow = db.query(RefreshToken).filter(RefreshToken.token_hash == token_hash).first()
    if rrow is not None:
        # Revoking a refresh token kills its whole rotation family.
        family = db.query(RefreshToken).filter(RefreshToken.family_id == rrow.family_id).all()
        changed = False
        for member in family:
            if not member.revoked:
                member.revoked = True
                changed = True
        if changed:
            log_event(db, "token_revoked", client_id=rrow.client_id, user_id=rrow.user_id,
                      scope=rrow.scope,
                      details={"reason": "revocation_endpoint", "token_type": "refresh_token",
                               "family_id": rrow.family_id},
                      **request_meta(request))
            db.commit()
        return {}

    # Unknown token: still 200 per RFC 7009.
    return {}
