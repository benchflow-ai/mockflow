"""Access token model.

The raw access token string IS the RS256 JWT; `token_hash` stores sha256(jwt) hex.
`user_id` is nullable to support `client_credentials` tokens that are not bound to
a user (divergence from the spec SQL, documented in API_NOTES.md).
"""

from __future__ import annotations

from sqlalchemy import Boolean, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from mock_auth.models.base import Base, utcnow_iso


class AccessToken(Base):
    __tablename__ = "access_tokens"

    token_hash: Mapped[str] = mapped_column(String, primary_key=True)  # sha256(jwt_string) hex
    jti: Mapped[str] = mapped_column(String, unique=True, nullable=False)  # tok_ + 24 hex
    client_id: Mapped[str] = mapped_column(ForeignKey("oauth_clients.client_id"), nullable=False)
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    scope: Mapped[str] = mapped_column(String, nullable=False)
    expires_at: Mapped[str] = mapped_column(String, nullable=False)  # default 1 hour
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[str] = mapped_column(String, default=utcnow_iso)
