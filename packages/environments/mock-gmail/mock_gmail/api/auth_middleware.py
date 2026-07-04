"""Gmail-side wrapper around Env_0AuthMiddleware: web-UI + /mcp exemptions.

Decision (v1, see API_NOTES.md "auth integration"):

- The human web dashboard (``/``, ``/thread/*``, ``/compose``, ``/star/*``,
  ``/trash/*``, ``/mark-read/*``, ``/static``, ``/dev/*``) identifies the user
  via the ``mock_gmail_user`` cookie, NOT Bearer tokens -- mirroring the
  real-world split between browser sessions and API credentials. With
  ``AUTH_ENABLED=1`` these routes stay reachable without a token.
- ``/mcp`` is exempt: agent MCP clients are out of OAuth scope for v1.

auth-client's public API is unchanged: the extra exemptions are plain
prefix additions passed through the existing ``exempt_prefixes`` parameter.
The one thing prefixes cannot express is the inbox at ``/`` (gmail's web UI
mounts at the root; a ``"/"`` PREFIX would exempt every path), so this
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

#: Gmail's web UI has no /web prefix, so each root-mounted route gets its own
#: precise prefix. /_admin, /health, /dev, /docs, /openapi.json and /web come
#: from the contract-pinned defaults.
GMAIL_EXEMPT_PREFIXES: tuple[str, ...] = DEFAULT_EXEMPT_PREFIXES + (
    "/thread",     # GET  /thread/{thread_id}
    "/compose",    # POST /compose
    "/star",       # POST /star/{message_id}
    "/trash",      # POST /trash/{message_id}
    "/mark-read",  # POST /mark-read/{message_id}
    "/static",     # static assets (none mounted today; defensive)
    "/mcp",        # MCP clients are out of OAuth scope for v1
)


class GmailMockAuthMiddleware(Env_0AuthMiddleware):
    """Env_0AuthMiddleware with gmail's exemptions baked in as defaults.

    Only the defaults differ; every kwarg (``scope_map``, ``jwks_static``,
    ``audience``, ...) is forwarded untouched, and callers may still override
    ``exempt_prefixes`` explicitly.
    """

    def __init__(
        self,
        app,
        exempt_prefixes: tuple[str, ...] = GMAIL_EXEMPT_PREFIXES,
        **kwargs,
    ):
        super().__init__(app, exempt_prefixes=exempt_prefixes, **kwargs)

    async def dispatch(self, request: Request, call_next) -> Response:
        if request.url.path in EXEMPT_EXACT_PATHS:
            return await call_next(request)
        return await super().dispatch(request, call_next)
