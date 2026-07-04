"""Environment-variable configuration for auth-client.

All values are read at call time (no module-level caching) so tests can
monkeypatch the environment freely.

Env vars:
- AUTH_ENABLED   -- "1"/"true"/"yes" (case-insensitive) turns auth on.
- AUTH_URL       -- base URL of the auth server (default http://localhost:9000).
- AUTH_ISSUER    -- expected `iss` claim (default = AUTH_URL).
- AUTH_INTROSPECT-- "1"/"true"/"yes" enables per-request revocation checks.
- AUTH_REPORT    -- security-event reporting; ON by default, "0"/"false"/"no" disables.
- AUTH_JWKS_TTL  -- JWKS cache TTL in seconds (default 300).
"""

import os

DEFAULT_AUTH_URL = "http://localhost:9000"
DEFAULT_JWKS_TTL = 300

_TRUTHY = ("1", "true", "yes")
_FALSY = ("0", "false", "no")


def is_auth_enabled() -> bool:
    """True when AUTH_ENABLED is "1", "true" or "yes" (case-insensitive)."""
    return os.environ.get("AUTH_ENABLED", "").strip().lower() in _TRUTHY


def get_auth_url() -> str:
    """Base URL of the auth server (AUTH_URL, default http://localhost:9000)."""
    url = os.environ.get("AUTH_URL", "").strip() or DEFAULT_AUTH_URL
    return url.rstrip("/") or DEFAULT_AUTH_URL


def get_issuer() -> str:
    """Expected `iss` claim (AUTH_ISSUER, default = the auth base URL)."""
    issuer = os.environ.get("AUTH_ISSUER", "").strip()
    if issuer:
        return issuer.rstrip("/")
    return get_auth_url()


def is_introspect_enabled() -> bool:
    """True when AUTH_INTROSPECT is truthy (per-request revocation checking)."""
    return os.environ.get("AUTH_INTROSPECT", "").strip().lower() in _TRUTHY


def is_report_enabled() -> bool:
    """Security-event reporting toggle. Default ON; "0"/"false"/"no" disables (tests use 0)."""
    return os.environ.get("AUTH_REPORT", "1").strip().lower() not in _FALSY


def get_jwks_ttl() -> int:
    """JWKS in-process cache TTL in seconds (AUTH_JWKS_TTL, default 300)."""
    raw = os.environ.get("AUTH_JWKS_TTL", "").strip()
    try:
        return int(raw)
    except ValueError:
        return DEFAULT_JWKS_TTL
