"""Seed data for the stripe-decline-handling task.

Loaded by stripe's ``task:<name>`` scenario, which calls
``seed(db, rng, fake)`` *after* the default API key has already been seeded.
Mirrors the way the default scenario builds customers + attached cards (+events),
but plants the decline-handling setup:

  * one ``renewal_target`` customer whose card-on-file
    (``invoice_settings.default_payment_method``) is a seeded *declining* card
    (insufficient_funds — number 4000000000009995), plus a second attached
    *working* backup card the agent is meant to fall back to.
  * several decoy customers — including a deliberately name-confusable
    "Northwind Logistics Inc." — that must NOT be charged.

Object roles live in ``metadata.env_0_role`` so the evaluator can resolve every
id from ``/_admin/state`` without hardcoding a single Stripe id (ids are
RNG-generated and change with ``--seed``).

The constants below are the source of truth; ``data/needles.py`` mirrors the
subset the evaluator needs (kept dependency-free for unit tests).
"""

from __future__ import annotations

import json

from mock_stripe import testcards
from mock_stripe.api.serializers import customer_to_dict, payment_method_to_dict
from mock_stripe.ids import generate_id
from mock_stripe.models import Customer, Event, PaymentMethod

# --- Source-of-truth constants (mirrored in needles.py) ---------------------
TARGET_NAME = "Northwind Trading Co."
TARGET_EMAIL = "ap@northwindtrading.com"
RENEWAL_AMOUNT = 4800  # $48.00 annual renewal, in cents

DECLINE_CARD_NUMBER = "4000000000009995"  # card_declined / insufficient_funds
BACKUP_CARD_NUMBER = "4242424242424242"   # visa, succeeds

# Decoy customers (must NOT be charged). The first is a name-confusable trap.
DECOYS = [
    ("Northwind Logistics Inc.", "ar@northwind-logistics.com", "5555555555554444"),
    ("Summit Outdoors LLC", "ap@summitoutdoors.com", "378282246310005"),
    ("Cedar & Pine Co.", "billing@cedarandpine.com", "6011111111111117"),
]

# Fixed anchor so seeded `created` timestamps are deterministic.
ANCHOR = 1_780_000_000
_DAY = 86_400
API_VERSION = "2026-05-27.dahlia"


def _event(db, rng, event_type: str, obj: dict, created: int) -> None:
    db.add(Event(
        id=generate_id("evt", rng=rng),
        type=event_type,
        api_version=API_VERSION,
        data_json=json.dumps({"object": obj}),
        request_idempotency_key=None,
        created=created,
    ))


def _customer(db, rng, *, name, email, metadata, created) -> Customer:
    c = Customer(
        id=generate_id("cus", rng=rng),
        name=name,
        email=email,
        phone=None,
        description=None,
        invoice_prefix="".join(rng.choice("ABCDEFGH0123456789") for _ in range(8)),
        metadata_json=json.dumps(metadata),
        created=created,
    )
    db.add(c)
    _event(db, rng, "customer.created", customer_to_dict(c), created)
    return c


def _card(db, rng, customer, number, *, metadata, created) -> PaymentMethod:
    spec = testcards.spec_for_number(number)
    pm = PaymentMethod(
        id=generate_id("pm", rng=rng),
        type="card",
        customer_id=customer.id,
        card_brand=spec["brand"],
        card_last4=spec["last4"],
        card_exp_month=rng.randint(1, 12),
        card_exp_year=rng.randint(2030, 2036),
        card_fingerprint=spec["fingerprint"],
        card_funding=spec["funding"],
        card_country=spec["country"],
        card_cvc_check="pass",
        # Decline behavior is carried by the seeded card itself, so confirming a
        # PI with it reproduces a real 402 + last_payment_error.
        failure_code=spec["failure_code"],
        decline_code=spec["decline_code"],
        failure_message=spec["failure_message"],
        authentication_required=spec["authentication_required"],
        metadata_json=json.dumps(metadata),
        created=created,
    )
    db.add(pm)
    _event(db, rng, "payment_method.attached", payment_method_to_dict(pm), created)
    return pm


def seed(db, rng, fake) -> dict:
    created = ANCHOR - 20 * _DAY

    target = _customer(
        db, rng,
        name=TARGET_NAME, email=TARGET_EMAIL,
        metadata={"env_0_role": "renewal_target", "account_ref": "NW-4821"},
        created=created,
    )
    declining = _card(
        db, rng, target, DECLINE_CARD_NUMBER,
        metadata={"env_0_role": "primary_declines", "note": "card on file"},
        created=created,
    )
    _card(
        db, rng, target, BACKUP_CARD_NUMBER,
        metadata={"env_0_role": "backup_works", "note": "backup card"},
        created=created + 60,
    )
    # The declining card is the customer's "card on file".
    target.default_payment_method = declining.id

    for i, (name, email, number) in enumerate(DECOYS):
        decoy = _customer(
            db, rng,
            name=name, email=email,
            metadata={"env_0_role": "decoy"},
            created=created + (i + 1) * _DAY,
        )
        _card(
            db, rng, decoy, number,
            metadata={"env_0_role": "decoy_card"},
            created=created + (i + 1) * _DAY,
        )

    return {
        "customers": 1 + len(DECOYS),
        "payment_methods": 2 + len(DECOYS),
        "renewal_target_email": TARGET_EMAIL,
    }
