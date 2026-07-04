"""SQLAlchemy models for stripe."""

from __future__ import annotations

from .base import (
    Base,
    DEFAULT_DB_PATH,
    get_engine,
    get_session_factory,
    init_db,
    next_seq,
    reset_engine,
    resolve_db_path,
)
from .api_key import ApiKey
from .balance_transaction import BalanceTransaction
from .charge import Charge
from .customer import Customer
from .event import Event
from .idempotency import IdempotencyRecord
from .payment_intent import PaymentIntent
from .payment_method import PaymentMethod
from .product import Price, Product
from .refund import Refund
from .webhook import WebhookDelivery, WebhookEndpoint

# Order matters for snapshot restore (no FKs between these tables, but keep stable).
MODEL_REGISTRY: list[tuple[str, type[Base]]] = [
    ("api_keys", ApiKey),
    ("customers", Customer),
    ("payment_methods", PaymentMethod),
    ("products", Product),
    ("prices", Price),
    ("payment_intents", PaymentIntent),
    ("charges", Charge),
    ("refunds", Refund),
    ("balance_transactions", BalanceTransaction),
    ("events", Event),
    ("idempotency_records", IdempotencyRecord),
    ("webhook_endpoints", WebhookEndpoint),
    ("webhook_deliveries", WebhookDelivery),
]

__all__ = [
    "ApiKey",
    "BalanceTransaction",
    "Base",
    "Charge",
    "Customer",
    "DEFAULT_DB_PATH",
    "Event",
    "IdempotencyRecord",
    "MODEL_REGISTRY",
    "PaymentIntent",
    "PaymentMethod",
    "Price",
    "Product",
    "Refund",
    "WebhookDelivery",
    "WebhookEndpoint",
    "get_engine",
    "get_session_factory",
    "init_db",
    "next_seq",
    "reset_engine",
    "resolve_db_path",
]
