"""WebhookEndpoint (`we_`) and WebhookDelivery (`whd_`, mock-internal) models.

`webhook_endpoints` mirrors the real Stripe resource. `webhook_deliveries` is
a mock-only audit table (real Stripe does not expose delivery attempts via the
v1 API); it is surfaced at `GET /_admin/webhook_deliveries`.

Both tables are part of MODEL_REGISTRY, so endpoints AND delivery attempts are
included in snapshots/restore/diff (documented in API_NOTES.md).
"""

from __future__ import annotations

from sqlalchemy import Boolean, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, next_seq


class WebhookEndpoint(Base):
    __tablename__ = "webhook_endpoints"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    url: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str | None] = mapped_column(String, nullable=True)
    # JSON list of enabled event types, e.g. '["charge.succeeded"]' or '["*"]'.
    enabled_events_json: Mapped[str] = mapped_column(Text, default="[]")
    # whsec_... signing secret — returned ONLY on create (real behavior).
    secret: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, default="enabled")  # enabled|disabled
    api_version: Mapped[str | None] = mapped_column(String, nullable=True)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")
    created: Mapped[int] = mapped_column(Integer, default=0)
    seq: Mapped[int] = mapped_column(Integer, default=next_seq)


class WebhookDelivery(Base):
    __tablename__ = "webhook_deliveries"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    endpoint_id: Mapped[str] = mapped_column(String, nullable=False)
    event_id: Mapped[str] = mapped_column(String, nullable=False)
    event_type: Mapped[str] = mapped_column(String, nullable=False)
    url: Mapped[str] = mapped_column(String, nullable=False)
    # HTTP status returned by the receiver; NULL when the request failed at the
    # transport level (connection refused, timeout, ...), in which case `error`
    # holds the exception text.
    status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    success: Mapped[bool] = mapped_column(Boolean, default=False)
    created: Mapped[int] = mapped_column(Integer, default=0)
    seq: Mapped[int] = mapped_column(Integer, default=next_seq)
