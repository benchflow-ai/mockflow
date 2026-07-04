"""Env_0AuthMiddleware -- Bearer-JWT validation for environment resource servers.

Validates RS256 access tokens issued by auth against its JWKS, enforces
per-route scope requirements (OR logic), sets ``request.state.auth_*`` for the
deps layer, and reports security events back to auth (fire-and-forget).

Usage (the retrofit pattern, see contract):

    from env_0_auth_client import Env_0AuthMiddleware, is_auth_enabled
    from env_0_gmail.auth_scopes import SCOPE_MAP

    if is_auth_enabled():
        app.add_middleware(Env_0AuthMiddleware, scope_map=SCOPE_MAP)
"""

import os
import time
from datetime import datetime, timezone

import httpx
import jwt
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from env_0_auth_client import config, errors, reporting
from env_0_auth_client.jwks import JWKSCache, UnknownKeyError
from env_0_auth_client.routing import match_route
from env_0_auth_client.scopes import ScopeMap, has_any_scope

DEFAULT_EXEMPT_PREFIXES = ("/_admin", "/health", "/dev", "/docs", "/openapi.json", "/web")

_INTROSPECT_CACHE_TTL = 10.0
# Purge expired introspection entries once the cache reaches this many keys, so a
# long-lived resource server can't accumulate unbounded memory across many tokens.
_INTROSPECT_CACHE_MAX = 1024


