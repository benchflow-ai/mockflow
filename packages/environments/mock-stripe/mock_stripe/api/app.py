"""Main FastAPI application for the mock Stripe API."""

from __future__ import annotations

import hashlib
import json
import os
import pathlib
import time

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from starlette.middleware.base import BaseHTTPMiddleware

from mock_stripe.state.action_log import action_log
from mock_stripe.state.snapshots import get_diff, get_state_dump, restore_snapshot, take_snapshot
from mock_stripe.web.routes import router as web_router

from . import (
    account,
    balance,
    charges,
    customers,
    events,
    payment_intents,
    payment_methods,
    products,
    refunds,
    webhook_endpoints,
)
from .errors import StripeError
from .forms import parse_form

app = FastAPI(
    title="Mock Stripe API",
    description="Stripe-compatible REST API for AI agent safety evaluation and RL training",
    version="0.1.0",
)


# --- Stripe-style error responses ---

@app.exception_handler(StripeError)
async def stripe_error_handler(request: Request, exc: StripeError):
    return JSONResponse(status_code=exc.status_code, content=exc.to_body())


@app.exception_handler(HTTPException)
async def http_error_handler(request: Request, exc: HTTPException):
    """Stray HTTPExceptions still come out in the Stripe envelope."""
    message = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"type": "invalid_request_error", "message": message}},
    )


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError):
    """Stripe returns 400 invalid_request_error for malformed requests (not 422)."""
    errors = exc.errors()
    message = (
        "; ".join(
            f"{'.'.join(str(loc) for loc in e.get('loc', []))}: {e.get('msg', '')}"
            for e in errors
        )
        if errors
        else "Invalid request."
    )
    return JSONResponse(
        status_code=400,
        content={"error": {"type": "invalid_request_error", "message": message}},
    )


# CORS — allow everything for local dev
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _parse_body_for_log(body_bytes: bytes, content_type: str) -> dict | None:
    if not body_bytes:
        return None
    if "application/json" in content_type:
        try:
            data = json.loads(body_bytes)
            return data if isinstance(data, dict) else None
        except (json.JSONDecodeError, UnicodeDecodeError):
            return None
    try:
        data = parse_form(body_bytes)
        return data or None
    except Exception:
        return None


def _token_type(request: Request) -> str:
    auth = request.headers.get("authorization") or ""
    if "sk_live_" in auth:
        return "live"
    if "sk_test_" in auth:
        return "test"
    return ""


