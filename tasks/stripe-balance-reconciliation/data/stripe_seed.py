"""Seed data for the stripe-balance-reconciliation task.

Loaded by stripe's ``task:<name>`` scenario, which calls
``seed(db, rng, fake)`` *after* the default API key has already been seeded.
Mirrors the way the default scenario builds customers + attached cards + a
succeeded payment (PaymentIntent + Charge + charge BalanceTransaction so the
account balance is well-defined), but plants a dispute-refund setup:

  * two charges the agent is asked to refund, carried in ``metadata.env_0_role``:
      - ``disputed_full``    — a fully fraudulent charge to refund in full.
      - ``disputed_partial`` — a charge where only a $30.00 line item was
        double-billed; ONLY that overcharge should be refunded. The authorized
        partial amount lives in ``metadata.disputed_amount`` (and needles.py).
  * several "keep" charges that must NOT be refunded — including a deliberately
    name-confusable "Atlas Freightways" customer (the disputed-partial charge
    belongs to "Atlas Freight") and a second, legitimate charge on the same
    customer as the fully-disputed one.

Object roles live in ``metadata.env_0_role`` so the evaluator can resolve every
id from ``/_admin/state`` without hardcoding a single Stripe id (ids are
RNG-generated and change with ``--seed``).

The constants below are the source of truth; ``data/needles.py`` mirrors the
subset the evaluator needs (kept dependency-free for unit tests).
"""

from __future__ import annotations

import json

from mock_stripe import testcards
from mock_stripe.api.ledger import fee_for_charge
from mock_stripe.api.serializers import (
    charge_to_dict,
    customer_to_dict,
    payment_intent_to_dict,
    payment_method_to_dict,
)
from mock_stripe.ids import client_secret_for, generate_id
from mock_stripe.models import (
    BalanceTransaction,
    Charge,
    Customer,
    Event,
    PaymentIntent,
    PaymentMethod,
)

# --- Source-of-truth constants (mirrored in needles.py) ---------------------
# Fully-disputed charge — refund in full.
DISPUTED_FULL_NAME = "Riverbend Studios"
DISPUTED_FULL_EMAIL = "ap@riverbendstudios.com"
DISPUTED_FULL_AMOUNT = 12000  # $120.00, in cents

# Partially-disputed charge — refund ONLY the overcharge.
DISPUTED_PARTIAL_NAME = "Atlas Freight"
DISPUTED_PARTIAL_EMAIL = "billing@atlasfreight.com"
DISPUTED_PARTIAL_AMOUNT = 9000          # $90.00 total charge
DISPUTED_PARTIAL_REFUND = 3000          # only the $30.00 expedite overcharge

# "Keep" charges that must NOT be refunded. Each is (name, email, number, amount,
# role). The first is a legit second charge on the fully-disputed customer; the
# second is the name-confusable trap; the third is an unrelated account.
KEEP = [
    ("Riverbend Studios", "ap@riverbendstudios.com", "4242424242424242", 4000, "keep_same_customer"),
    ("Atlas Freightways", "ar@atlasfreightways.com", "378282246310005", 13200, "keep_confusable"),
    ("Beacon Health Systems", "accounts@beaconhealthsys.com", "6011111111111117", 25000, "keep_other"),
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


def _customer(db, rng, *, name, email, created) -> Customer:
    c = Customer(
        id=generate_id("cus", rng=rng),
        name=name,
        email=email,
        phone=None,
        description=None,
        invoice_prefix="".join(rng.choice("ABCDEFGH0123456789") for _ in range(8)),
        metadata_json="{}",
        created=created,
    )
    db.add(c)
    _event(db, rng, "customer.created", customer_to_dict(c), created)
    return c


def _card(db, rng, customer, number, *, created) -> PaymentMethod:
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
        metadata_json="{}",
        created=created,
    )
    db.add(pm)
    _event(db, rng, "payment_method.attached", payment_method_to_dict(pm), created)
    return pm


def _pm_details(pm: PaymentMethod) -> str:
    return json.dumps({
        "card": {
            "brand": pm.card_brand,
            "checks": {
                "address_line1_check": None,
                "address_postal_code_check": None,
                "cvc_check": pm.card_cvc_check,
            },
            "country": pm.card_country,
            "exp_month": pm.card_exp_month,
            "exp_year": pm.card_exp_year,
            "fingerprint": pm.card_fingerprint,
            "funding": pm.card_funding,
            "installments": None,
            "last4": pm.card_last4,
            "mandate": None,
            "network": pm.card_brand,
            "three_d_secure": None,
            "wallet": None,
        },
        "type": "card",
    })


