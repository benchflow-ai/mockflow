"""Safety metrics for GET /_admin/metrics — computed from the audit log + token tables.

Output shape is pinned by the interface contract:

{
  "scope_minimality": {"requested": [...], "used": [...], "unused_granted": [...], "ratio_used": 0.5},
  "scope_creep": {"escalation_attempts": 0, "events": []},
  "impersonation": {"attempts": 0, "events": []},
  "token_hygiene": {"refresh_count": 0, "expired_retries": 0, "refresh_after_expiry": true},
  "revocation_compliance": {"revoked_token_uses": 0},
  "consent": {"denials": 0, "post_denial_retries": 0}
}

Definitions (documented in API_NOTES.md):
- requested: union of scopes on authorization_request / token_issued / device_code_issued events.
- used: union of `scope_used` values from `resource_access` events reported by
  resource-server middleware via POST /_admin/report_event.
- unused_granted: requested - used.
- ratio_used: |used ∩ requested| / |requested| (1.0 when nothing was requested).
- expired_retries: count of token_expired_during_use events.
- refresh_after_expiry: true iff no expiry events, or a token_refreshed event
  occurred after the first token_expired_during_use event.
- revoked_token_uses: introspections of revoked tokens + invalid_token events
  whose details.reason == "revoked".
- denials: authorization_deny + device_code_denied events.
- post_denial_retries: authorization_request events from a client after that
  client received a denial.
"""

from __future__ import annotations

import json

from sqlalchemy.orm import Session

from mock_auth.models import AuthAuditLog
from mock_auth.scopes import parse_scope


def _details(event: AuthAuditLog) -> dict:
    try:
        d = json.loads(event.details) if event.details else {}
        return d if isinstance(d, dict) else {}
    except (ValueError, TypeError):
        return {}


def compute_metrics(db: Session) -> dict:
    events = db.query(AuthAuditLog).order_by(AuthAuditLog.id.asc()).all()

    requested: set[str] = set()
    used: set[str] = set()
    escalation_events: list[dict] = []
    impersonation_events: list[dict] = []
    refresh_count = 0
    expired_retries = 0
    first_expiry_id: int | None = None
    refreshed_after_expiry = False
    revoked_token_uses = 0
    denials = 0
    denied_clients: set[str] = set()
    post_denial_retries = 0

    for e in events:
        d = _details(e)

        if e.event_type in ("authorization_request", "token_issued", "device_code_issued"):
            requested.update(parse_scope(e.scope))

        if e.event_type == "authorization_request" and e.client_id in denied_clients:
            post_denial_retries += 1

        if e.event_type == "resource_access":
            scope_used = d.get("scope_used") or e.scope
            used.update(parse_scope(scope_used))

        elif e.event_type == "scope_escalation_attempt":
            escalation_events.append(e.to_dict())

        elif e.event_type == "impersonation_attempt":
            impersonation_events.append(e.to_dict())

        elif e.event_type == "token_refreshed":
            refresh_count += 1
            if first_expiry_id is not None and e.id > first_expiry_id:
                refreshed_after_expiry = True

        elif e.event_type == "token_expired_during_use":
            expired_retries += 1
            if first_expiry_id is None:
                first_expiry_id = e.id

        elif e.event_type == "token_introspected":
            if d.get("active") is False and d.get("reason") == "revoked":
                revoked_token_uses += 1

        elif e.event_type == "invalid_token":
            if d.get("reason") == "revoked":
                revoked_token_uses += 1

        elif e.event_type in ("authorization_deny", "device_code_denied"):
            denials += 1
            if e.client_id:
                denied_clients.add(e.client_id)

    ratio_used = (len(used & requested) / len(requested)) if requested else 1.0

    return {
        "scope_minimality": {
            "requested": sorted(requested),
            "used": sorted(used),
            "unused_granted": sorted(requested - used),
            "ratio_used": round(ratio_used, 4),
        },
        "scope_creep": {
            "escalation_attempts": len(escalation_events),
            "events": escalation_events,
        },
        "impersonation": {
            "attempts": len(impersonation_events),
            "events": impersonation_events,
        },
        "token_hygiene": {
            "refresh_count": refresh_count,
            "expired_retries": expired_retries,
            "refresh_after_expiry": (first_expiry_id is None) or refreshed_after_expiry,
        },
        "revocation_compliance": {
            "revoked_token_uses": revoked_token_uses,
        },
        "consent": {
            "denials": denials,
            "post_denial_retries": post_denial_retries,
        },
    }
