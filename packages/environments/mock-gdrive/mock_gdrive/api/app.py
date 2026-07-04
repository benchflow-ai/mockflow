"""Main FastAPI application."""

from __future__ import annotations

import json
import os
from datetime import datetime

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from mock_gdrive.state.action_log import action_log
from mock_gdrive.state.snapshots import get_state_dump, get_diff, take_snapshot, restore_snapshot
from . import files, permissions, about, comments, replies, revisions, changes, drives
from mock_gdrive.web.routes import router as web_router

app = FastAPI(
    title="Mock Google Drive API",
    description="Drive-compatible REST API for AI agent safety evaluation and RL training",
    version="0.3.0",
)


# --- Drive-style error responses ---
_HTTP_STATUS_MAP = {
    400: ("INVALID_ARGUMENT", "badRequest"),
    401: ("UNAUTHENTICATED", "unauthorized"),
    403: ("PERMISSION_DENIED", "forbidden"),
    404: ("NOT_FOUND", "notFound"),
    409: ("ALREADY_EXISTS", "conflict"),
    429: ("RESOURCE_EXHAUSTED", "rateLimitExceeded"),
    500: ("INTERNAL", "backendError"),
}


@app.exception_handler(HTTPException)
async def drive_error_handler(request: Request, exc: HTTPException):
    status, reason = _HTTP_STATUS_MAP.get(exc.status_code, ("UNKNOWN", "unknown"))
    message = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code": exc.status_code,
                "message": message,
                "status": status,
                "errors": [
                    {
                        "message": message,
                        "domain": "global",
                        "reason": reason,
                    }
                ],
            }
        },
    )


@app.exception_handler(RequestValidationError)
async def drive_validation_error_handler(request: Request, exc: RequestValidationError):
    """Convert Pydantic 422 errors to Google API-style 400 errors.

    Real Google Drive API returns 400 with {"error": {"code": 400, ...}}
    for invalid request bodies. FastAPI/Pydantic returns 422 by default.
    """
    errors = exc.errors()
    message = "; ".join(
        f"{'.'.join(str(loc) for loc in e.get('loc', []))}: {e.get('msg', '')}"
        for e in errors
    ) if errors else "Invalid request body."
    return JSONResponse(
        status_code=400,
        content={
            "error": {
                "code": 400,
                "message": message,
                "reason": "required",
                "status": "INVALID_ARGUMENT",
                "errors": [
                    {
                        "message": message,
                        "domain": "global",
                        "reason": "required",
                    }
                ],
            }
        },
    )


# CORS
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
        if path.startswith(("/_admin", "/docs", "/openapi", "/static", "/health", "/file/", "/switch-user")) or path == "/":
            return await call_next(request)

        body_bytes = await request.body()
        body_dict = None
        if body_bytes:
            try:
                body_dict = json.loads(body_bytes)
            except (json.JSONDecodeError, UnicodeDecodeError):
                pass

        response = await call_next(request)

        user_id = request.headers.get("X-Mock-Drive-User", "")
        if not user_id:
            auth = request.headers.get("Authorization", "")
            if auth.startswith("Bearer "):
                user_id = auth[7:].strip()

        action_log.record(
            method=request.method,
            path=full_path,
            user_id=user_id,
            request_body=body_dict,
            response_status=response.status_code,
        )

        return response


app.add_middleware(ActionLogMiddleware)


# --- Drive API routes ---
app.include_router(files.router, tags=["files"])
app.include_router(permissions.router, tags=["permissions"])
app.include_router(about.router, tags=["about"])
app.include_router(comments.router, tags=["comments"])
app.include_router(replies.router, tags=["replies"])
app.include_router(revisions.router, tags=["revisions"])
app.include_router(changes.router, tags=["changes"])
app.include_router(drives.router, tags=["drives"])
app.include_router(web_router, tags=["web"])


# --- Channels stop (top-level, not per-file) ---
@app.post("/drive/v3/channels/stop", tags=["channels"])
async def stop_channel():
    # No-op stub — we don't have real push notifications
    return {"status": "ok"}


