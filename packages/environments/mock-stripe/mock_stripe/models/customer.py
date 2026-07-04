"""Customer model (`cus_`)."""

from __future__ import annotations

from sqlalchemy import Boolean, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, next_seq


class Customer(Base):
    __tablename__ = "customers"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    email: Mapped[str | None] = mapped_column(String, nullable=True)
    name: Mapped[str | None] = mapped_column(String, nullable=True)
    description: Mapped[str | None] = mapped_column(String, nullable=True)
    phone: Mapped[str | None] = mapped_column(String, nullable=True)
    balance: Mapped[int] = mapped_column(Integer, default=0)
    currency: Mapped[str | None] = mapped_column(String, nullable=True)
    delinquent: Mapped[bool] = mapped_column(Boolean, default=False)
    invoice_prefix: Mapped[str] = mapped_column(String, default="")
    next_invoice_sequence: Mapped[int] = mapped_column(Integer, default=1)
    default_source: Mapped[str | None] = mapped_column(String, nullable=True)
    default_payment_method: Mapped[str | None] = mapped_column(String, nullable=True)
    tax_exempt: Mapped[str] = mapped_column(String, default="none")
    address_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    shipping_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    preferred_locales_json: Mapped[str] = mapped_column(Text, default="[]")
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")
    deleted: Mapped[bool] = mapped_column(Boolean, default=False)
    created: Mapped[int] = mapped_column(Integer, default=0)
    seq: Mapped[int] = mapped_column(Integer, default=next_seq)
