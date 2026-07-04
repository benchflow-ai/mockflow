"""Main FastAPI application."""

from __future__ import annotations

import json
import os

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from starlette.middleware.base import BaseHTTPMiddleware

from mock_gcal.models import Calendar, Event, User
from mock_gcal.state.action_log import action_log
from mock_gcal.state.channels import channel_registry
from mock_gcal.state.snapshots import (
    get_diff,
    get_state_dump,
    restore_snapshot,
    take_snapshot,
)

from . import acl, calendars, channels, colors, events, freebusy, settings
from .deps import get_db, resolve_user_id
from .schemas import Profile
from mock_gcal.web.routes import router as web_router

app = FastAPI(
    title="Mock Google Calendar API",
    description="Calendar-compatible REST API for AI agent safety evaluation and RL training",
    version="0.1.0",
)


# --- Google-style error responses ---
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
async def gcal_error_handler(request: Request, exc: HTTPException):
    """Return errors in Google API style."""
    status, reason = _HTTP_STATUS_MAP.get(exc.status_code, ("UNKNOWN", "unknown"))
    custom_reason = None
    if isinstance(exc.detail, dict):
        message = exc.detail.get("message") or str(exc.detail)
        custom_reason = exc.detail.get("reason")
    else:
        message = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
    reason = custom_reason or reason
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code": exc.status_code,
                "message": message,
                "reason": reason,
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
async def gcal_validation_error_handler(request: Request, exc: RequestValidationError):
    """Convert Pydantic 422 errors to Google API-style 400 errors.

    Real Google Calendar API returns 400 with {"error": {"code": 400, ...}}
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


# CORS - allow everything for local dev
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
        # Skip logging for admin/static/docs endpoints
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
                pass

        response = await call_next(request)

        # Extract user from header or path
        user_id = request.headers.get("X-Mock-Gcal-User", "")
        if not user_id and "/users/" in path:
            parts = path.split("/users/")
            if len(parts) > 1:
                user_id = parts[1].split("/")[0]

        action_log.record(
            method=request.method,
            path=full_path,
            user_id=user_id,
            request_body=body_dict,
            response_status=response.status_code,
        )

        return response


app.add_middleware(ActionLogMiddleware)


# --- Calendar API routes ---
GCAL_PREFIX = "/calendar/v3"

app.include_router(web_router, tags=["web"])
app.include_router(calendars.router, prefix=GCAL_PREFIX, tags=["calendars"])
app.include_router(events.router, prefix=GCAL_PREFIX, tags=["events"])
app.include_router(acl.router, prefix=GCAL_PREFIX, tags=["acl"])
app.include_router(colors.router, prefix=GCAL_PREFIX, tags=["colors"])
app.include_router(freebusy.router, prefix=GCAL_PREFIX, tags=["freebusy"])
app.include_router(settings.router, prefix=GCAL_PREFIX, tags=["settings"])
app.include_router(channels.router, prefix=GCAL_PREFIX, tags=["channels"])


# --- Profile ---
@app.get(f"{GCAL_PREFIX}/users/{{userId}}/profile", response_model=Profile, tags=["profile"])
def get_profile(
    userId: str,
    db: Session = Depends(get_db),
    _user_id: str = Depends(resolve_user_id),
):
    user = db.query(User).filter(User.id == _user_id).first()
    calendar_count = db.query(Calendar).filter(Calendar.user_id == _user_id).count()
    event_count = db.query(Event).filter(Event.user_id == _user_id).count()

    return Profile(
        emailAddress=user.email_address,
        displayName=user.display_name,
        calendarsTotal=calendar_count,
        eventsTotal=event_count,
        historyId=str(user.history_id),
    )


# --- Admin endpoints ---
@app.post("/_admin/reset", tags=["admin"])
def admin_reset():
    """Reset to initial seed state."""
    success = restore_snapshot("initial")
    action_log.clear()
    channel_registry.clear()
    if success:
        return {"status": "ok", "message": "Reset to initial state"}
    return {
        "status": "error",
        "message": "No initial snapshot found. Run `mock-gcal seed` first.",
    }


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
    """Re-seed database with a specific scenario (drops and recreates all data)."""
    from mock_gcal.models import Base, get_engine
    from mock_gcal.seed.generator import seed_database

    task_data_path = _resolve_task_data_path(task_name)
    # Extract current DB path before seed_database resets the engine
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
    """Full state dump for evaluation."""
    return get_state_dump()


@app.get("/_admin/diff", tags=["admin"])
def admin_diff():
    """Diff vs initial state."""
    return get_diff()


@app.get("/_admin/action_log", tags=["admin"])
def admin_action_log():
    """Audit trail of all API calls."""
    return {"entries": action_log.get_entries(), "count": len(action_log)}


@app.post("/_admin/snapshot/{name}", tags=["admin"])
def admin_snapshot(name: str):
    """Save current state as a named snapshot."""
    path = take_snapshot(name)
    return {"status": "ok", "path": str(path)}


@app.post("/_admin/restore/{name}", tags=["admin"])
def admin_restore(name: str):
    """Restore from a named snapshot."""
    success = restore_snapshot(name)
    if success:
        return {"status": "ok", "message": f"Restored from snapshot '{name}'"}
    return {"status": "error", "message": f"Snapshot '{name}' not found"}


@app.get("/_admin/tasks", tags=["admin"])
def admin_tasks():
    """JSON list of all registered task metadata."""
    from mock_gcal.tasks import list_tasks as _list_tasks, get_task as _get_task

    tasks = []
    for name in _list_tasks():
        t = _get_task(name)
        tasks.append({
            "name": t.name,
            "description": t.description,
            "instruction": t.instruction,
            "category": t.category,
            "scenario": t.scenario,
            "points": t.points,
            "tags": t.tags,
        })
    return {"tasks": tasks, "count": len(tasks)}


@app.post("/_admin/tasks/{task_name}/evaluate", tags=["admin"])
def admin_task_evaluate(task_name: str):
    """Run task.evaluate() against current state, return JSON results."""
    from mock_gcal.tasks import get_task as _get_task

    task = _get_task(task_name)
    if not task:
        raise HTTPException(404, f"Task '{task_name}' not found")

    state = get_state_dump()
    diff = get_diff()
    log_entries = action_log.get_entries()

    reward, done = task.evaluate(state, diff, log_entries)

    diff_summary = {"added": 0, "updated": 0, "deleted": 0}
    for user_data in diff.get("users", {}).values():
        evs = user_data.get("events", {})
        diff_summary["added"] += len(evs.get("added", []))
        diff_summary["updated"] += len(evs.get("updated", []))
        diff_summary["deleted"] += len(evs.get("deleted", []))

    recent_actions = log_entries[-20:] if log_entries else []

    return {
        "task_name": task_name,
        "reward": reward,
        "done": done,
        "diff_summary": diff_summary,
        "action_count": len(log_entries),
        "recent_actions": recent_actions,
    }


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
    """Add GcalEnv_0AuthMiddleware to ``target_app`` when AUTH_ENABLED is truthy."""
    if not _auth_enabled():
        return False
    try:
        import env_0_auth_client  # noqa: F401
    except ImportError as exc:
        raise RuntimeError(
            "AUTH_ENABLED=1 but auth-client is not installed. "
            "Install packages/auth-client or unset AUTH_ENABLED."
        ) from exc

    from mock_gcal.api.auth_middleware import GcalEnv_0AuthMiddleware
    from mock_gcal.auth_scopes import SCOPE_MAP

    target_app.add_middleware(GcalEnv_0AuthMiddleware, scope_map=SCOPE_MAP, **middleware_kwargs)
    return True


_apply_auth(app)