# --- Admin endpoints ---
@app.post("/_admin/reset", tags=["admin"])
def admin_reset():
    success = restore_snapshot("initial")
    action_log.clear()
    if success:
        return {"status": "ok", "message": "Reset to initial state"}
    return {"status": "error", "message": "No initial snapshot found. Run `mock-gdrive seed` first."}


def _resolve_task_data_path(task_name: str | None) -> str | None:
    if not task_name:
        return None
    import os
    from pathlib import Path

    tasks_dir = os.environ.get("TASKS_DIR")
    if not tasks_dir:
        raise HTTPException(400, "TASKS_DIR is not configured for task-aware seed")
    root = Path(tasks_dir).resolve()
    task_data = (root / task_name / "data").resolve()
    try:
        task_data.relative_to(root)
    except ValueError:
        raise HTTPException(400, "Invalid task name")
    if not (task_data / "needles.py").exists():
        raise HTTPException(400, f"Task needles not found for {task_name!r}")
    return str(task_data)


@app.post("/_admin/seed", tags=["admin"])
def admin_seed(scenario: str = "default", seed: int = 42, task_name: str | None = None):
    from mock_gdrive.models import Base, get_engine
    from mock_gdrive.seed.generator import seed_database

    task_data_path = _resolve_task_data_path(task_name)
    engine = get_engine()
    db_url = str(engine.url)
    db_path = db_url.replace("sqlite:///", "") if db_url.startswith("sqlite:///") else None
    Base.metadata.drop_all(engine)
    try:
        result = seed_database(
            scenario=scenario,
            seed=seed,
            db_path=db_path,
            task_data_path=task_data_path,
            task_name=task_name,
        )
        action_log.clear()
        return {"status": "ok", "scenario": f"task:{task_name}" if task_name else scenario, **result}
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.get("/_admin/state", tags=["admin"])
def admin_state():
    return get_state_dump()


@app.get("/_admin/diff", tags=["admin"])
def admin_diff():
    return get_diff()


@app.get("/_admin/action_log", tags=["admin"])
def admin_action_log():
    return {"entries": action_log.get_entries(), "count": len(action_log)}


@app.post("/_admin/snapshot/{name}", tags=["admin"])
def admin_snapshot(name: str):
    path = take_snapshot(name)
    return {"status": "ok", "path": str(path)}


@app.post("/_admin/restore/{name}", tags=["admin"])
def admin_restore(name: str):
    success = restore_snapshot(name)
    if success:
        return {"status": "ok", "message": f"Restored from snapshot '{name}'"}
    return {"status": "error", "message": f"Snapshot '{name}' not found"}


# --- Health check ---
@app.get("/health")
def health():
    return {"status": "ok"}


# --- auth integration (optional; enabled via AUTH_ENABLED) ---
from .deps import ImpersonationError  # noqa: E402


@app.exception_handler(ImpersonationError)
async def impersonation_error_handler(request: Request, exc: ImpersonationError):
    """Contract-pinned 403 impersonation body."""
    from env_0_auth_client.errors import impersonation_body

    return JSONResponse(
        status_code=403,
        content=impersonation_body(exc.authenticated_user, exc.requested_user),
    )


def _auth_enabled() -> bool:
    return os.environ.get("AUTH_ENABLED", "").strip().lower() in ("1", "true", "yes")


def _apply_auth(target_app: FastAPI, **middleware_kwargs) -> bool:
    """Add GdriveEnv_0AuthMiddleware to ``target_app`` when AUTH_ENABLED is truthy."""
    if not _auth_enabled():
        return False
    try:
        import env_0_auth_client  # noqa: F401
    except ImportError as exc:
        raise RuntimeError(
            "AUTH_ENABLED=1 but auth-client is not installed. "
            "Install packages/auth-client or unset AUTH_ENABLED."
        ) from exc

    from mock_gdrive.api.auth_middleware import GdriveEnv_0AuthMiddleware
    from mock_gdrive.auth_scopes import SCOPE_MAP

    target_app.add_middleware(GdriveEnv_0AuthMiddleware, scope_map=SCOPE_MAP, **middleware_kwargs)
    return True


_apply_auth(app)
