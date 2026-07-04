"""OAuth client model."""

from __future__ import annotations

import json

from sqlalchemy import Boolean, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from mock_auth.models.base import Base, utcnow_iso


class OAuthClient(Base):
    __tablename__ = "oauth_clients"

    client_id: Mapped[str] = mapped_column(String, primary_key=True)
    client_secret: Mapped[str] = mapped_column(String, nullable=False, default="")  # bcrypt hash; "" for public
    client_name: Mapped[str] = mapped_column(String, nullable=False)
    client_type: Mapped[str] = mapped_column(String, default="confidential")  # 'confidential' | 'public'
    redirect_uris: Mapped[str] = mapped_column(String, nullable=False, default="[]")  # JSON array
    allowed_scopes: Mapped[str] = mapped_column(String, nullable=False, default="[]")  # JSON array
    grant_types: Mapped[str] = mapped_column(
        String, nullable=False, default='["authorization_code","refresh_token"]'
    )
    # Per-client access token TTL in seconds; NULL (or 0) => the 1h default.
    # Honored by ALL grant types and /_admin/issue_token (unless an explicit
    # expires_in overrides it there).
    access_token_ttl: Mapped[int | None] = mapped_column(Integer, nullable=True, default=None)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[str] = mapped_column(String, default=utcnow_iso)

    # -- JSON helpers (columns store JSON arrays as TEXT per the spec SQL) --
    @property
    def redirect_uri_list(self) -> list[str]:
        return json.loads(self.redirect_uris or "[]")

    @property
    def allowed_scope_list(self) -> list[str]:
        return json.loads(self.allowed_scopes or "[]")

    @property
    def grant_type_list(self) -> list[str]:
        return json.loads(self.grant_types or "[]")
