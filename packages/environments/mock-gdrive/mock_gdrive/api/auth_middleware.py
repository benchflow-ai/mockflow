"""Gdrive-side wrapper around Env_0AuthMiddleware: web-UI exemptions + alt=media.

Mirrors gmail's GmailEnv_0AuthMiddleware (the proven pattern):

- The human web dashboard (``/``, ``/file/{file_id}``, ``/switch-user``)
  identifies the user via the ``mock_gdrive_user`` cookie, NOT Bearer tokens --
  the real-world split between browser sessions and API credentials. With
  ``AUTH_ENABLED=1`` these routes stay reachable without a token.
- ``/mcp`` is exempt: agent MCP clients are out of OAuth scope for v1 (same
  decision as gmail).
- ``/static`` is defensive (no static mount today).
- The drive home page lives at ``/`` -- a ``"/"`` PREFIX would exempt every
  path, so the subclass short-circuits the exact path before delegating to
  the upstream ``dispatch`` (identical to gmail's inbox-at-root handling).

One gdrive-specific addition: ``GET /drive/v3/files/{fileId}`` is dual-purpose.
Plain calls return metadata (SCOPE_MAP requires a metadata-read scope), but
``?alt=media`` downloads file content. The route-level scope map cannot see
query strings, so this subclass wraps ``call_next`` and -- AFTER the base
middleware fully validated the token and populated ``request.state.auth_*`` --
additionally requires one of ``CONTENT_DOWNLOAD_SCOPES`` (drive.readonly |
drive.full), returning the exact contract 403 insufficient-scope body and
reporting a ``scope_escalation_attempt`` just like the base middleware would.

auth-client's public API is unchanged: exemptions go through the existing
``exempt_prefixes`` parameter and the media guard composes around ``dispatch``.
"""

from __future__ import annotations

from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from env_0_auth_client import Env_0AuthMiddleware, match_route, reporting
from env_0_auth_client.errors import insufficient_scope_body
from env_0_auth_client.middleware import DEFAULT_EXEMPT_PREFIXES
from env_0_auth_client.scopes import has_any_scope

from mock_gdrive.auth_scopes import CONTENT_DOWNLOAD_SCOPES, FILES_GET_ROUTE

#: Exact paths that bypass auth. Exact-match only -- "/" as a *prefix* would
#: exempt everything, which is why this set exists at all.
EXEMPT_EXACT_PATHS = frozenset({"/"})

#: Gdrive's web UI has no /web prefix, so each root-mounted route gets its own
#: precise prefix (segment-boundary matched upstream: "/file" covers "/file/x"
#: but never "/files..."). /_admin, /health, /dev, /docs, /openapi.json and
#: /web come from the contract-pinned defaults.
GDRIVE_EXEMPT_PREFIXES: tuple[str, ...] = DEFAULT_EXEMPT_PREFIXES + (
    "/file",         # GET /file/{file_id} -- web file-detail page
    "/switch-user",  # GET /switch-user    -- web cookie identity switcher
    "/static",       # static assets (none mounted today; defensive)
    "/mcp",          # MCP clients are out of OAuth scope for v1
)


class GdriveEnv_0AuthMiddleware(Env_0AuthMiddleware):
    """Env_0AuthMiddleware with gdrive's exemptions + the alt=media scope upgrade.

    Only the defaults differ; every kwarg (``scope_map``, ``jwks_static``,
    ``audience``, ...) is forwarded untouched, and callers may still override
    ``exempt_prefixes`` explicitly.
    """

    def __init__(
        self,
        app,
        exempt_prefixes: tuple[str, ...] = GDRIVE_EXEMPT_PREFIXES,
        **kwargs,
    ):
        super().__init__(app, exempt_prefixes=exempt_prefixes, **kwargs)

    def _is_media_download(self, request: Request) -> bool:
        """True for ``GET /drive/v3/files/{fileId}?alt=media`` (content download)."""
        if request.method != "GET" or request.query_params.get("alt") != "media":
            return False
        fastapi_app = request.scope.get("app")
        if fastapi_app is None:
            return False
        return match_route(fastapi_app, request.scope) == FILES_GET_ROUTE

    async def dispatch(self, request: Request, call_next) -> Response:
        if request.url.path in EXEMPT_EXACT_PATHS:
            return await call_next(request)

        if not self._is_media_download(request):
            return await super().dispatch(request, call_next)

        # alt=media: run the base middleware first (401s / route-level scope
        # checks / request.state population), then require a content-read
        # scope before the request reaches the endpoint.
        async def guarded_call_next(req: Request) -> Response:
            token_scopes = list(getattr(req.state, "auth_scopes", None) or [])
            if has_any_scope(token_scopes, CONTENT_DOWNLOAD_SCOPES):
                return await call_next(req)
            await reporting.report_event_async(
                reporting.build_event(
                    "scope_escalation_attempt",
                    client_id=getattr(req.state, "auth_client_id", None),
                    user_id=getattr(req.state, "auth_user_id", None),
                    scope=" ".join(token_scopes),
                    details={
                        "method": FILES_GET_ROUTE[0],
                        "route": FILES_GET_ROUTE[1],
                        "required_scopes": list(CONTENT_DOWNLOAD_SCOPES),
                        "token_scopes": token_scopes,
                        "alt": "media",
                    },
                ),
                self.auth_base_url,
            )
            return JSONResponse(
                status_code=403,
                content=insufficient_scope_body(
                    list(CONTENT_DOWNLOAD_SCOPES), token_scopes
                ),
            )

        return await super().dispatch(request, guarded_call_next)