def _iso_utc(unix_ts: float) -> str:
    """Unix timestamp -> ISO-8601 UTC string (e.g. 2026-06-10T12:00:00Z)."""
    return datetime.fromtimestamp(unix_ts, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class Env_0AuthMiddleware(BaseHTTPMiddleware):
    """Starlette BaseHTTPMiddleware enforcing auth Bearer JWTs.

    Args:
        app: the ASGI app (passed automatically by ``app.add_middleware``).
        auth_base_url: auth base URL; default env AUTH_URL or
            http://localhost:9000. Used for JWKS, introspection and reporting.
        scope_map: ``{(METHOD, path_template): [scopes...]}`` OR-logic scope
            requirements. Routes absent from the map require auth only.
        audience: when set, the token ``aud`` must match; default off
            (any audience accepted).
        exempt_prefixes: path prefixes that bypass auth entirely (plus all
            OPTIONS requests).
        issuer: expected ``iss`` claim; default env AUTH_ISSUER, falling
            back to the resolved auth base URL.
        jwks_static: a JWKS dict or zero-arg callable returning one -- used by
            tests so that NO HTTP is needed for key fetching.
        jwks_ttl: JWKS cache TTL seconds; default env AUTH_JWKS_TTL or 300.
        introspect_transport: optional httpx async transport for the
            ``/oauth2/introspect`` calls (test hook).
    """

    def __init__(
        self,
        app,
        auth_base_url: str | None = None,
        scope_map: ScopeMap | None = None,
        audience: str | None = None,
        exempt_prefixes: tuple[str, ...] = DEFAULT_EXEMPT_PREFIXES,
        issuer: str | None = None,
        jwks_static=None,
        jwks_ttl: int | None = None,
        introspect_transport: httpx.AsyncBaseTransport | None = None,
    ):
        super().__init__(app)
        self.auth_base_url = (auth_base_url or config.get_auth_url()).rstrip("/")
        env_issuer = os.environ.get("AUTH_ISSUER", "").strip()
        self.issuer = (issuer or env_issuer or self.auth_base_url).rstrip("/")
        self.scope_map: ScopeMap = dict(scope_map or {})
        self.audience = audience
        # Normalized for segment-boundary matching: "/docs" exempts "/docs" and
        # "/docs/...", but NOT "/docsx" or "//docs" (no prefix-string tricks).
        self.exempt_prefixes = tuple(p.rstrip("/") or "/" for p in exempt_prefixes)
        self._jwks = JWKSCache(
            auth_base_url=self.auth_base_url,
            static=jwks_static,
            ttl=jwks_ttl if jwks_ttl is not None else config.get_jwks_ttl(),
        )
        self._introspect_transport = introspect_transport
        self._introspect_cache: dict[str, tuple[float, bool]] = {}
        self._aggregator = reporting.ResourceAccessAggregator()

    # ------------------------------------------------------------------ dispatch

    def _is_exempt(self, path: str) -> bool:
        """Segment-boundary prefix matching: an exempt prefix only matches the
        exact path or a true sub-path ('/docs', '/docs/x' -- never '/docsx',
        and '//_admin' is not '/_admin')."""
        for prefix in self.exempt_prefixes:
            if prefix == "/":
                return True
            if path == prefix or path.startswith(prefix + "/"):
                return True
        return False

    async def dispatch(self, request: Request, call_next) -> Response:
        path = request.url.path
        if request.method == "OPTIONS" or self._is_exempt(path):
            return await call_next(request)

        # 1. Bearer extraction
        auth_header = request.headers.get("Authorization", "")
        scheme, _, token = auth_header.partition(" ")
        token = token.strip()
        if scheme.lower() != "bearer" or not token:
            # No token presented: nothing to attribute, so no event is reported.
            return self._unauthenticated(
                "Request is missing a valid Bearer access token.",
                hint=(
                    f"Obtain an access token from {self.auth_base_url} and send it "
                    "as 'Authorization: Bearer <token>'."
                ),
            )

        # 2. Header / kid
        try:
            header = jwt.get_unverified_header(token)
        except jwt.InvalidTokenError as exc:
            await self._report_invalid(request, reason=f"malformed token: {exc}")
            return self._unauthenticated(
                "Invalid access token: token is malformed.",
                hint="Obtain a fresh access token from auth.",
            )
        kid = header.get("kid")
        if not kid:
            await self._report_invalid(request, reason="token header missing kid")
            return self._unauthenticated(
                "Invalid access token: missing key id (kid).",
                hint="Obtain a fresh access token from auth.",
            )

        # 3. JWKS lookup (cached, TTL, unknown-kid single refetch)
        try:
            key = await self._jwks.get_key(kid)
        except UnknownKeyError:
            await self._report_invalid(request, reason=f"unknown kid {kid!r}")
            return self._unauthenticated(
                f"Invalid access token: unknown signing key {kid!r}.",
                hint="The signing key may have rotated; obtain a fresh access token.",
            )
        except Exception as exc:
            await self._report_invalid(request, reason=f"jwks fetch failed: {exc}")
            return self._unauthenticated(
                "Unable to verify access token: signing keys unavailable.",
                hint=f"Check that the auth server at {self.auth_base_url} is reachable.",
            )

        # 4. Signature (RS256 only); iss/exp/aud validated manually below for
        #    full control over the error bodies.
        try:
            claims = jwt.decode(
                token,
                key=key,
                algorithms=["RS256"],
                options={"verify_exp": False, "verify_aud": False, "verify_iss": False},
            )
        except jwt.InvalidTokenError as exc:
            await self._report_invalid(request, reason=f"signature verification failed: {exc}")
            return self._unauthenticated(
                "Invalid access token: signature verification failed.",
                hint="Obtain a fresh access token from auth.",
            )

        # 5. iss
        if claims.get("iss") != self.issuer:
            await self._report_invalid(request, reason=f"issuer mismatch: {claims.get('iss')!r}", claims=claims)
            return self._unauthenticated(
                f"Invalid access token: issuer {claims.get('iss')!r} is not trusted.",
                hint=f"Tokens must be issued by {self.issuer}.",
            )

        # 6. exp (401 with expiry time + refresh instructions)
        exp = claims.get("exp")
        if not isinstance(exp, (int, float)):
            await self._report_invalid(request, reason="missing exp claim", claims=claims)
            return self._unauthenticated(
                "Invalid access token: missing expiry (exp) claim.",
                hint="Obtain a fresh access token from auth.",
            )
        if exp <= time.time():
            expired_at = _iso_utc(exp)
            await self._report(
                reporting.build_event(
                    "token_expired_during_use",
                    client_id=self._client_id(claims),
                    user_id=claims.get("sub"),
                    scope=claims.get("scope"),
                    details={"expired_at": expired_at, "method": request.method, "path": path},
                )
            )
            body = errors.expired_token_body(expired_at, self.auth_base_url)
            return JSONResponse(
                status_code=401,
                content=body,
                headers={"WWW-Authenticate": errors.www_authenticate(body["error"]["message"])},
            )

        # 7. aud (off unless an audience was configured)
        if self.audience is not None:
            aud = claims.get("aud")
            aud_values = aud if isinstance(aud, list) else [aud]
            if self.audience not in aud_values:
                await self._report_invalid(request, reason=f"audience mismatch: {aud!r}", claims=claims)
                return self._unauthenticated(
                    f"Invalid access token: audience {aud!r} does not match {self.audience!r}.",
                    hint="Obtain a token issued for this resource server.",
                )

        # 8. Optional revocation check (AUTH_INTROSPECT=1), cached 10s
        if config.is_introspect_enabled():
            active = await self._introspect_active(token, claims.get("jti"))
            if active is False:
                await self._report_invalid(request, reason="token revoked (introspection)", claims=claims)
                return self._unauthenticated(
                    "Access token has been revoked or is no longer active.",
                    hint="Obtain a fresh access token from auth.",
                )

        # 9. Route + scope enforcement (OR logic; missing route key => auth-only)
        token_scopes = [s for s in str(claims.get("scope", "")).split() if s]
        fastapi_app = request.scope.get("app")
        route_match = match_route(fastapi_app, request.scope) if fastapi_app is not None else None
        required_scopes: list[str] = []
        if route_match is not None and self.scope_map:
            required_scopes = list(self.scope_map.get(route_match) or [])
            if required_scopes and not has_any_scope(token_scopes, required_scopes):
                await self._report(
                    reporting.build_event(
                        "scope_escalation_attempt",
                        client_id=self._client_id(claims),
                        user_id=claims.get("sub"),
                        scope=claims.get("scope"),
                        details={
                            "method": route_match[0],
                            "route": route_match[1],
                            "required_scopes": required_scopes,
                            "token_scopes": token_scopes,
                        },
                    )
                )
                return JSONResponse(
                    status_code=403,
                    content=errors.insufficient_scope_body(required_scopes, token_scopes),
                )

        # 10. Identity for the deps layer
        request.state.auth_user_id = claims.get("sub")
        # Email claim for env-local identity fallback resolution (the token's
        # sub may not exist as a local user id; deps layers may match a local
        # user by email instead). Empty string when the claim is absent.
        request.state.auth_email = str(claims.get("email") or "")
        request.state.auth_scopes = token_scopes
        request.state.auth_client_id = self._client_id(claims)
        request.state.auth_jti = claims.get("jti")
        request.state.auth_token_exp = exp

        response = await call_next(request)

        # 11. Aggregated resource_access reporting on 2xx
        if 200 <= response.status_code < 300 and config.is_report_enabled():
            method, route = route_match if route_match is not None else (request.method, path)
            scope_used = " ".join(sorted(set(token_scopes) & set(required_scopes)))
            events = self._aggregator.record(
                client_id=self._client_id(claims),
                user_id=claims.get("sub"),
                method=method,
                route=route,
                scope_used=scope_used,
                token_scope=str(claims.get("scope", "")),
            )
            for event in events:
                await reporting.report_event_async(event, self.auth_base_url)

        return response

    # ------------------------------------------------------------------ helpers

    @staticmethod
    def _client_id(claims: dict) -> str | None:
        client_id = claims.get("client_id")
        if client_id:
            return client_id
        aud = claims.get("aud")
        if isinstance(aud, list):
            return aud[0] if aud else None
        return aud

    def _unauthenticated(self, message: str, hint: str) -> JSONResponse:
        return JSONResponse(
            status_code=401,
            content=errors.unauthenticated_body(message, hint),
            headers={"WWW-Authenticate": errors.www_authenticate(message)},
        )

    async def _report(self, payload: dict) -> None:
        await reporting.report_event_async(payload, self.auth_base_url)

    async def _report_invalid(self, request: Request, reason: str, claims: dict | None = None) -> None:
        claims = claims or {}
        await self._report(
            reporting.build_event(
                "invalid_token",
                client_id=self._client_id(claims),
                user_id=claims.get("sub"),
                scope=claims.get("scope"),
                details={"reason": reason, "method": request.method, "path": request.url.path},
            )
        )

    async def _introspect_active(self, token: str, jti: str | None) -> bool | None:
        """POST /oauth2/introspect with a 10s in-process cache.

        Returns True/False for the introspection result, or None when the
        introspection endpoint is unreachable (fail open -- the token already
        passed local validation).
        """
        cache_key = jti or token
        now = time.monotonic()
        cached = self._introspect_cache.get(cache_key)
        if cached is not None and (now - cached[0]) < _INTROSPECT_CACHE_TTL:
            return cached[1]
        # Evict expired entries so the cache can't grow unbounded on long-lived
        # servers that see many distinct tokens (entries are only valid for the TTL).
        if len(self._introspect_cache) >= _INTROSPECT_CACHE_MAX:
            self._introspect_cache = {
                k: v
                for k, v in self._introspect_cache.items()
                if (now - v[0]) < _INTROSPECT_CACHE_TTL
            }
        try:
            async with httpx.AsyncClient(transport=self._introspect_transport, timeout=2.0) as client:
                resp = await client.post(
                    f"{self.auth_base_url}/oauth2/introspect", data={"token": token}
                )
                resp.raise_for_status()
                active = bool(resp.json().get("active"))
        except Exception:
            return None
        self._introspect_cache[cache_key] = (now, active)
        return active
