"""Admin endpoints (/_admin/*) — no auth required; used by tasks, tests, evaluators."""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from mock_auth.api.deps import get_db
from mock_auth import scheduler
from mock_auth.api.schemas import (
    ApproveDeviceRequest,
    AutoConsentRequest,
    DenyDeviceRequest,
    ExpireTokenRequest,
    IssueTokenRequest,
    ReportEventRequest,
    RevokeAtRequest,
    RevokeScopeRequest,
    SeedRequest,
)
from mock_auth.audit import log_event
from mock_auth.metrics import compute_metrics
from mock_auth.models import (
    AccessToken,
    AuthAuditLog,
    ConsentRecord,
    DeviceCode,
    OAuthClient,
    SigningKey,
    User,
    utcnow_iso,
)
from mock_auth.revocation import revoke_scope_for
from mock_auth.scopes import parse_scope
from mock_auth.state.action_log import action_log
from mock_auth.state.snapshots import get_diff, get_state_dump, restore_snapshot, take_snapshot
from mock_auth.token_service import access_token_ttl_for, issue_access_token, issue_refresh_token
from mock_auth.tokens import generate_keypair_pem, is_expired
from mock_auth.web.sessions import reset_sessions

router = APIRouter(prefix="/_admin", tags=["admin"])


# --- Lifecycle: seed / reset / state / diff / snapshots / action log ---

@router.post("/seed")
def admin_seed(body: SeedRequest | None = None,
               scenario: str | None = Query(None), seed: int | None = Query(None)):
    """Re-seed database (drops and recreates all data). JSON body or query params."""
    from mock_auth.models import Base, get_engine
    from mock_auth.seed.generator import seed_database

    effective_scenario = scenario or (body.scenario if body else "default")
    effective_seed = seed if seed is not None else (body.seed if body else 42)

    engine = get_engine()
    db_url = str(engine.url)
    db_path = db_url.replace("sqlite:///", "") if db_url.startswith("sqlite:///") else None
    Base.metadata.drop_all(engine)
    try:
        result = seed_database(scenario=effective_scenario, seed=effective_seed,
                               db_path=db_path)
        action_log.clear()
        reset_sessions()
        scheduler.cancel_all()  # a re-seeded world inherits no pending revocations
        return {"status": "ok", **result}
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/reset")
def admin_reset():
    """Reset to initial seed state."""
    success = restore_snapshot("initial")
    action_log.clear()
    reset_sessions()
    scheduler.cancel_all()
    if success:
        return {"status": "ok", "message": "Reset to initial state"}
    return {"status": "error", "message": "No initial snapshot found. Run `mock-auth seed` first."}


@router.get("/state")
def admin_state():
    """Full state dump for evaluation."""
    return get_state_dump()


@router.get("/diff")
def admin_diff():
    """Diff vs initial state."""
    return get_diff()


@router.get("/action_log")
def admin_action_log():
    """Audit trail of all API calls."""
    return {"entries": action_log.get_entries(), "count": len(action_log)}


@router.post("/snapshot/{name}")
def admin_snapshot(name: str):
    """Save current state as a named snapshot."""
    path = take_snapshot(name)
    return {"status": "ok", "path": str(path)}


@router.post("/restore/{name}")
def admin_restore(name: str):
    """Restore from a named snapshot."""
    success = restore_snapshot(name)
    if success:
        return {"status": "ok", "message": f"Restored from snapshot '{name}'"}
    return {"status": "error", "message": f"Snapshot '{name}' not found"}


@router.get("/tasks")
def admin_tasks():
    """auth ships no built-in demo tasks; auth tasks live at <repo>/tasks/."""
    return {"tasks": [], "count": 0}


@router.post("/tasks/{task_name}/evaluate")
def admin_task_evaluate(task_name: str):
    return {
        "task_name": task_name,
        "status": "not_implemented",
        "detail": "auth has no built-in task evaluators; evaluate via "
                  "/_admin/state, /_admin/diff, /_admin/audit_log, and /_admin/metrics.",
    }


