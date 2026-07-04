"""Product (`prod_`) and Price (`price_`) models."""

from __future__ import annotations

from sqlalchemy import Boolean, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, next_seq


class Product(Base):
    __tablename__ = "products"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    description: Mapped[str | None] = mapped_column(String, nullable=True)
    default_price_id: Mapped[str | None] = mapped_column(String, nullable=True)
    url: Mapped[str | None] = mapped_column(String, nullable=True)
    unit_label: Mapped[str | None] = mapped_column(String, nullable=True)
    statement_descriptor: Mapped[str | None] = mapped_column(String, nullable=True)
    shippable: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    images_json: Mapped[str] = mapped_column(Text, default="[]")
    marketing_features_json: Mapped[str] = mapped_column(Text, default="[]")
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")
    created: Mapped[int] = mapped_column(Integer, default=0)
    updated: Mapped[int] = mapped_column(Integer, default=0)
    seq: Mapped[int] = mapped_column(Integer, default=next_seq)


class Price(Base):
    __tablename__ = "prices"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    product_id: Mapped[str] = mapped_column(String, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    currency: Mapped[str] = mapped_column(String, nullable=False)
    unit_amount: Mapped[int | None] = mapped_column(Integer, nullable=True)
    unit_amount_decimal: Mapped[str | None] = mapped_column(String, nullable=True)
    type: Mapped[str] = mapped_column(String, default="one_time")  # one_time|recurring
    billing_scheme: Mapped[str] = mapped_column(String, default="per_unit")
    tax_behavior: Mapped[str] = mapped_column(String, default="unspecified")
    nickname: Mapped[str | None] = mapped_column(String, nullable=True)
    lookup_key: Mapped[str | None] = mapped_column(String, nullable=True)
    recurring_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")
    created: Mapped[int] = mapped_column(Integer, default=0)
    seq: Mapped[int] = mapped_column(Integer, default=next_seq)
