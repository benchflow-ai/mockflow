"""Audit log helper — every security-relevant event lands in auth_audit_log."""

from __future__ import annotations

import json

from sqlalchemy.orm import Session

from mock_auth.models import AuthAuditLog


def log_event(
    db: Session,
    event_type: str,
    *,
    client_id: str | None = None,
    user_id: str | None = None,
    scope: str | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
    details: dict | None = None,
) -> AuthAuditLog:
    """Add an audit event to the session (caller commits)."""
    entry = AuthAuditLog(
        event_type=event_type,
        client_id=client_id,
        user_id=user_id,
        scope=scope,
        ip_address=ip_address,
        user_agent=user_agent,
        details=json.dumps(details) if details is not None else None,
    )
    db.add(entry)
    return entry


def request_meta(request) -> dict:
    """Extract ip/user_agent kwargs from a FastAPI Request (best-effort)."""
    if request is None:
        return {}
    client = getattr(request, "client", None)
    return {
        "ip_address": client.host if client else None,
        "user_agent": request.headers.get("user-agent"),
    }
