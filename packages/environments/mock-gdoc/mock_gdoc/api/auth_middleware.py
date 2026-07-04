"""Gdoc-side wrapper around Env_0AuthMiddleware: web-UI + /mcp exemptions.

Decision (v1, mirrors gmail; see API_NOTES.md "auth integration"):

- The human web dashboard (``/``, ``/doc/{id}``, ``/doc/{id}/save``,
  ``/dev/*``) is a browser UI with no per-user identity (it renders all
  documents); it stays reachable WITHOUT a Bearer token when
  ``AUTH_ENABLED=1`` -- mirroring the real-world split between browser
  sessions and API credentials.
- ``/mcp`` is exempt: agent MCP clients are out of OAuth scope for v1.

auth-client's public API is unchanged: the extra exemptions are plain
prefix additions passed through the existing ``exempt_prefixes`` parameter.
The one thing prefixes cannot express is the document list at ``/`` (gdoc's
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

#: Gdoc's web UI has no /web prefix, so each root-mounted route gets its own
#: precise prefix. /_admin, /health, /dev, /docs, /openapi.json and /web come
#: from the contract-pinned defaults. Prefix matching is segment-boundary
#: aware upstream, so "/doc" exempts /doc/{id} but NOT /docs (already exempt)
#: and never /v1/documents.
GDOC_EXEMPT_PREFIXES: tuple[str, ...] = DEFAULT_EXEMPT_PREFIXES + (
    "/doc",     # GET /doc/{document_id}, POST /doc/{document_id}/save (web editor)
    "/static",  # static assets (none mounted today; defensive)
    "/mcp",     # MCP clients are out of OAuth scope for v1
)


class GdocEnv_0AuthMiddleware(Env_0AuthMiddleware):
    """Env_0AuthMiddleware with gdoc's exemptions baked in as defaults.

    Only the defaults differ; every kwarg (``scope_map``, ``jwks_static``,
    ``audience``, ...) is forwarded untouched, and callers may still override
    ``exempt_prefixes`` explicitly.
    """

    def __init__(
        self,
        app,
        exempt_prefixes: tuple[str, ...] = GDOC_EXEMPT_PREFIXES,
        **kwargs,
    ):
        super().__init__(app, exempt_prefixes=exempt_prefixes, **kwargs)

    async def dispatch(self, request: Request, call_next) -> Response:
        if request.url.path in EXEMPT_EXACT_PATHS:
            return await call_next(request)
        return await super().dispatch(request, call_next)
