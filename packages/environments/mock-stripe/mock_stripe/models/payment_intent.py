"""PaymentIntent model (`pi_`)."""

from __future__ import annotations

from sqlalchemy import Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, next_seq


class PaymentIntent(Base):
    __tablename__ = "payment_intents"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    amount: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, default="requires_payment_method")
    client_secret: Mapped[str] = mapped_column(String, nullable=False)
    customer_id: Mapped[str | None] = mapped_column(String, nullable=True)
    payment_method_id: Mapped[str | None] = mapped_column(String, nullable=True)
    latest_charge_id: Mapped[str | None] = mapped_column(String, nullable=True)
    description: Mapped[str | None] = mapped_column(String, nullable=True)
    receipt_email: Mapped[str | None] = mapped_column(String, nullable=True)
    capture_method: Mapped[str] = mapped_column(String, default="automatic")
    confirmation_method: Mapped[str] = mapped_column(String, default="automatic")
    amount_capturable: Mapped[int] = mapped_column(Integer, default=0)
    amount_received: Mapped[int] = mapped_column(Integer, default=0)
    canceled_at: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cancellation_reason: Mapped[str | None] = mapped_column(String, nullable=True)
    setup_future_usage: Mapped[str | None] = mapped_column(String, nullable=True)
    statement_descriptor: Mapped[str | None] = mapped_column(String, nullable=True)
    statement_descriptor_suffix: Mapped[str | None] = mapped_column(String, nullable=True)
    automatic_payment_methods_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    payment_method_types_json: Mapped[str] = mapped_column(Text, default='["card"]')
    last_payment_error_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Populated while status == "requires_action" (3DS/SCA), null otherwise.
    next_action_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    shipping_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")
    created: Mapped[int] = mapped_column(Integer, default=0)
    seq: Mapped[int] = mapped_column(Integer, default=next_seq)
