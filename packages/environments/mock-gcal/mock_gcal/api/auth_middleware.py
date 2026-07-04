"""Gcal-side wrapper around Env_0AuthMiddleware: web-UI + /mcp exemptions.

Decision (v1, mirroring gmail -- see its API_NOTES.md "auth
integration" section):

- The human web dashboard (``/`` and ``/dev/*``) identifies the user via the
  ``mock_gcal_user`` cookie, NOT Bearer tokens -- the real-world split between
  browser sessions and API credentials. With ``AUTH_ENABLED=1`` these
  routes stay reachable without a token. ``/dev`` is already in the
  contract-pinned default exempt prefixes.
- ``/mcp`` is exempt: agent MCP clients are out of OAuth scope for v1.

auth-client's public API is unchanged: the extra exemptions are plain
prefix additions passed through the existing ``exempt_prefixes`` parameter.
The one thing prefixes cannot express is the calendar view at ``/`` (gcal's
web UI mounts at the root; a ``"/"`` PREFIX would exempt every path), so this
subclass short-circuits the exact path ``/`` before delegating to the
upstream ``dispatch``.
"""

from __future__ import annotations

from starlette.requests import Request
from starlette.responses import Response

from env_0_auth_client import Env_0AuthMiddleware
from env_0_auth_client.middleware import DEFAULT_EXEMPT_PREFIXES

#: Exact paths that bypass auth. Exact-match only -- "/" as a *prefix* would
#: exempt everything, which is why this set exists at all.
EXEMPT_EXACT_PATHS = frozenset({"/"})

#: /_admin, /health, /dev, /docs, /openapi.json and /web come from the
#: contract-pinned defaults; gcal's whole web UI lives at "/" and "/dev/*".
GCAL_EXEMPT_PREFIXES: tuple[str, ...] = DEFAULT_EXEMPT_PREFIXES + (
    "/static",  # static assets (none mounted today; defensive)
    "/mcp",     # MCP clients are out of OAuth scope for v1
)


class GcalEnv_0AuthMiddleware(Env_0AuthMiddleware):
    """Env_0AuthMiddleware with gcal's exemptions baked in as defaults.

    Only the defaults differ; every kwarg (``scope_map``, ``jwks_static``,
    ``audience``, ...) is forwarded untouched, and callers may still override
    ``exempt_prefixes`` explicitly.
    """

    def __init__(
        self,
        app,
        exempt_prefixes: tuple[str, ...] = GCAL_EXEMPT_PREFIXES,
        **kwargs,
    ):
        super().__init__(app, exempt_prefixes=exempt_prefixes, **kwargs)

    async def dispatch(self, request: Request, call_next) -> Response:
        if request.url.path in EXEMPT_EXACT_PATHS:
            return await call_next(request)
        return await super().dispatch(request, call_next)
