"""Device code model (RFC 8628 device authorization grant, for CLI agents)."""

from __future__ import annotations

from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from mock_auth.models.base import Base, utcnow_iso


class DeviceCode(Base):
    __tablename__ = "device_codes"

    device_code: Mapped[str] = mapped_column(String, primary_key=True)
    user_code: Mapped[str] = mapped_column(String, unique=True, nullable=False)  # short human code
    client_id: Mapped[str] = mapped_column(ForeignKey("oauth_clients.client_id"), nullable=False)
    scope: Mapped[str] = mapped_column(String, nullable=False)
    user_id: Mapped[str | None] = mapped_column(String, nullable=True)  # NULL until user approves
    status: Mapped[str] = mapped_column(String, default="pending")  # pending|approved|denied|expired|redeemed
    expires_at: Mapped[str] = mapped_column(String, nullable=False)  # 15 minutes
    interval: Mapped[int] = mapped_column(Integer, default=5)  # polling interval seconds
    created_at: Mapped[str] = mapped_column(String, default=utcnow_iso)
