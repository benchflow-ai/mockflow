"""Main FastAPI application."""

from __future__ import annotations

import json
from datetime import datetime

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
import os
from pathlib import Path

from mock_slack.state.action_log import action_log
from mock_slack.state.snapshots import (
    get_state_dump,
    get_diff,
    take_snapshot,
    restore_snapshot,
)
from mock_slack.web.routes import router as web_router
from . import (
    conversations,
    messages,
    users,
    reactions,
    search,
    files,
    pins,
    team,
    auth,
    reminders,
)

app = FastAPI(
    title="Mock Slack API",
    description="Slack-compatible REST API for AI agent safety evaluation and RL training",
    version="0.1.0",
)

# Mount static files
static_dir = Path(__file__).resolve().parent.parent / "web" / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


# --- Slack-style error responses ---
@app.exception_handler(HTTPException)
async def slack_error_handler(request: Request, exc: HTTPException):
    """Return errors in Slack API format: {"ok": false, "error": "..."}."""
    # Map HTTP status to Slack error codes
    status_map = {
        400: "invalid_arguments",
        401: "not_authed",
        403: "access_denied",
        404: "not_found",
        409: "conflict",
        429: "ratelimited",
        500: "fatal_error",
    }
    error_code = status_map.get(exc.status_code, "unknown_error")
    message = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
    return JSONResponse(
        status_code=exc.status_code,
        content={"ok": False, "error": error_code, "detail": message},
    )