# --- Idempotency middleware (POST /v1/* with Idempotency-Key header) ---
class IdempotencyMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        key = request.headers.get("idempotency-key")
        path = str(request.url.path)
        if not key or request.method != "POST" or not path.startswith("/v1/"):
            return await call_next(request)

        from mock_stripe.models import IdempotencyRecord, get_session_factory

        body_bytes = await request.body()
        fingerprint = hashlib.sha256(
            f"{request.method} {path}\n".encode() + body_bytes
        ).hexdigest()

        SessionLocal = get_session_factory()
        db = SessionLocal()
        try:
            record = db.get(IdempotencyRecord, key)
            if record is not None:
                if record.fingerprint != fingerprint:
                    return JSONResponse(
                        status_code=400,
                        content={
                            "error": {
                                "type": "idempotency_error",
                                "message": (
                                    "Keys for idempotent requests can only be used "
                                    "with the same parameters they were first used "
                                    f"with. Try using a key other than '{key}' if "
                                    "you meant to execute a different request."
                                ),
                            }
                        },
                    )
                return Response(
                    content=record.response_body,
                    status_code=record.response_status,
                    media_type="application/json",
                    headers={"Idempotent-Replayed": "true"},
                )
        finally:
            db.close()

        response = await call_next(request)
        resp_body = b""
        async for chunk in response.body_iterator:
            resp_body += chunk

        db = SessionLocal()
        try:
            if db.get(IdempotencyRecord, key) is None:
                db.add(IdempotencyRecord(
                    key=key,
                    method=request.method,
                    path=path,
                    fingerprint=fingerprint,
                    response_status=response.status_code,
                    response_body=resp_body.decode("utf-8", errors="replace"),
                    created=int(time.time()),
                ))
                db.commit()
        finally:
            db.close()

        headers = dict(response.headers)
        headers.pop("content-length", None)
        return Response(
            content=resp_body,
            status_code=response.status_code,
            headers=headers,
            media_type=response.media_type,
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
        content_type = (request.headers.get("content-type") or "").lower()
        body_dict = _parse_body_for_log(body_bytes, content_type)

        response = await call_next(request)

        action_log.record(
            method=request.method,
            path=full_path,
            user_id="",
            request_body=body_dict,
            response_status=response.status_code,
            token_type=_token_type(request),
        )
        return response


# Middleware order: last added runs first. ActionLog (outer) sees every request
# including idempotent replays; Idempotency (inner) wraps the routers.
app.add_middleware(IdempotencyMiddleware)
app.add_middleware(ActionLogMiddleware)


# --- Routers ---
app.include_router(web_router, tags=["web"])
app.include_router(customers.router, tags=["customers"])
app.include_router(payment_methods.router, tags=["payment_methods"])
app.include_router(payment_intents.router, tags=["payment_intents"])
app.include_router(charges.router, tags=["charges"])
app.include_router(refunds.router, tags=["refunds"])
app.include_router(products.router, tags=["products"])
app.include_router(balance.router, tags=["balance"])
app.include_router(events.router, tags=["events"])
app.include_router(account.router, tags=["account"])
app.include_router(webhook_endpoints.router, tags=["webhook_endpoints"])


# --- Admin endpoints ---
@app.post("/_admin/reset", tags=["admin"])
def admin_reset():
    """Reset to initial seed state."""
    success = restore_snapshot("initial")
    action_log.clear()
    if success:
        return {"status": "ok", "message": "Reset to initial state"}
    return {"status": "error", "message": "No initial snapshot found. Run `mock-stripe seed` first."}


@app.post("/_admin/seed", tags=["admin"])
async def admin_seed(request: Request, scenario: str | None = None, seed: int | None = None):
    """Re-seed database with a specific scenario (drops and recreates all data).

    Accepts scenario/seed from query params or a JSON body; query takes
    precedence when both are supplied.
    """
    # Widen to accept either source: read query first, fall back to JSON body.
    body: dict = {}
    if scenario is None or seed is None:
        try:
            payload = await request.json()
            if isinstance(payload, dict):
                body = payload
        except Exception:
            body = {}
    scenario = scenario if scenario is not None else body.get("scenario", "default")
    seed = seed if seed is not None else body.get("seed", 42)

    from mock_stripe.models import Base, get_engine
    from mock_stripe.seed.generator import seed_database

    engine = get_engine()
    db_url = str(engine.url)
    db_path = db_url.replace("sqlite:///", "") if db_url.startswith("sqlite:///") else None
    Base.metadata.drop_all(engine)
    try:
        result = seed_database(scenario=scenario, seed=seed, db_path=db_path)
        action_log.clear()
        return {"status": "ok", "scenario": scenario, **result}
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


@app.get("/_admin/webhook_deliveries", tags=["admin"])
def admin_webhook_deliveries(endpoint: str | None = None, event: str | None = None,
                             limit: int = 100):
    """Webhook delivery attempts (newest first; status_code/error per attempt)."""
    from mock_stripe.models import WebhookDelivery, get_session_factory
    from .serializers import webhook_delivery_to_dict

    db = get_session_factory()()
    try:
        query = db.query(WebhookDelivery).order_by(WebhookDelivery.seq.desc())
        if endpoint:
            query = query.filter(WebhookDelivery.endpoint_id == endpoint)
        if event:
            query = query.filter(WebhookDelivery.event_id == event)
        rows = query.all()
        limit = max(1, min(int(limit), 1000))
        return {
            "deliveries": [webhook_delivery_to_dict(r) for r in rows[:limit]],
            "count": len(rows),
        }
    finally:
        db.close()


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
    from mock_stripe.tasks import get_task as _get_task
    from mock_stripe.tasks import list_tasks as _list_tasks

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
    from mock_stripe.tasks import get_task as _get_task

    task = _get_task(task_name)
    if not task:
        raise HTTPException(404, f"Task '{task_name}' not found")

    state = get_state_dump()
    diff = get_diff()
    log_entries = action_log.get_entries()

    reward, done = task.evaluate(state, diff, log_entries)

    diff_summary = {"added": 0, "updated": 0, "deleted": 0}
    for kind in ("added", "updated", "deleted"):
        for rows in diff.get(kind, {}).values():
            diff_summary[kind] += len(rows)

    recent_actions = log_entries[-20:] if log_entries else []

    return {
        "task_name": task_name,
        "reward": reward,
        "done": done,
        "diff_summary": diff_summary,
        "action_count": len(log_entries),
        "recent_actions": recent_actions,
    }


def _scan_skill_files(skill_dir: pathlib.Path) -> list[dict]:
    """Recursively collect all files in a skill directory."""
    files = []
    for path in sorted(skill_dir.rglob("*")):
        if not path.is_file():
            continue
        rel = str(path.relative_to(skill_dir))
        if any(part.startswith(".") or part == "__pycache__" for part in path.parts):
            continue
        try:
            content = path.read_text()
        except (UnicodeDecodeError, ValueError):
            content = f"(binary file, {path.stat().st_size} bytes)"
        files.append({"path": rel, "content": content, "size": path.stat().st_size})
    return files


@app.get("/_admin/skills", tags=["admin"])
def admin_skills():
    """List all agent skills from the repo skills/ directory."""
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
                    "files": _scan_skill_files(skill_dir),
                })
    return {"skills": skills, "count": len(skills)}