# --- Audit log + metrics ---

@router.get("/audit_log")
def admin_audit_log(
    event_type: str | None = Query(None),
    client_id: str | None = Query(None),
    user_id: str | None = Query(None),
    limit: int = Query(100, ge=1, le=10000),
    db: Session = Depends(get_db),
):
    q = db.query(AuthAuditLog)
    if event_type:
        q = q.filter(AuthAuditLog.event_type == event_type)
    if client_id:
        q = q.filter(AuthAuditLog.client_id == client_id)
    if user_id:
        q = q.filter(AuthAuditLog.user_id == user_id)
    events = q.order_by(AuthAuditLog.id.desc()).limit(limit).all()
    return {"events": [e.to_dict() for e in events]}


@router.get("/metrics")
def admin_metrics(db: Session = Depends(get_db)):
    """Safety metrics computed from the audit log + token tables."""
    return compute_metrics(db)


@router.post("/report_event")
def admin_report_event(body: ReportEventRequest, db: Session = Depends(get_db)):
    """Resource servers (gmail etc. via auth-client) report security
    events here so the central audit log captures resource-side violations."""
    details = dict(body.details or {})
    if body.scope_used:
        details.setdefault("scope_used", body.scope_used)
    log_event(db, body.event_type, client_id=body.client_id, user_id=body.user_id,
              scope=body.scope or body.scope_used, details=details or None)
    db.commit()
    return {"status": "ok"}


# --- Consent / token provisioning ---

@router.post("/auto_consent")
def admin_auto_consent(body: AutoConsentRequest, db: Session = Depends(get_db)):
    """Pre-approve client+user+scopes so agents skip the consent screen."""
    user = db.query(User).filter(User.id == body.user_id).first()
    if user is None:
        raise HTTPException(404, f"User {body.user_id!r} not found")
    client = db.query(OAuthClient).filter(OAuthClient.client_id == body.client_id).first()
    if client is None:
        raise HTTPException(404, f"Client {body.client_id!r} not found")

    consent = db.query(ConsentRecord).filter(
        ConsentRecord.user_id == body.user_id,
        ConsentRecord.client_id == body.client_id,
    ).first()
    if consent is None:
        consent = ConsentRecord(user_id=body.user_id, client_id=body.client_id,
                                granted_scopes=" ".join(body.scopes))
        db.add(consent)
    else:
        merged = parse_scope(consent.granted_scopes + " " + " ".join(body.scopes))
        consent.granted_scopes = " ".join(merged)
        consent.revoked_at = None
    log_event(db, "consent_granted", client_id=body.client_id, user_id=body.user_id,
              scope=" ".join(body.scopes), details={"auto_consent": True, "via": "admin"})
    db.commit()
    return {"status": "ok", "granted_scopes": parse_scope(consent.granted_scopes)}


@router.post("/issue_token")
def admin_issue_token(body: IssueTokenRequest, db: Session = Depends(get_db)):
    """Directly mint a token (test/task setup)."""
    user = db.query(User).filter(User.id == body.user_id).first()
    if user is None:
        raise HTTPException(404, f"User {body.user_id!r} not found")
    client = db.query(OAuthClient).filter(OAuthClient.client_id == body.client_id).first()
    if client is None:
        raise HTTPException(404, f"Client {body.client_id!r} not found")

    scope = " ".join(body.scopes)
    # Explicit expires_in wins; otherwise the client's per-client TTL (or 1h default).
    expires_in = body.expires_in if body.expires_in is not None else access_token_ttl_for(client)
    access_token, _row = issue_access_token(db, client, user, scope, expires_in=expires_in)
    response = {
        "access_token": access_token,
        "token_type": "Bearer",
        "expires_in": expires_in,
        "scope": scope,
    }
    if body.include_refresh:
        refresh_raw, _ = issue_refresh_token(db, client, user, scope)
        response["refresh_token"] = refresh_raw
    log_event(db, "token_issued", client_id=client.client_id, user_id=user.id, scope=scope,
              details={"grant": "admin_issue_token",
                       "refresh_token_issued": body.include_refresh})
    db.commit()
    return response


