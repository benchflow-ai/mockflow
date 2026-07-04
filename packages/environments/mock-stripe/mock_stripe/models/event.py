"""Event model (`evt_`). Every mutation records an event."""

from __future__ import annotations

from sqlalchemy import Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, next_seq


class Event(Base):
    __tablename__ = "events"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    type: Mapped[str] = mapped_column(String, nullable=False)
    api_version: Mapped[str] = mapped_column(String, default="2026-05-27.dahlia")
    data_json: Mapped[str] = mapped_column(Text, nullable=False)  # {"object": {...}}
    request_idempotency_key: Mapped[str | None] = mapped_column(String, nullable=True)
    created: Mapped[int] = mapped_column(Integer, default=0)
    seq: Mapped[int] = mapped_column(Integer, default=next_seq)
