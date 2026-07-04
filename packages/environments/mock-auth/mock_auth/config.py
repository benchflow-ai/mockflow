"""Runtime configuration for auth (env-var driven, mock-friendly defaults)."""

from __future__ import annotations

import os

DEFAULT_PORT = 9000

# Token lifetimes (seconds)
ACCESS_TOKEN_TTL = 3600          # 1 hour
REFRESH_TOKEN_TTL = 30 * 86400   # 30 days
AUTH_CODE_TTL = 30               # 30 seconds, single use
DEVICE_CODE_TTL = 900            # 15 minutes
ID_TOKEN_TTL = 3600

FIXED_KID = "env-0-auth-key-001"


def get_issuer() -> str:
    """Issuer string for JWTs and OIDC discovery (overridable via AUTH_ISSUER)."""
    return os.environ.get("AUTH_ISSUER", f"http://localhost:{DEFAULT_PORT}")
