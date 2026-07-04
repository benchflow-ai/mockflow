"""Authorization code model (short-lived, single-use)."""

from __future__ import annotations

from sqlalchemy import Boolean, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from mock_auth.models.base import Base, utcnow_iso


class AuthorizationCode(Base):
    __tablename__ = "authorization_codes"

    code: Mapped[str] = mapped_column(String, primary_key=True)
    client_id: Mapped[str] = mapped_column(ForeignKey("oauth_clients.client_id"), nullable=False)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    redirect_uri: Mapped[str] = mapped_column(String, nullable=False)
    scope: Mapped[str] = mapped_column(String, nullable=False)  # space-separated granted scopes
    code_challenge: Mapped[str | None] = mapped_column(String, nullable=True)  # PKCE
    code_challenge_method: Mapped[str | None] = mapped_column(String, nullable=True)  # 'S256' | 'plain'
    nonce: Mapped[str | None] = mapped_column(String, nullable=True)  # OIDC nonce
    state: Mapped[str | None] = mapped_column(String, nullable=True)
    expires_at: Mapped[str] = mapped_column(String, nullable=False)  # 30 seconds from creation
    used: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[str] = mapped_column(String, default=utcnow_iso)
