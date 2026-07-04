"""Auth audit log model — the substrate for safety metrics."""

from __future__ import annotations

import json

from sqlalchemy import Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from mock_auth.models.base import Base, utcnow_iso

# All audit event types emitted by auth (see docs/ideas/auth.md),
# plus `resource_access` reported by resource-server middleware via /_admin/report_event.
AUDIT_EVENT_TYPES = [
    "authorization_request",
    "authorization_grant",
    "authorization_deny",
    "token_issued",
    "token_refreshed",
    "token_revoked",
    "token_introspected",
    "token_expired_during_use",
    "scope_escalation_attempt",
    "impersonation_attempt",
    "consent_granted",
    "consent_revoked",
    "device_code_issued",
    "device_code_approved",
    "device_code_denied",
    "invalid_client",
    "invalid_token",
    "pkce_failure",
    "resource_access",
    "scheduled_revocation_fired",
    "web_sso_assertion_issued",
]


class AuthAuditLog(Base):
    __tablename__ = "auth_audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_type: Mapped[str] = mapped_column(String, nullable=False)
    client_id: Mapped[str | None] = mapped_column(String, nullable=True)
    user_id: Mapped[str | None] = mapped_column(String, nullable=True)
    scope: Mapped[str | None] = mapped_column(String, nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String, nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String, nullable=True)
    details: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON blob
    created_at: Mapped[str] = mapped_column(String, default=utcnow_iso)

    def to_dict(self) -> dict:
        try:
            details = json.loads(self.details) if self.details else None
        except (ValueError, TypeError):
            details = self.details
        return {
            "id": self.id,
            "event_type": self.event_type,
            "client_id": self.client_id,
            "user_id": self.user_id,
            "scope": self.scope,
            "ip_address": self.ip_address,
            "user_agent": self.user_agent,
            "details": details,
            "created_at": self.created_at,
        }
