"""In-process JWKS cache with TTL and unknown-kid single refetch.

The key source is either the auth JWKS endpoint
(``{auth_base_url}/oauth2/v3/certs``) or a static source supplied by tests
(``jwks_static`` on the middleware): a JWKS dict, or a zero-arg callable
returning one (callables let tests exercise the refetch logic by swapping
the returned JWKS).
"""

import asyncio
import time
from collections.abc import Callable

import httpx
import jwt

JWKS_PATH = "/oauth2/v3/certs"


class UnknownKeyError(Exception):
    """Raised when a token's `kid` is not present in the JWKS, even after refetch."""


class JWKSCache:
    def __init__(
        self,
        auth_base_url: str | None = None,
        static: dict | Callable[[], dict] | None = None,
        ttl: int = 300,
        transport: httpx.AsyncBaseTransport | None = None,
    ):
        if auth_base_url is None and static is None:
            raise ValueError("JWKSCache needs an auth_base_url or a static JWKS source")
        self._url = auth_base_url.rstrip("/") + JWKS_PATH if auth_base_url else None
        self._static = static
        self._ttl = ttl
        self._transport = transport
        self._keys: dict[str, object] = {}
        self._fetched_at: float | None = None
        # Serializes refreshes so N concurrent cold-cache requests trigger ONE
        # JWKS fetch instead of a thundering herd.
        self._lock = asyncio.Lock()

    async def _load_jwks(self) -> dict:
        if self._static is not None:
            return self._static() if callable(self._static) else self._static
        async with httpx.AsyncClient(transport=self._transport, timeout=5.0) as client:
            resp = await client.get(self._url)
            resp.raise_for_status()
            return resp.json()

    async def _refresh(self) -> None:
        data = await self._load_jwks()
        keys: dict[str, object] = {}
        for jwk_dict in data.get("keys", []):
            kid = jwk_dict.get("kid")
            if not kid:
                continue
            try:
                keys[kid] = jwt.PyJWK.from_dict(jwk_dict, algorithm="RS256").key
            except Exception:
                continue  # skip unusable keys, keep the rest
        self._keys = keys
        self._fetched_at = time.monotonic()

    def _is_stale(self) -> bool:
        return (self._fetched_at is None
                or (time.monotonic() - self._fetched_at) >= self._ttl)

    async def get_key(self, kid: str):
        """Return the verification key for `kid`.

        Refreshes when the cache is empty or older than the TTL. On an unknown
        `kid`, refetches ONCE (handles key rotation) and then fails with
        UnknownKeyError if the kid is still absent. Refreshes are serialized
        behind an asyncio.Lock with a double-check, so concurrent requests on
        a cold/expired cache trigger a single fetch (no thundering herd).
        """
        if self._is_stale():
            async with self._lock:
                if self._is_stale():
                    await self._refresh()
        key = self._keys.get(kid)
        if key is None:
            async with self._lock:
                key = self._keys.get(kid)
                if key is None:
                    await self._refresh()  # unknown kid: single refetch, then fail
                    key = self._keys.get(kid)
        if key is None:
            raise UnknownKeyError(f"Signing key {kid!r} not found in JWKS")
        return key