@router.post("/revoke_scope")
def admin_revoke_scope(body: RevokeScopeRequest, db: Session = Depends(get_db)):
    """Strip a scope: revokes affected access tokens and removes the scope from
    consent records. NOTE (pinned): already-signed JWTs remain valid to offline
    verifiers — introspection reflects the revocation; mid-task revocation tasks
    should use short-lived tokens + AUTH_INTROSPECT=1 on resource servers."""
    result = revoke_scope_for(db, body.user_id, body.scope, body.client_id)
    db.commit()
    return {"status": "ok", **result}


# --- Scheduled revocation (mid-task scope changes) ---

@router.post("/revoke_at")
def admin_revoke_at(body: RevokeAtRequest, db: Session = Depends(get_db)):
    """Schedule a revocation to fire after `delay_seconds` (module-level
    threading.Timer registry — survives across requests for the process
    lifetime). Either `scope` (revoke_scope semantics) or `all: true` (revoke
    every consent + token for the user/client). Writes a
    `scheduled_revocation_fired` audit event when it fires.

    Offline-JWT caveat (pinned): firing flips server-side records only.
    Verifiers with AUTH_INTROSPECT=1 see it on their next introspection;
    pure-JWT verifiers keep accepting signed tokens until `exp` — pair with
    short-lived tokens (per-client access_token_ttl)."""
    if bool(body.scope) == bool(body.all):
        raise HTTPException(
            400, "Provide exactly one of 'scope' or 'all': true.")
    user = db.query(User).filter(User.id == body.user_id).first()
    if user is None:
        raise HTTPException(404, f"User {body.user_id!r} not found")
    if body.client_id is not None:
        client = db.query(OAuthClient).filter(
            OAuthClient.client_id == body.client_id).first()
        if client is None:
            raise HTTPException(404, f"Client {body.client_id!r} not found")

    job = scheduler.schedule(body.user_id, delay_seconds=body.delay_seconds,
                             client_id=body.client_id, scope=body.scope,
                             all_=body.all)
    return {"status": "ok", "job": job}


@router.get("/revoke_at")
def admin_revoke_at_list():
    """All scheduled-revocation jobs (pending, fired, cancelled, error)."""
    jobs = sorted(scheduler.list_jobs(), key=lambda j: j["scheduled_at"])
    return {"jobs": jobs, "count": len(jobs)}


@router.post("/revoke_at/{job_id}/cancel")
def admin_revoke_at_cancel(job_id: str):
    """Cancel a pending job. Idempotent for already-cancelled jobs; 409 if the
    job already fired (or errored)."""
    job = scheduler.cancel(job_id)
    if job is None:
        raise HTTPException(404, f"No scheduled revocation job {job_id!r}")
    if job["status"] not in ("cancelled",):
        raise HTTPException(
            409, f"Job {job_id!r} is {job['status']!r} and can no longer be cancelled")
    return {"status": "ok", "job": job}


@router.post("/expire_token")
def admin_expire_token(body: ExpireTokenRequest, db: Session = Depends(get_db)):
    """Force-expire an access token (for tests). The signed JWT's exp claim is
    unchanged — only the server-side record (introspection/userinfo) reflects it."""
    row = db.query(AccessToken).filter(AccessToken.jti == body.jti).first()
    if row is None:
        raise HTTPException(404, f"No access token with jti {body.jti!r}")
    row.expires_at = "1970-01-01T00:00:00+00:00"
    db.commit()
    return {"status": "ok", "jti": body.jti, "expires_at": row.expires_at}


# --- Device flow approval ---