@app.exception_handler(RequestValidationError)
async def slack_validation_error_handler(request: Request, exc: RequestValidationError):
    """Convert FastAPI/Pydantic 422 errors to Slack-style 200 with ok=false.

    Real Slack returns HTTP 200 for virtually all errors, including bad
    arguments.  FastAPI's default 422 breaks that convention and confuses
    Slack client libraries that never expect non-2xx status codes.
    """
    return JSONResponse(
        status_code=200,
        content={"ok": False, "error": "invalid_arguments", "detail": exc.errors()},
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
        # Skip logging for admin/static/docs/mcp endpoints
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

        # Extract workspace from header
        workspace_id = request.headers.get("X-Mock-Slack-Workspace", "")

        # Derive token type from Authorization header
        auth = request.headers.get("Authorization", "")
        token = auth.removeprefix("Bearer ").strip()
        if token in {"mock-user-token", "mock-user"} or token.startswith("xoxp-"):
            token_type = "user"
        elif token in {"mock-bot-token", "mock-bot"} or token.startswith("xoxb-"):
            token_type = "bot"
        else:
            token_type = ""

        action_log.record(
            method=request.method,
            path=full_path,
            user_id=workspace_id,
            request_body=body_dict,
            response_status=response.status_code,
            token_type=token_type,
        )

        return response


app.add_middleware(ActionLogMiddleware)


@app.on_event("startup")
async def migrate_db():
    """Add any missing columns and migrate old data formats."""
    import json as _json
    from mock_slack.models import get_engine, get_session_factory, Message
    import sqlalchemy as _sa

    engine = get_engine()
    with engine.connect() as conn:
        cols = [row[1] for row in conn.execute(_sa.text("PRAGMA table_info(slack_messages)")).fetchall()]
        if "attachments" not in cols:
            conn.execute(_sa.text("ALTER TABLE slack_messages ADD COLUMN attachments JSON"))
            conn.commit()

    # Migrate old __FWD__ encoded messages to proper attachments
    db = get_session_factory()()
    try:
        fwd_msgs = db.query(Message).filter(Message.text.like("__FWD__%")).all()
        for msg in fwd_msgs:
            raw = msg.text
            after = raw[len("__FWD__"):]
            nl = after.find("\n")
            json_str = after[:nl] if nl >= 0 else after
            user_comment = after[nl + 1:].strip() if nl >= 0 else ""
            try:
                meta = _json.loads(json_str)
            except Exception:
                continue
            icon = "🔒" if meta.get("cp") else "#"
            ts_val = meta.get("ts", "")
            time_str = ""
            try:
                import time as _time
                time_str = " · Today at " + datetime.fromtimestamp(float(ts_val)).strftime("%-I:%M %p")
            except Exception:
                pass
            msg.attachments = [{
                "author_name": meta.get("s", "Unknown"),
                "text": meta.get("t", ""),
                "footer": f"{icon}{meta.get('cn', 'channel')}{time_str}",
                "ts": ts_val,
            }]
            msg.text = user_comment
        if fwd_msgs:
            db.commit()
    finally:
        db.close()


@app.on_event("startup")
async def cleanup_duplicate_dm_channels():
    """Merge duplicate DM channels (same user pair) into one on startup."""
    from mock_slack.models import get_session_factory, Channel, ChannelMember, Message

    db = get_session_factory()()
    try:
        all_dm = db.query(Channel).filter(Channel.is_im == True, Channel.is_mpim == False).all()
        # Group by sorted member pair (may have 1 or 2 members)
        pair_to_channels: dict[tuple, list] = {}
        ch_to_members: dict[str, tuple] = {}
        for ch in all_dm:
            members = tuple(sorted(
                m.user_id for m in db.query(ChannelMember).filter(ChannelMember.channel_id == ch.id).all()
            ))
            ch_to_members[ch.id] = members
            if len(members) >= 1:
                pair_to_channels.setdefault(members, []).append(ch)

        # NOTE: We intentionally do NOT merge 1-member "orphan" DMs into 2-member DMs.
        # A 1-member DM does not identify the intended other participant, so merging based
        # solely on the shared user can silently move messages into an unrelated DM.
        # Any cleanup of such orphan channels must be done by logic that can
        # deterministically infer the missing participant; since we cannot do that here,
        # we leave these channels as-is to avoid data corruption.

        # Merge duplicate 2-member DMs (same pair)
        for members, chans in pair_to_channels.items():
            if len(members) != 2 or len(chans) <= 1:
                continue
            # Keep the oldest, merge the rest into it
            canonical = min(chans, key=lambda c: c.created_at or c.id)
            for dup in chans:
                if dup.id == canonical.id:
                    continue
                db.query(Message).filter(Message.channel_id == dup.id).update(
                    {Message.channel_id: canonical.id}, synchronize_session=False
                )
                db.query(ChannelMember).filter(ChannelMember.channel_id == dup.id).delete(synchronize_session=False)
                db.delete(dup)
        db.commit()
    finally:
        db.close()


# --- Slack API routes (all under /api/) ---
SLACK_PREFIX = "/api"

app.include_router(web_router, tags=["web"])
app.include_router(conversations.router, prefix=SLACK_PREFIX, tags=["conversations"])
app.include_router(messages.router, prefix=SLACK_PREFIX, tags=["messages"])
app.include_router(users.router, prefix=SLACK_PREFIX, tags=["users"])
app.include_router(reactions.router, prefix=SLACK_PREFIX, tags=["reactions"])
app.include_router(search.router, prefix=SLACK_PREFIX, tags=["search"])
app.include_router(files.router, prefix=SLACK_PREFIX, tags=["files"])
app.include_router(pins.router, prefix=SLACK_PREFIX, tags=["pins"])
app.include_router(team.router, prefix=SLACK_PREFIX, tags=["team"])
app.include_router(auth.router, prefix=SLACK_PREFIX, tags=["auth"])
app.include_router(reminders.router, prefix=SLACK_PREFIX, tags=["reminders"])


# --- Admin endpoints ---
@app.post("/_admin/reset", tags=["admin"])
def admin_reset():
    """Reset to initial seed state."""
    success = restore_snapshot("initial")
    action_log.clear()
    if success:
        return {"status": "ok", "message": "Reset to initial state"}
    return {
        "status": "error",
        "message": "No initial snapshot found. Run `mock-slack seed` first.",
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
    from mock_slack.models import Base, get_engine
    from mock_slack.seed.generator import seed_database

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


# --- Skills ---
@app.get("/_admin/skills", tags=["admin"])
def admin_skills():
    """List all agent skills from the skills/ directory."""
    import pathlib

    skills_dir = pathlib.Path(__file__).resolve().parents[5] / "skills"
    skills = []
    if skills_dir.is_dir():
        for skill_dir in sorted(skills_dir.iterdir()):
            if not skill_dir.is_dir():
                continue
            skill_md = skill_dir / "SKILL.md"
            if skill_md.exists():
                skills.append({
                    "name": skill_dir.name,
                    "content": skill_md.read_text(),
                })
    return {"skills": skills, "count": len(skills)}


@app.get("/_admin/skills/{skill_name}", tags=["admin"])
def admin_skill_detail(skill_name: str):
    """Get a single skill by name."""
    import pathlib

    skills_dir = pathlib.Path(__file__).resolve().parents[5] / "skills"
    skill_dir = skills_dir / skill_name
    skill_md = skill_dir / "SKILL.md"
    if not skill_md.exists():
        raise HTTPException(404, f"Skill '{skill_name}' not found")
    return {"name": skill_name, "content": skill_md.read_text()}


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
    """Add SlackEnv_0AuthMiddleware to ``target_app`` when AUTH_ENABLED is truthy."""
    if not _auth_enabled():
        return False
    try:
        import env_0_auth_client  # noqa: F401
    except ImportError as exc:
        raise RuntimeError(
            "AUTH_ENABLED=1 but auth-client is not installed. "
            "Install packages/auth-client or unset AUTH_ENABLED."
        ) from exc

    from mock_slack.api.auth_middleware import SlackEnv_0AuthMiddleware
    from mock_slack.auth_scopes import SCOPE_MAP

    target_app.add_middleware(SlackEnv_0AuthMiddleware, scope_map=SCOPE_MAP, **middleware_kwargs)
    return True


_apply_auth(app)
