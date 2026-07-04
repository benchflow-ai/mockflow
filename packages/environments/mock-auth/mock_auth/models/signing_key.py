"""Signing key model (RS256 keys; supports rotation)."""

from __future__ import annotations

from sqlalchemy import Boolean, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from mock_auth.models.base import Base, utcnow_iso


class SigningKey(Base):
    __tablename__ = "signing_keys"

    kid: Mapped[str] = mapped_column(String, primary_key=True)
    algorithm: Mapped[str] = mapped_column(String, nullable=False, default="RS256")
    public_key_pem: Mapped[str] = mapped_column(Text, nullable=False)
    private_key_pem: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[str] = mapped_column(String, default=utcnow_iso)
    rotated_at: Mapped[str | None] = mapped_column(String, nullable=True)
