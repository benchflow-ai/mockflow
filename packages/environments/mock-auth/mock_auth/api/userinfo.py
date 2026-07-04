"""UserInfo endpoint — Bearer-protected, scope-gated profile fields.

Bearer validation lives in mock_auth.api.bearer (shared with /v1/myaccount).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from mock_auth.api.bearer import authenticate_bearer, require_user
from mock_auth.api.deps import get_db
from mock_auth.api.errors import BearerError
from mock_auth.scopes import parse_scope

router = APIRouter()

USERINFO_SCOPES = {"openid", "email", "profile"}


@router.get("/oauth2/v2/userinfo")
@router.post("/oauth2/v2/userinfo")
def userinfo(request: Request, db: Session = Depends(get_db)):
    claims, _row = authenticate_bearer(request, db, where="userinfo")
    scopes = set(parse_scope(claims.get("scope")))

    granted_userinfo = scopes & USERINFO_SCOPES
    if not granted_userinfo:
        raise BearerError(
            403, "PERMISSION_DENIED",
            "Token has none of the scopes required for userinfo.",
            hint="Request at least one of: openid, email, profile.",
            extra={"required_scopes": sorted(USERINFO_SCOPES),
                   "token_scopes": sorted(scopes)},
        )

    user = require_user(db, claims)

    result: dict = {}
    if "openid" in scopes:
        result["sub"] = user.id
    if "profile" in scopes:
        result.update({
            "sub": user.id,
            "name": user.display_name,
            "given_name": user.given_name or "",
            "family_name": user.family_name or "",
            "picture": user.picture_url or "",
        })
    if "email" in scopes:
        result.setdefault("sub", user.id)
        result["email"] = user.email
        result["email_verified"] = True
    return result
