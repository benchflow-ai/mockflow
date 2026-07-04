"""Refresh token model (opaque `rt_` + 48 hex; rotation with family reuse detection)."""

from __future__ import annotations

from sqlalchemy import Boolean, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from mock_auth.models.base import Base, utcnow_iso


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    token_hash: Mapped[str] = mapped_column(String, primary_key=True)  # sha256(raw token) hex
    client_id: Mapped[str] = mapped_column(ForeignKey("oauth_clients.client_id"), nullable=False)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    scope: Mapped[str] = mapped_column(String, nullable=False)
    family_id: Mapped[str] = mapped_column(String, nullable=False)  # rotation family; detect reuse
    expires_at: Mapped[str] = mapped_column(String, nullable=False)  # default 30 days
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)
    replaced_by: Mapped[str | None] = mapped_column(String, nullable=True)  # hash of successor token
    created_at: Mapped[str] = mapped_column(String, default=utcnow_iso)
