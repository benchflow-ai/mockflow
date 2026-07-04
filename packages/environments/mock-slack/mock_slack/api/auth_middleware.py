"""Slack-side wrapper around Env_0AuthMiddleware: web-UI + /mcp exemptions.

Mirrors gmail's ``GmailEnv_0AuthMiddleware`` (see API_NOTES.md
"auth integration"):

- The human web UI (``/``, ``/channel/*``, ``/dms``, ``/activity``, ...)
  identifies the user via browser sessions, NOT Bearer tokens -- the
  real-world split between browser sessions and API credentials. With
  ``AUTH_ENABLED=1`` these routes stay reachable without a token.
- ``/mcp`` is exempt: agent MCP clients are out of OAuth scope for v1.
- ``/static`` serves assets for the web UI; ``/redoc`` is FastAPI's second
  docs page (the contract defaults already cover ``/docs`` and
  ``/openapi.json``).

auth-client's public API is unchanged: the extra exemptions are plain
prefix additions passed through the existing ``exempt_prefixes`` parameter
(which uses segment-boundary matching, so ``/app`` does NOT exempt ``/api``).
The one thing prefixes cannot express is the workspace home at ``/`` (slack's
web UI mounts at the root; a ``"/"`` PREFIX would exempt every path), so this
subclass short-circuits the exact path ``/`` before delegating to the
upstream ``dispatch``.

Token coexistence note: legacy ``xoxb-``/``xoxp-`` tokens are NOT JWTs (no
three-dot header.payload.signature structure), so when auth is enabled the
upstream middleware rejects them with the contract 401 "malformed token"
body. They keep working only when AUTH_ENABLED is unset.
"""

from __future__ import annotations

from starlette.requests import Request
from starlette.responses import Response

from env_0_auth_client import Env_0AuthMiddleware
from env_0_auth_client.middleware import DEFAULT_EXEMPT_PREFIXES

#: Exact paths that bypass auth. Exact-match only -- "/" as a *prefix* would
#: exempt everything, which is why this set exists at all.
EXEMPT_EXACT_PATHS = frozenset({"/"})

#: Slack's web UI has no /web prefix, so each root-mounted page gets its own
#: precise prefix (see mock_slack/web/routes.py). /_admin, /health, /dev,
#: /docs, /openapi.json and /web come from the contract-pinned defaults.
#: NOTE: prefix matching is segment-boundary ("/app" matches "/app/x", never
#: "/api/..."), and "/new" does not cover "/new-dm" -- hence both entries.
SLACK_EXEMPT_PREFIXES: tuple[str, ...] = DEFAULT_EXEMPT_PREFIXES + (
    "/static",       # static assets for the web UI
    "/mcp",          # MCP clients are out of OAuth scope for v1
    "/redoc",        # FastAPI's ReDoc page (docs/openapi.json are defaults)
    "/dms",          # GET  /dms
    "/activity",     # GET  /activity
    "/files",        # GET  /files, POST /files/delete (web UI; API is /api/files.*)
    "/later",        # GET  /later
    "/more",         # GET  /more
    "/search",       # GET  /search (web UI; API is /api/search.messages)
    "/tools",        # GET  /tools
    "/channel",      # GET/POST /channel/{channel_id}/...
    "/user",         # GET  /user/{user_id}/profile/panel
    "/drafts",       # GET  /drafts
    "/directories",  # GET  /directories
    "/app",          # GET  /app/{app_id}  (segment-boundary: not /api!)
    "/new",          # GET/POST /new, /new/inline
    "/new-dm",       # GET  /new-dm/{user_id}
    "/threads",      # GET  /threads
)


class SlackEnv_0AuthMiddleware(Env_0AuthMiddleware):
    """Env_0AuthMiddleware with slack's exemptions baked in as defaults.

    Only the defaults differ; every kwarg (``scope_map``, ``jwks_static``,
    ``audience``, ...) is forwarded untouched, and callers may still override
    ``exempt_prefixes`` explicitly.
    """

    def __init__(
        self,
        app,
        exempt_prefixes: tuple[str, ...] = SLACK_EXEMPT_PREFIXES,
        **kwargs,
    ):
        super().__init__(app, exempt_prefixes=exempt_prefixes, **kwargs)

    async def dispatch(self, request: Request, call_next) -> Response:
        if request.url.path in EXEMPT_EXACT_PATHS:
            return await call_next(request)
        return await super().dispatch(request, call_next)
