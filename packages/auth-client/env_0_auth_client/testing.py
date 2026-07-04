"""Test utilities for environment packages: keypairs, JWTs and JWKS without HTTP.

Typical usage in a resource server's test suite:

    from env_0_auth_client.testing import generate_test_keypair, jwks_for, make_jwt

    private_key, public_key = generate_test_keypair()
    jwks = jwks_for(public_key, kid="test-key-001")
    app.add_middleware(Env_0AuthMiddleware, scope_map=SCOPE_MAP, jwks_static=jwks)

    token = make_jwt(private_key=private_key, kid="test-key-001",
                     sub="user_001", scope="gmail.readonly")
    client.get("/gmail/v1/users/me/messages",
               headers={"Authorization": f"Bearer {token}"})

``jwks_static`` accepts either the JWKS dict itself or a zero-arg callable
returning one (swap the callable's return value to exercise key rotation /
unknown-kid refetch behavior).
"""

import time
import uuid

import jwt as pyjwt
from cryptography.hazmat.primitives.asymmetric import rsa

from env_0_auth_client import config

DEFAULT_KID = "env-0-auth-key-001"


def generate_test_keypair() -> tuple[rsa.RSAPrivateKey, rsa.RSAPublicKey]:
    """Generate a fresh RSA-2048 keypair. Returns (private_key, public_key)."""
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return private_key, private_key.public_key()


def jwks_for(public_key: rsa.RSAPublicKey, kid: str = DEFAULT_KID) -> dict:
    """Build a JWKS dict ({"keys": [...]}) for one RSA public key."""
    jwk = pyjwt.algorithms.RSAAlgorithm.to_jwk(public_key, as_dict=True)
    jwk.update({"kid": kid, "alg": "RS256", "use": "sig"})
    return {"keys": [jwk]}


def make_jwt(
    *,
    private_key,
    kid: str = DEFAULT_KID,
    sub: str = "user_001",
    client_id: str = "gws-cli",
    scope: str = "",
    issuer: str | None = None,
    audience: str | None = None,
    email: str | None = None,
    expires_in: int = 3600,
    jti: str | None = None,
    extra_claims: dict | None = None,
) -> str:
    """Mint an RS256 access token shaped exactly like auth's.

    ``expires_in`` may be negative to produce an already-expired token.
    ``issuer`` defaults to the configured issuer (AUTH_ISSUER /
    AUTH_URL / http://localhost:9000). ``audience`` defaults to
    ``client_id`` (auth sets aud == client_id).
    """
    now = int(time.time())
    claims = {
        "iss": issuer or config.get_issuer(),
        "sub": sub,
        "aud": audience or client_id,
        "exp": now + expires_in,
        "iat": now,
        "jti": jti or ("tok_" + uuid.uuid4().hex[:24]),
        "scope": scope,
        "email": email or f"{sub}@clawsbench.local",
        "client_id": client_id,
    }
    if extra_claims:
        claims.update(extra_claims)
    return pyjwt.encode(claims, private_key, algorithm="RS256", headers={"kid": kid})
