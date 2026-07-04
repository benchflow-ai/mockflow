"""OIDC discovery document and JWKS endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from mock_auth.api.deps import get_db
from mock_auth.config import get_issuer
from mock_auth.models import SigningKey
from mock_auth.scopes import SCOPES_SUPPORTED
from mock_auth.tokens import public_pem_to_jwk

router = APIRouter()


@router.get("/.well-known/openid-configuration")
def openid_configuration():
    issuer = get_issuer()
    return {
        "issuer": issuer,
        "authorization_endpoint": f"{issuer}/o/oauth2/v2/auth",
        "device_authorization_endpoint": f"{issuer}/oauth2/device/code",
        "token_endpoint": f"{issuer}/oauth2/token",
        "userinfo_endpoint": f"{issuer}/oauth2/v2/userinfo",
        "revocation_endpoint": f"{issuer}/oauth2/revoke",
        "introspection_endpoint": f"{issuer}/oauth2/introspect",
        "jwks_uri": f"{issuer}/oauth2/v3/certs",
        "response_types_supported": ["code"],
        "response_modes_supported": ["query"],
        "authorization_response_iss_parameter_supported": True,
        "subject_types_supported": ["public"],
        "id_token_signing_alg_values_supported": ["RS256"],
        "scopes_supported": SCOPES_SUPPORTED,
        "token_endpoint_auth_methods_supported": ["client_secret_post", "client_secret_basic"],
        "grant_types_supported": [
            "authorization_code",
            "refresh_token",
            "client_credentials",
            "urn:ietf:params:oauth:grant-type:device_code",
        ],
        "code_challenge_methods_supported": ["S256", "plain"],
        "claims_supported": [
            "aud", "email", "email_verified", "exp", "family_name", "given_name",
            "iat", "iss", "name", "picture", "sub",
        ],
    }


@router.get("/oauth2/v3/certs")
def jwks(db: Session = Depends(get_db)):
    """All signing keys (active + rotated) so verifiers can validate older JWTs."""
    keys = db.query(SigningKey).order_by(SigningKey.created_at.asc()).all()
    return {"keys": [public_pem_to_jwk(k.public_key_pem, k.kid, k.algorithm) for k in keys]}
