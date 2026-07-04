"""Stripe-side wrapper around Env_0AuthMiddleware: web-UI + /mcp exemptions.

Mirrors gmail's ``GmailMockAuthMiddleware`` (see API_NOTES.md
"auth integration"):

- The human web dashboard (``/`` -- customers/payments/balance) identifies the
  operator via the browser, NOT Bearer tokens -- the real-world split between
  browser sessions and API credentials. With ``AUTH_ENABLED=1`` the root
  page stays reachable without a token.
- ``/mcp`` is exempt: agent MCP clients are out of OAuth scope for v1.
- ``/static`` serves assets for the web UI; ``/_admin``, ``/health``, ``/dev``,
  ``/web``, ``/docs`` and ``/openapi.json`` come from the contract-pinned
  defaults.

auth-client's public API is unchanged: the extra exemptions are plain
prefix additions passed through the existing ``exempt_prefixes`` parameter
(segment-boundary matching, so ``/web`` does NOT exempt ``/webhook_endpoints``).
The one thing prefixes cannot express is the dashboard at ``/`` (a ``"/"``
PREFIX would exempt every path), so this subclass short-circuits the EXACT path
``/`` before delegating to the upstream ``dispatch``.

Token coexistence note: legacy ``sk_test_`` keys are NOT JWTs (no three-dot
header.payload.signature structure), so when auth is enabled the upstream
middleware rejects them with the contract 401 body. A bare ``sk_test_`` key is
insufficient under auth (like slack's xoxb-); it keeps working only when
AUTH_ENABLED is unset. See ``mock_stripe/api/deps.py``.
"""

from __future__ import annotations

from starlette.requests import Request
from starlette.responses import Response

from env_0_auth_client import Env_0AuthMiddleware
from env_0_auth_client.middleware import DEFAULT_EXEMPT_PREFIXES

#: Exact paths that bypass auth. Exact-match only -- "/" as a *prefix* would
#: exempt everything, which is why this set exists at all.
EXEMPT_EXACT_PATHS = frozenset({"/"})

#: Stripe's web dashboard mounts at the root, so it gets the exact-match "/"
#: above; everything else is contract defaults plus /static and /mcp. Prefix
#: matching is segment-boundary ("/web" matches "/web/x", never
#: "/webhook_endpoints").
STRIPE_EXEMPT_PREFIXES: tuple[str, ...] = DEFAULT_EXEMPT_PREFIXES + (
    "/static",  # static assets for the web UI (defensive; none mounted today)
    "/mcp",     # MCP clients are out of OAuth scope for v1
    "/redoc",   # FastAPI's ReDoc page (/docs and /openapi.json are defaults)
)


class StripeMockAuthMiddleware(Env_0AuthMiddleware):
    """Env_0AuthMiddleware with stripe's exemptions baked in as defaults.

    Only the defaults differ; every kwarg (``scope_map``, ``jwks_static``,
    ``audience``, ...) is forwarded untouched, and callers may still override
    ``exempt_prefixes`` explicitly.
    """

    def __init__(
        self,
        app,
        exempt_prefixes: tuple[str, ...] = STRIPE_EXEMPT_PREFIXES,
        **kwargs,
    ):
        super().__init__(app, exempt_prefixes=exempt_prefixes, **kwargs)

    async def dispatch(self, request: Request, call_next) -> Response:
        if request.url.path in EXEMPT_EXACT_PATHS:
            return await call_next(request)
        return await super().dispatch(request, call_next)