@app.get("/_admin/skills/{skill_name}", tags=["admin"])
def admin_skill_detail(skill_name: str):
    """Get a single skill with all files in its directory."""
    skills_dir = pathlib.Path(__file__).resolve().parents[5] / "skills"
    skill_dir = skills_dir / skill_name
    skill_md = skill_dir / "SKILL.md"
    if not skill_md.exists():
        raise HTTPException(404, f"Skill '{skill_name}' not found")
    return {
        "name": skill_name,
        "content": skill_md.read_text(),
        "files": _scan_skill_files(skill_dir),
    }


# --- Health check ---
@app.get("/health")
def health():
    return {"status": "ok"}


# --- auth integration (optional; enabled via AUTH_ENABLED) ---

def _auth_enabled() -> bool:
    """Mirror env_0_auth_client.is_auth_enabled() without importing the optional dep."""
    return os.environ.get("AUTH_ENABLED", "").strip().lower() in ("1", "true", "yes")


def _apply_auth(target_app: FastAPI, **middleware_kwargs) -> bool:
    """Add StripeMockAuthMiddleware to ``target_app`` when AUTH_ENABLED is truthy.

    Returns True when the middleware was added, False when auth is disabled.
    Extra ``middleware_kwargs`` are forwarded to the middleware (tests pass
    ``jwks_static=...`` so no HTTP key fetching is needed).

    NOTE: ``app`` is a module-level singleton and AUTH_ENABLED is read at
    import time (the ``_apply_auth(app)`` call below). Middleware cannot be
    added once the app has started, so tests that need an auth-enabled app must
    build a FRESH instance, e.g.:

        monkeypatch.delenv("AUTH_ENABLED", raising=False)
        app_module = importlib.reload(mock_stripe.api.app)   # fresh, no auth
        monkeypatch.setenv("AUTH_ENABLED", "1")
        app_module._apply_auth(app_module.app, jwks_static=jwks)

    (see tests/test_auth_integration.py). Normal serving keeps using the
    singleton untouched.
    """
    if not _auth_enabled():
        return False
    try:
        import env_0_auth_client  # noqa: F401
    except ImportError as exc:
        raise RuntimeError(
            "AUTH_ENABLED=1 but auth-client is not installed. "
            "Install it (from the monorepo: uv pip install -e packages/auth-client), "
            "or unset AUTH_ENABLED."
        ) from exc

    # Stripe-side subclass: exempts the web dashboard root ("/"), /static and
    # /mcp on top of the contract defaults -- see auth_middleware.py.
    from mock_stripe.api.auth_middleware import StripeMockAuthMiddleware
    from mock_stripe.auth_scopes import STRIPE_SCOPE_MAP

    # Added after full app assembly, so this middleware is OUTERMOST: requests
    # rejected here (401/403) are not recorded in the action log.
    target_app.add_middleware(
        StripeMockAuthMiddleware, scope_map=STRIPE_SCOPE_MAP, **middleware_kwargs
    )
    return True


_apply_auth(app)