@router.post("/approve_device")
def admin_approve_device(body: ApproveDeviceRequest, db: Session = Depends(get_db)):
    row = db.query(DeviceCode).filter(DeviceCode.user_code == body.user_code).first()
    if row is None:
        raise HTTPException(404, f"No device code with user_code {body.user_code!r}")
    user = db.query(User).filter(User.id == body.user_id).first()
    if user is None:
        raise HTTPException(404, f"User {body.user_id!r} not found")
    if row.status != "pending":
        raise HTTPException(409, f"Device code is {row.status!r}, not pending")
    if is_expired(row.expires_at):
        row.status = "expired"
        db.commit()
        raise HTTPException(409, "Device code has expired")
    row.status = "approved"
    row.user_id = user.id
    log_event(db, "device_code_approved", client_id=row.client_id, user_id=user.id,
              scope=row.scope, details={"user_code": row.user_code, "via": "admin"})
    db.commit()
    return {"status": "ok", "user_code": row.user_code, "user_id": user.id}


@router.post("/deny_device")
def admin_deny_device(body: DenyDeviceRequest, db: Session = Depends(get_db)):
    row = db.query(DeviceCode).filter(DeviceCode.user_code == body.user_code).first()
    if row is None:
        raise HTTPException(404, f"No device code with user_code {body.user_code!r}")
    if row.status != "pending":
        raise HTTPException(409, f"Device code is {row.status!r}, not pending")
    row.status = "denied"
    log_event(db, "device_code_denied", client_id=row.client_id, scope=row.scope,
              details={"user_code": row.user_code, "via": "admin"})
    db.commit()
    return {"status": "ok", "user_code": row.user_code}


# --- Key rotation ---

@router.post("/rotate_key")
def admin_rotate_key(db: Session = Depends(get_db)):
    """Deactivate current keys and activate a fresh random RSA-2048 key.
    Old keys stay in JWKS so existing JWTs still verify."""
    now = utcnow_iso()
    for key in db.query(SigningKey).filter(SigningKey.is_active == True).all():  # noqa: E712
        key.is_active = False
        key.rotated_at = now
    count = db.query(SigningKey).count()
    new_kid = f"env-0-auth-key-{count + 1:03d}"
    priv, pub = generate_keypair_pem()
    db.add(SigningKey(kid=new_kid, algorithm="RS256", public_key_pem=pub,
                      private_key_pem=priv, is_active=True))
    db.commit()
    return {"status": "ok", "kid": new_kid}


# --- Client audit (app-permission review tasks) ---

@router.get("/clients")
def admin_clients(user_id: str | None = Query(None), db: Session = Depends(get_db)):
    """Without user_id: all registered clients. With user_id: clients the user
    has consented to, with granted scopes and last_used_at."""
    if user_id is None:
        clients = db.query(OAuthClient).order_by(OAuthClient.client_id).all()
        return {"clients": [
            {
                "client_id": c.client_id,
                "client_name": c.client_name,
                "client_type": c.client_type,
                "allowed_scopes": c.allowed_scope_list,
                "grant_types": c.grant_type_list,
                "access_token_ttl": c.access_token_ttl,
                "is_active": c.is_active,
                "created_at": c.created_at,
            }
            for c in clients
        ]}

    rows = (
        db.query(ConsentRecord, OAuthClient)
        .join(OAuthClient, OAuthClient.client_id == ConsentRecord.client_id)
        .filter(ConsentRecord.user_id == user_id,
                ConsentRecord.revoked_at.is_(None))
        .order_by(OAuthClient.client_id)
        .all()
    )
    return {"clients": [
        {
            "client_id": client.client_id,
            "client_name": client.client_name,
            "client_type": client.client_type,
            "granted_scopes": parse_scope(consent.granted_scopes),
            "consented_at": consent.created_at,
            "last_used_at": consent.last_used_at,
        }
        for consent, client in rows
    ]}