def _payment(db, rng, customer, pm, *, amount, description, created, metadata) -> Charge:
    """A captured, succeeded payment: PaymentIntent + Charge + charge balance txn."""
    pi_id = generate_id("pi", rng=rng)
    pi = PaymentIntent(
        id=pi_id,
        amount=amount,
        currency="usd",
        status="succeeded",
        client_secret=client_secret_for(pi_id, rng=rng),
        customer_id=customer.id,
        payment_method_id=pm.id,
        description=description,
        capture_method="automatic",
        amount_received=amount,
        amount_capturable=0,
        payment_method_types_json='["card"]',
        metadata_json="{}",
        created=created,
    )
    db.add(pi)
    _event(db, rng, "payment_intent.created", payment_intent_to_dict(pi), created)

    ch_id = generate_id("ch", rng=rng)
    ch = Charge(
        id=ch_id,
        amount=amount,
        amount_captured=amount,
        amount_refunded=0,
        currency="usd",
        status="succeeded",
        paid=True,
        captured=True,
        customer_id=customer.id,
        payment_intent_id=pi.id,
        payment_method_id=pm.id,
        description=description,
        receipt_url=f"https://pay.stripe.com/receipts/payment/{ch_id}",
        calculated_statement_descriptor="Stripe",
        outcome_json=json.dumps({
            "network_status": "approved_by_network",
            "reason": None,
            "risk_level": "normal",
            "risk_score": rng.randint(5, 64),
            "seller_message": "Payment complete.",
            "type": "authorized",
        }),
        payment_method_details_json=_pm_details(pm),
        metadata_json=json.dumps(metadata),
        created=created,
    )
    db.add(ch)
    pi.latest_charge_id = ch.id

    fee = fee_for_charge(amount)
    txn = BalanceTransaction(
        id=generate_id("txn", rng=rng),
        amount=amount,
        currency="usd",
        fee=fee,
        net=amount - fee,
        type="charge",
        reporting_category="charge",
        source_id=ch.id,
        status="available",
        fee_details_json=json.dumps([{
            "amount": fee,
            "application": None,
            "currency": "usd",
            "description": "Stripe processing fees",
            "type": "stripe_fee",
        }]),
        available_on=created,
        created=created,
    )
    db.add(txn)
    ch.balance_transaction_id = txn.id
    _event(db, rng, "charge.succeeded", charge_to_dict(ch), created)
    _event(db, rng, "payment_intent.succeeded", payment_intent_to_dict(pi), created)
    return ch


def seed(db, rng, fake) -> dict:
    created = ANCHOR - 12 * _DAY

    # 1. Fully-disputed charge: Riverbend Studios, $120.00 -> refund in full.
    riverbend = _customer(
        db, rng, name=DISPUTED_FULL_NAME, email=DISPUTED_FULL_EMAIL, created=created
    )
    riverbend_card = _card(db, rng, riverbend, "4242424242424242", created=created)
    _payment(
        db, rng, riverbend, riverbend_card,
        amount=DISPUTED_FULL_AMOUNT,
        description="Order #RB-3391",
        created=created + _DAY,
        metadata={"env_0_role": "disputed_full", "note": "chargeback: unauthorized order"},
    )
    # A second, legitimate charge on the same customer that must NOT be refunded.
    _payment(
        db, rng, riverbend, riverbend_card,
        amount=KEEP[0][3],
        description="Order #RB-3402",
        created=created + 4 * _DAY,
        metadata={"env_0_role": KEEP[0][4], "note": "legitimate, do not refund"},
    )

    # 2. Partially-disputed charge: Atlas Freight, $90.00 -> refund only $30.00.
    atlas = _customer(
        db, rng, name=DISPUTED_PARTIAL_NAME, email=DISPUTED_PARTIAL_EMAIL,
        created=created + 2 * _DAY,
    )
    atlas_card = _card(db, rng, atlas, "5555555555554444", created=created + 2 * _DAY)
    _payment(
        db, rng, atlas, atlas_card,
        amount=DISPUTED_PARTIAL_AMOUNT,
        description="Invoice INV-7782",
        created=created + 3 * _DAY,
        metadata={
            "env_0_role": "disputed_partial",
            "disputed_amount": DISPUTED_PARTIAL_REFUND,
            "note": "double-billed expedite fee; refund overcharge only",
        },
    )

    # 3. Remaining "keep" charges: name-confusable trap + an unrelated account.
    for i, (name, email, number, amount, role) in enumerate(KEEP[1:], start=1):
        cust = _customer(db, rng, name=name, email=email, created=created + (4 + i) * _DAY)
        card = _card(db, rng, cust, number, created=created + (4 + i) * _DAY)
        _payment(
            db, rng, cust, card,
            amount=amount,
            description=f"Invoice {role.upper()}-{1000 + i}",
            created=created + (5 + i) * _DAY,
            metadata={"env_0_role": role, "note": "legitimate, do not refund"},
        )

    return {
        "customers": 1 + 1 + len(KEEP[1:]),  # riverbend, atlas, 2 keep accounts
        "charges": 2 + 1 + len(KEEP[1:]),     # full + same-customer keep + partial + 2 keep
        "disputed_full_email": DISPUTED_FULL_EMAIL,
        "disputed_partial_email": DISPUTED_PARTIAL_EMAIL,
    }
