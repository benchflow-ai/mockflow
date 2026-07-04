"""Shared dependencies: DB session and API-key auth.

Auth matches real Stripe: `Authorization: Bearer sk_test_...` or HTTP Basic
with the key as username and empty password (`curl -u sk_test_...:`).
Valid keys are seeded in the `api_keys` table (default:
`sk_test_env_0_51deterministic`).

auth coexistence (AUTH_ENABLED=1): the per-request key dependency
becomes JWT-aware. When ``StripeMockAuthMiddleware`` has validated a auth
JWT (``request.state.auth_client_id`` set), the JWT IS the credential and no
``sk_test_`` key is consulted. A bare ``sk_test_`` key carries no validated JWT
and is insufficient under auth (the middleware, running first, rejects a
non-JWT Bearer value with a contract 401 before this dependency runs -- legacy
keys behave like slack's xoxb-). When AUTH_ENABLED is unset, behavior is
byte-for-byte today's: a seeded ``sk_test_`` key is required and JWTs are
irrelevant. stripe is single-tenant with no {userId} path params, so there
is no impersonation guard -- the value here is per-resource scope enforcement.
"""

from __future__ import annotations

import base64
import binascii
import os

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from mock_stripe.models import ApiKey, get_session_factory

from .errors import StripeError

_MISSING_KEY_MESSAGE = (
    "You did not provide an API key. You need to provide your API key in the "
    "Authorization header, using Bearer auth (e.g. 'Authorization: Bearer "
    "YOUR_SECRET_KEY'). See https://stripe.com/docs/api#authentication for details."
)
_AUTH_REQUIRED_MESSAGE = (
    "This server requires a auth access token (AUTH_ENABLED=1). A bare "
    "API key is not sufficient. Provide a valid Bearer JWT issued by auth."
)


def _auth_enabled() -> bool:
    """Mirror env_0_auth_client.is_auth_enabled() without importing the optional dep."""
    return os.environ.get("AUTH_ENABLED", "").strip().lower() in ("1", "true", "yes")


def get_db() -> Session:
    SessionLocal = get_session_factory()
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _mask_key(key: str) -> str:
    if len(key) <= 12:
        return key[:4] + "*" * max(len(key) - 4, 0)
    return key[:8] + "*" * (len(key) - 12) + key[-4:]


def extract_api_key(request: Request) -> str | None:
    """Pull the secret key from Bearer or Basic auth."""
    auth = request.headers.get("authorization") or ""
    if not auth:
        return None
    scheme, _, credential = auth.partition(" ")
    scheme = scheme.lower()
    credential = credential.strip()
    if scheme == "bearer":
        return credential or None
    if scheme == "basic":
        try:
            decoded = base64.b64decode(credential, validate=True).decode("utf-8")
        except (binascii.Error, UnicodeDecodeError, ValueError):
            return None
        return decoded.split(":", 1)[0] or None
    return None


def require_api_key(request: Request, db: Session = Depends(get_db)) -> ApiKey | None:
    # --- auth coexistence ---
    # A JWT validated by StripeMockAuthMiddleware IS the credential: the
    # middleware (outermost) set request.state.auth_client_id. No sk_test_ key
    # is consulted, and the router-level dependency value is unused anyway.
    if getattr(request.state, "auth_client_id", None) is not None:
        return None
    # Auth enabled but no validated JWT reached here. In practice unreachable
    # for guarded /v1 routes (the middleware rejects a non-JWT Bearer -- e.g. a
    # bare sk_test_ key -- with a contract 401 before routing); kept as
    # defense-in-depth so legacy keys can never satisfy the gate under auth.
    if _auth_enabled():
        raise StripeError(401, _AUTH_REQUIRED_MESSAGE)

    # --- legacy mode (AUTH_ENABLED unset): byte-identical to today ---
    key = extract_api_key(request)
    if not key:
        raise StripeError(401, _MISSING_KEY_MESSAGE)
    row = db.query(ApiKey).filter(ApiKey.id == key).first()
    if not row:
        # Real Stripe replies with type+message only; the mock adds
        # code="api_key_invalid" for machine-readability (see API_NOTES.md).
        raise StripeError(
            401,
            f"Invalid API Key provided: {_mask_key(key)}",
            code="api_key_invalid",
            doc_url=None,
        )
    return row
