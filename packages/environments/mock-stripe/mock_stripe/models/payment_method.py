"""PaymentMethod model (`pm_`)."""

from __future__ import annotations

from sqlalchemy import Boolean, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, next_seq


class PaymentMethod(Base):
    __tablename__ = "payment_methods"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    type: Mapped[str] = mapped_column(String, default="card")
    customer_id: Mapped[str | None] = mapped_column(String, nullable=True)
    # Card details (present when type == "card")
    card_brand: Mapped[str | None] = mapped_column(String, nullable=True)
    card_last4: Mapped[str | None] = mapped_column(String, nullable=True)
    card_exp_month: Mapped[int | None] = mapped_column(Integer, nullable=True)
    card_exp_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    card_fingerprint: Mapped[str | None] = mapped_column(String, nullable=True)
    card_funding: Mapped[str | None] = mapped_column(String, nullable=True)
    card_country: Mapped[str | None] = mapped_column(String, nullable=True)
    card_cvc_check: Mapped[str | None] = mapped_column(String, nullable=True)
    billing_details_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")
    # Test-card decline behavior, applied when this PM is used to confirm a PI.
    # e.g. failure_code="card_declined", decline_code="generic_decline"
    failure_code: Mapped[str | None] = mapped_column(String, nullable=True)
    decline_code: Mapped[str | None] = mapped_column(String, nullable=True)
    failure_message: Mapped[str | None] = mapped_column(String, nullable=True)
    # 3DS/SCA test cards (pm_card_authenticationRequired, 4000002760003184, ...):
    # confirming a PI with this PM yields status=requires_action + next_action.
    authentication_required: Mapped[bool] = mapped_column(Boolean, default=False)
    created: Mapped[int] = mapped_column(Integer, default=0)
    seq: Mapped[int] = mapped_column(Integer, default=next_seq)
