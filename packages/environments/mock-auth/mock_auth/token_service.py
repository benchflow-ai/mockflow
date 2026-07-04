"""Token issuance service — mints JWT access tokens, opaque refresh tokens, id_tokens.

Used by the token endpoint, /_admin/issue_token, and seed scenarios.
"""

from __future__ import annotations

import random

from sqlalchemy.orm import Session

from mock_auth.config import ACCESS_TOKEN_TTL, ID_TOKEN_TTL, REFRESH_TOKEN_TTL, get_issuer
from mock_auth.models import AccessToken, OAuthClient, RefreshToken, SigningKey, User
from mock_auth.tokens import (
    iso_in,
    new_family_id,
    new_jti,
    new_refresh_token,
    sha256_hex,
    sign_jwt,
    utc_ts,
)


def get_active_signing_key(db: Session) -> SigningKey:
    key = (
        db.query(SigningKey)
        .filter(SigningKey.is_active == True)  # noqa: E712
        .order_by(SigningKey.created_at.desc())
        .first()
    )
    if key is None:
        raise RuntimeError("No active signing key. Run `mock-auth seed` first.")
    return key


def access_token_ttl_for(client: OAuthClient) -> int:
    """Effective access-token TTL for a client: its per-client override
    (oauth_clients.access_token_ttl, seconds) when set and positive, else the
    1h default (config.ACCESS_TOKEN_TTL)."""
    ttl = getattr(client, "access_token_ttl", None)
    if ttl is not None and ttl > 0:
        return int(ttl)
    return ACCESS_TOKEN_TTL


def issue_access_token(
    db: Session,
    client: OAuthClient,
    user: User | None,
    scope: str,
    *,
    expires_in: int | None = None,
    act: dict | None = None,
    rng: random.Random | None = None,
) -> tuple[str, AccessToken]:
    """Mint an RS256 JWT access token and record it. Returns (jwt_string, row).

    `expires_in=None` (the default) resolves to the client's per-client TTL
    when configured, else the 1h default — so every grant type honors
    oauth_clients.access_token_ttl unless the caller explicitly overrides it
    (e.g. /_admin/issue_token with expires_in).
    """
    if expires_in is None:
        expires_in = access_token_ttl_for(client)
    key = get_active_signing_key(db)
    now = utc_ts()
    jti = new_jti(rng)
    if user is not None:
        sub = user.id
        email = user.email
    else:
        # Pure client_credentials token (no subject impersonation):
        # the client itself is the principal, service-account style.
        sub = client.client_id
        email = f"{client.client_id}@service-accounts.clawsbench.local"
    claims = {
        "iss": get_issuer(),
        "sub": sub,
        "aud": client.client_id,
        "exp": now + expires_in,
        "iat": now,
        "jti": jti,
        "scope": scope,
        "email": email,
        "client_id": client.client_id,
    }
    if act:
        claims["act"] = act
    token = sign_jwt(claims, key.private_key_pem, key.kid)
    row = AccessToken(
        token_hash=sha256_hex(token),
        jti=jti,
        client_id=client.client_id,
        user_id=user.id if user is not None else None,
        scope=scope,
        expires_at=iso_in(expires_in),
    )
    db.add(row)
    return token, row


def issue_refresh_token(
    db: Session,
    client: OAuthClient,
    user: User,
    scope: str,
    *,
    family_id: str | None = None,
    rng: random.Random | None = None,
) -> tuple[str, RefreshToken]:
    raw = new_refresh_token(rng)
    row = RefreshToken(
        token_hash=sha256_hex(raw),
        client_id=client.client_id,
        user_id=user.id,
        scope=scope,
        family_id=family_id or new_family_id(rng),
        expires_at=iso_in(REFRESH_TOKEN_TTL),
    )
    db.add(row)
    return raw, row


#: Audience marker for cross-service web-SSO identity assertions. Resource
#: servers don't enforce it (mock), but it documents intent and distinguishes
#: these from OAuth access/id tokens.
WEB_SSO_AUDIENCE = "env-0-web-sso"

#: Identity assertions are deliberately short-lived: they are single-use
#: hand-offs consumed immediately by the resource server's SSO callback.
WEB_SSO_ASSERTION_TTL = 120  # seconds


def issue_identity_assertion(
    db: Session,
    user: User,
    *,
    ttl: int = WEB_SSO_ASSERTION_TTL,
) -> str:
    """Mint a short-lived RS256 *identity assertion* for web-session SSO.

    Shaped like a minimal OIDC id_token (iss/sub/email/aud/exp/iat) and signed
    with the active signing key, so any environment resource server can verify it
    against ``/oauth2/v3/certs`` -- the same keys the Bearer middleware trusts.
    Carries ``purpose=web_sso`` so a verifier never confuses it with an access
    token. Used by ``POST /web/login`` to hand the just-authenticated identity
    to a cross-origin web UI (e.g. gmail's ``/web/auth/callback``).
    """
    key = get_active_signing_key(db)
    now = utc_ts()
    claims = {
        "iss": get_issuer(),
        "sub": user.id,
        "aud": WEB_SSO_AUDIENCE,
        "purpose": "web_sso",
        "exp": now + ttl,
        "iat": now,
        "jti": new_jti(),
        "email": user.email,
        "email_verified": True,
        "name": user.display_name,
    }
    return sign_jwt(claims, key.private_key_pem, key.kid)


def issue_id_token(
    db: Session,
    client: OAuthClient,
    user: User,
    *,
    nonce: str | None = None,
) -> str:
    """OIDC id_token (issued when scope contains `openid`). at_hash intentionally omitted."""
    key = get_active_signing_key(db)
    now = utc_ts()
    claims = {
        "iss": get_issuer(),
        "sub": user.id,
        "aud": client.client_id,
        "exp": now + ID_TOKEN_TTL,
        "iat": now,
        "email": user.email,
        "email_verified": True,
        "name": user.display_name,
        "given_name": user.given_name or "",
        "family_name": user.family_name or "",
        "picture": user.picture_url or "",
    }
    if nonce:
        claims["nonce"] = nonce
    return sign_jwt(claims, key.private_key_pem, key.kid)
