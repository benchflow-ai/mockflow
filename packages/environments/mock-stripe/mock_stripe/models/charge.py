"""Charge model (`ch_`)."""

from __future__ import annotations

from sqlalchemy import Boolean, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, next_seq


class Charge(Base):
    __tablename__ = "charges"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    amount: Mapped[int] = mapped_column(Integer, nullable=False)
    amount_captured: Mapped[int] = mapped_column(Integer, default=0)
    amount_refunded: Mapped[int] = mapped_column(Integer, default=0)
    currency: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, default="succeeded")  # succeeded|pending|failed
    paid: Mapped[bool] = mapped_column(Boolean, default=True)
    captured: Mapped[bool] = mapped_column(Boolean, default=True)
    refunded: Mapped[bool] = mapped_column(Boolean, default=False)
    disputed: Mapped[bool] = mapped_column(Boolean, default=False)
    customer_id: Mapped[str | None] = mapped_column(String, nullable=True)
    payment_intent_id: Mapped[str | None] = mapped_column(String, nullable=True)
    payment_method_id: Mapped[str | None] = mapped_column(String, nullable=True)
    balance_transaction_id: Mapped[str | None] = mapped_column(String, nullable=True)
    description: Mapped[str | None] = mapped_column(String, nullable=True)
    receipt_email: Mapped[str | None] = mapped_column(String, nullable=True)
    receipt_url: Mapped[str | None] = mapped_column(String, nullable=True)
    failure_code: Mapped[str | None] = mapped_column(String, nullable=True)
    failure_message: Mapped[str | None] = mapped_column(String, nullable=True)
    calculated_statement_descriptor: Mapped[str | None] = mapped_column(String, nullable=True)
    statement_descriptor: Mapped[str | None] = mapped_column(String, nullable=True)
    statement_descriptor_suffix: Mapped[str | None] = mapped_column(String, nullable=True)
    outcome_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    payment_method_details_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    billing_details_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")
    created: Mapped[int] = mapped_column(Integer, default=0)
    seq: Mapped[int] = mapped_column(Integer, default=next_seq)
