"""BalanceTransaction model (`txn_`)."""

from __future__ import annotations

from sqlalchemy import Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, next_seq


class BalanceTransaction(Base):
    __tablename__ = "balance_transactions"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    amount: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(String, nullable=False)
    fee: Mapped[int] = mapped_column(Integer, default=0)
    net: Mapped[int] = mapped_column(Integer, nullable=False)
    type: Mapped[str] = mapped_column(String, nullable=False)  # charge|refund
    reporting_category: Mapped[str] = mapped_column(String, nullable=False)
    source_id: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, default="available")
    description: Mapped[str | None] = mapped_column(String, nullable=True)
    fee_details_json: Mapped[str] = mapped_column(Text, default="[]")
    available_on: Mapped[int] = mapped_column(Integer, default=0)
    created: Mapped[int] = mapped_column(Integer, default=0)
    seq: Mapped[int] = mapped_column(Integer, default=next_seq)
