"""Main FastAPI application for auth."""

from __future__ import annotations

import json

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from mock_auth.api.errors import BearerError, OAuthError
from mock_auth.state.action_log import action_log

app = FastAPI(
    title="Mock Google OAuth2/OIDC (auth)",
    description="OAuth2/OIDC-compatible mock authorization server for AI agent "
                "safety evaluation and RL training",
    version="0.1.0",
)


# --- RFC 6749 errors for OAuth protocol endpoints (never re-wrapped) ---
@app.exception_handler(OAuthError)
async def oauth_error_handler(request: Request, exc: OAuthError):
    return JSONResponse(status_code=exc.status_code, content=exc.body(),
                        headers=exc.headers or None)


# --- Resource-server style errors (userinfo) ---
@app.exception_handler(BearerError)
async def bearer_error_handler(request: Request, exc: BearerError):
    headers = {}
    if exc.www_authenticate:
        headers["WWW-Authenticate"] = exc.www_authenticate
    return JSONResponse(status_code=exc.status_code, content=exc.body(),
                        headers=headers or None)


# --- Generic Google-style envelope for everything else (admin, web) ---
_HTTP_STATUS_MAP = {
    400: ("INVALID_ARGUMENT", "badRequest"),
    401: ("UNAUTHENTICATED", "unauthorized"),
    403: ("PERMISSION_DENIED", "forbidden"),
    404: ("NOT_FOUND", "notFound"),
    409: ("ALREADY_EXISTS", "conflict"),
    429: ("RESOURCE_EXHAUSTED", "rateLimitExceeded"),
    500: ("INTERNAL", "backendError"),
}

_OAUTH_PATH_PREFIXES = ("/oauth2", "/o/oauth2")


@app.exception_handler(HTTPException)
async def generic_error_handler(request: Request, exc: HTTPException):
    status, reason = _HTTP_STATUS_MAP.get(exc.status_code, ("UNKNOWN", "unknown"))
    message = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code": exc.status_code,
                "message": message,
                "status": status,
                "errors": [{"message": message, "domain": "global", "reason": reason}],
            }
        },
    )


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError):
    """OAuth endpoints get RFC 6749 invalid_request; others get the Google envelope."""
    errors = exc.errors()
    message = "; ".join(
        f"{'.'.join(str(loc) for loc in e.get('loc', []))}: {e.get('msg', '')}"
        for e in errors
    ) if errors else "Invalid request."
    path = str(request.url.path)
    if path.startswith(_OAUTH_PATH_PREFIXES):
        return JSONResponse(
            status_code=400,
            content={"error": "invalid_request", "error_description": message,
                     "hint": "Check required parameters; OAuth endpoints accept "
                             "form-encoded bodies."},
        )
    return JSONResponse(
        status_code=400,
        content={
            "error": {
                "code": 400,
                "message": message,
                "reason": "required",
                "status": "INVALID_ARGUMENT",
                "errors": [{"message": message, "domain": "global", "reason": "required"}],
            }
        },
    )


# CORS — allow everything for local dev
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- Action logging middleware ---
class ActionLogMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = str(request.url.path)
        query = str(request.url.query)
        full_path = f"{path}?{query}" if query else path
        if path.startswith(("/_admin", "/docs", "/openapi", "/static", "/mcp")):
            return await call_next(request)

        body_bytes = await request.body()
        body_dict = None
        if body_bytes:
            try:
                body_dict = json.loads(body_bytes)
            except (json.JSONDecodeError, UnicodeDecodeError):
                # form-encoded bodies: record raw fields, redacting secrets
                try:
                    from urllib.parse import parse_qs
                    parsed = parse_qs(body_bytes.decode("utf-8"))
                    body_dict = {k: (v[0] if len(v) == 1 else v) for k, v in parsed.items()}
                    for sensitive in ("client_secret", "password", "code_verifier"):
                        if sensitive in body_dict:
                            body_dict[sensitive] = "[redacted]"
                except (UnicodeDecodeError, ValueError):
                    pass

        response = await call_next(request)

        from mock_auth.web.sessions import SESSION_COOKIE, get_session_user_id
        user_id = get_session_user_id(request.cookies.get(SESSION_COOKIE)) or ""

        action_log.record(
            method=request.method,
            path=full_path,
            user_id=user_id,
            request_body=body_dict,
            response_status=response.status_code,
        )
        return response


app.add_middleware(ActionLogMiddleware)


# --- Routers ---
from mock_auth.api import (  # noqa: E402
    admin,
    authorize,
    device,
    discovery,
    introspect,
    myaccount,
    revoke,
    token,
    userinfo,
)
from mock_auth.web.routes import router as web_router  # noqa: E402

app.include_router(web_router, tags=["web"])
app.include_router(discovery.router, tags=["discovery"])
app.include_router(authorize.router, tags=["authorize"])
app.include_router(token.router, tags=["token"])
app.include_router(introspect.router, tags=["introspect"])
app.include_router(revoke.router, tags=["revoke"])
app.include_router(userinfo.router, tags=["userinfo"])
app.include_router(myaccount.router)
app.include_router(device.router, tags=["device"])
app.include_router(admin.router)


# --- Health check ---
@app.get("/health")
def health():
    return {"status": "ok"}
