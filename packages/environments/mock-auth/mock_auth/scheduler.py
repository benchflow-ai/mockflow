"""Scheduled revocation — module-level threading.Timer registry for /_admin/revoke_at.

Tasks use this to flip a user's permissions MID-TASK ("the user changed their
mind N seconds in"): after `delay_seconds` the job revokes a scope
(revoke_scope semantics) or everything (`all=true`) for a user/client and
writes a `scheduled_revocation_fired` audit event.

The registry is module-level so jobs survive across requests for the lifetime
of the server process. Jobs are listed via GET /_admin/revoke_at and cancelled
via POST /_admin/revoke_at/{job_id}/cancel. `/_admin/seed` and `/_admin/reset`
cancel all pending jobs (a re-seeded world should not inherit timers).

Pinned offline-JWT caveat: when a job fires, only the server-side records flip.
Resource servers running auth-client with AUTH_INTROSPECT=1 see the
revocation on their next introspection; pure-JWT (offline) verifiers keep
accepting already-signed tokens until their `exp`. Combine revoke_at with
short-lived tokens (per-client `access_token_ttl`) and/or introspection.
"""

from __future__ import annotations

import secrets
import threading
from datetime import datetime, timedelta, timezone


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


_LOCK = threading.Lock()
_JOBS: dict[str, dict] = {}      # job_id -> public job dict (status mutated in place)
_TIMERS: dict[str, threading.Timer] = {}


def _fire(job_id: str) -> None:
    """Timer callback: perform the revocation and audit it. Never raises."""
    with _LOCK:
        job = _JOBS.get(job_id)
        if job is None or job["status"] != "pending":
            return  # cancelled (or unknown) — lost the race, do nothing
        job["status"] = "fired"
        job["fired_at"] = _iso(datetime.now(timezone.utc))
        _TIMERS.pop(job_id, None)

    # DB work outside the lock; session opened at fire time so the job targets
    # the CURRENT engine (matters for tests that reset the engine per test).
    from mock_auth.audit import log_event
    from mock_auth.models import get_session_factory
    from mock_auth.revocation import revoke_all_for, revoke_scope_for

    try:
        db = get_session_factory()()
        try:
            if job["all"]:
                result = revoke_all_for(db, job["user_id"], job["client_id"],
                                        via="scheduled_revocation")
            else:
                result = revoke_scope_for(db, job["user_id"], job["scope"],
                                          job["client_id"])
            log_event(db, "scheduled_revocation_fired",
                      client_id=job["client_id"], user_id=job["user_id"],
                      scope=job["scope"],
                      details={"job_id": job_id, "all": job["all"],
                               "delay_seconds": job["delay_seconds"],
                               "result": result})
            db.commit()
            with _LOCK:
                job["result"] = result
        finally:
            db.close()
    except Exception as exc:  # pragma: no cover - defensive; timers must not die loudly
        with _LOCK:
            job["status"] = "error"
            job["error"] = f"{type(exc).__name__}: {exc}"


def schedule(user_id: str, *, delay_seconds: float, client_id: str | None = None,
             scope: str | None = None, all_: bool = False) -> dict:
    """Register a job and start its timer. Validation is the API layer's job."""
    now = datetime.now(timezone.utc)
    job_id = "rvk_" + secrets.token_hex(6)
    job = {
        "job_id": job_id,
        "status": "pending",
        "user_id": user_id,
        "client_id": client_id,
        "scope": scope,
        "all": all_,
        "delay_seconds": delay_seconds,
        "scheduled_at": _iso(now),
        "fire_at": _iso(now + timedelta(seconds=delay_seconds)),
        "fired_at": None,
        "result": None,
    }
    timer = threading.Timer(delay_seconds, _fire, args=(job_id,))
    timer.daemon = True
    with _LOCK:
        _JOBS[job_id] = job
        _TIMERS[job_id] = timer
    timer.start()
    return dict(job)


def list_jobs() -> list[dict]:
    with _LOCK:
        return [dict(j) for j in _JOBS.values()]


def get_job(job_id: str) -> dict | None:
    with _LOCK:
        job = _JOBS.get(job_id)
        return dict(job) if job else None


def cancel(job_id: str) -> dict | None:
    """Cancel a pending job. Returns the job dict (status reflects the outcome),
    or None if the job_id is unknown. Cancelling a fired job is a no-op
    (status stays 'fired') — the caller turns that into a 409."""
    with _LOCK:
        job = _JOBS.get(job_id)
        if job is None:
            return None
        if job["status"] == "pending":
            timer = _TIMERS.pop(job_id, None)
            if timer is not None:
                timer.cancel()
            job["status"] = "cancelled"
        return dict(job)


def cancel_all() -> int:
    """Cancel every pending job (called on /_admin/seed, /_admin/reset, tests)."""
    with _LOCK:
        cancelled = 0
        for job_id, job in _JOBS.items():
            if job["status"] == "pending":
                timer = _TIMERS.pop(job_id, None)
                if timer is not None:
                    timer.cancel()
                job["status"] = "cancelled"
                cancelled += 1
        return cancelled


def clear() -> None:
    """Cancel pending timers and drop the registry (test isolation)."""
    cancel_all()
    with _LOCK:
        _JOBS.clear()
        _TIMERS.clear()
