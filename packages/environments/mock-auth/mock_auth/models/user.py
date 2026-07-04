"""User model — identities shared across all environment services."""

from __future__ import annotations

from sqlalchemy import Boolean, String
from sqlalchemy.orm import Mapped, mapped_column

from mock_auth.models.base import Base, utcnow_iso


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    email: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String, nullable=False)
    given_name: Mapped[str] = mapped_column(String, default="")
    family_name: Mapped[str] = mapped_column(String, default="")
    picture_url: Mapped[str] = mapped_column(String, default="")
    password_hash: Mapped[str] = mapped_column(String, nullable=False)  # bcrypt; consent screen login
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[str] = mapped_column(String, default=utcnow_iso)
    updated_at: Mapped[str] = mapped_column(String, default=utcnow_iso)
