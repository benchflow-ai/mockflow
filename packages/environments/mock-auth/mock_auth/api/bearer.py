"""Shared Bearer-token validation for resource-style endpoints on auth itself.

auth has no Env_0AuthMiddleware on itself; endpoints that act as resource
servers (userinfo, /v1/myaccount/*) perform explicit Bearer validation here:
signature (RS256, kid lookup against signing_keys), expiry, issuer, and
server-side revocation. Error shapes follow the pinned resource-server
envelope (BearerError) with WWW-Authenticate headers.

The token IS the identity: callers never pass a userId — every protected
endpoint derives the acting user from the validated `sub` claim, so a token
for one user can never read or mutate another user's data.
"""

from __future__ import annotations

from datetime import datetime, timezone

import jwt as pyjwt
from fastapi import Request
from sqlalchemy.orm import Session

from mock_auth.api.errors import BearerError
from mock_auth.audit import log_event, request_meta
from mock_auth.config import get_issuer
from mock_auth.models import AccessToken, SigningKey, User
from mock_auth.scopes import parse_scope
from mock_auth.tokens import sha256_hex, verify_jwt


def bearer_401(message: str, hint: str) -> BearerError:
    return BearerError(
        401, "UNAUTHENTICATED", message, hint=hint,
        www_authenticate=f'Bearer error="invalid_token", error_description="{message}"',
    )


def authenticate_bearer(
    request: Request, db: Session, *, where: str = "userinfo"
) -> tuple[dict, AccessToken | None]:
    """Validate the Bearer JWT (signature, expiry, revocation). Returns (claims, row).

    `where` tags audit events with the endpoint family that rejected the token.
    """
    header = request.headers.get("authorization", "")
    if not header.lower().startswith("bearer "):
        raise bearer_401(
            "Missing Bearer token.",
            "Send `Authorization: Bearer <access_token>`; obtain a token from "
            "POST /oauth2/token.",
        )
    token = header[7:].strip()

    try:
        unverified_header = pyjwt.get_unverified_header(token)
    except pyjwt.PyJWTError:
        log_event(db, "invalid_token", details={"reason": "malformed JWT", "where": where},
                  **request_meta(request))
        db.commit()
        raise bearer_401("Malformed access token.",
                         "The access token must be the RS256 JWT issued by auth.")

    kid = unverified_header.get("kid")
    key = db.query(SigningKey).filter(SigningKey.kid == kid).first()
    if key is None:
        log_event(db, "invalid_token", details={"reason": f"unknown kid {kid!r}",
                                                "where": where},
                  **request_meta(request))
        db.commit()
        raise bearer_401(f"Unknown signing key id: {kid!r}.",
                         "Refetch JWKS from /oauth2/v3/certs; the key may have rotated.")

    try:
        claims = verify_jwt(token, key.public_key_pem, verify_exp=True)
    except pyjwt.ExpiredSignatureError:
        expired_claims = pyjwt.decode(token, options={"verify_signature": False,
                                                      "verify_exp": False})
        exp = expired_claims.get("exp")
        exp_iso = (datetime.fromtimestamp(exp, tz=timezone.utc).isoformat()
                   if isinstance(exp, (int, float)) else "unknown")
        log_event(db, "token_expired_during_use",
                  client_id=expired_claims.get("client_id"),
                  user_id=expired_claims.get("sub"),
                  scope=expired_claims.get("scope"),
                  details={"jti": expired_claims.get("jti"), "expired_at": exp_iso,
                           "where": where},
                  **request_meta(request))
        db.commit()
        raise bearer_401(
            f"Access token expired at {exp_iso}.",
            f"Use your refresh token at POST {get_issuer()}/oauth2/token with "
            "grant_type=refresh_token to obtain a new access token.",
        )
    except pyjwt.PyJWTError as exc:
        log_event(db, "invalid_token", details={"reason": str(exc), "where": where},
                  **request_meta(request))
        db.commit()
        raise bearer_401("Invalid access token signature.",
                         "The token was not signed by auth or is corrupted.")

    if claims.get("iss") != get_issuer():
        log_event(db, "invalid_token", details={"reason": "issuer mismatch",
                                                "where": where},
                  **request_meta(request))
        db.commit()
        raise bearer_401("Token issuer mismatch.",
                         f"Expected iss={get_issuer()!r}.")

    row = db.query(AccessToken).filter(AccessToken.token_hash == sha256_hex(token)).first()
    if row is not None and row.revoked:
        log_event(db, "invalid_token", client_id=row.client_id, user_id=row.user_id,
                  scope=row.scope,
                  details={"reason": "revoked", "jti": row.jti, "where": where},
                  **request_meta(request))
        db.commit()
        raise bearer_401("Access token has been revoked.",
                         "Obtain a new token via POST /oauth2/token.")

    return claims, row


def require_scopes(claims: dict, required: set[str], *, any_of: bool = True) -> set[str]:
    """403 unless the token carries the required scope(s). Returns the token scopes."""
    scopes = set(parse_scope(claims.get("scope")))
    granted = scopes & required
    if (any_of and not granted) or (not any_of and required - scopes):
        raise BearerError(
            403, "PERMISSION_DENIED",
            "Token does not carry the scope(s) required for this endpoint.",
            hint=f"Request {'one of' if any_of else 'all of'}: "
                 f"{', '.join(sorted(required))}.",
            extra={"required_scopes": sorted(required),
                   "token_scopes": sorted(scopes)},
        )
    return scopes


def require_user(db: Session, claims: dict) -> User:
    """403 unless the token's `sub` is a real user (rejects pure
    client_credentials tokens that are not bound to a user)."""
    user = db.query(User).filter(User.id == claims.get("sub")).first()
    if user is None:
        raise BearerError(
            403, "PERMISSION_DENIED",
            "Token is not bound to a user (client_credentials token without subject).",
            hint="Use a user-bound token (authorization_code/device flow, or "
                 "client_credentials with subject=).",
        )
    return user
