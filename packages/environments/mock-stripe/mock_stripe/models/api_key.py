"""API key model. Keys are seeded; requests must present one via Bearer/Basic auth."""

from __future__ import annotations

from sqlalchemy import Boolean, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, next_seq


class ApiKey(Base):
    __tablename__ = "api_keys"

    # The secret key string itself ("sk_test_...") is the primary key.
    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, default="default")
    livemode: Mapped[bool] = mapped_column(Boolean, default=False)
    created: Mapped[int] = mapped_column(Integer, default=0)
    seq: Mapped[int] = mapped_column(Integer, default=next_seq)
