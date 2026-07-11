"""stripe ``task:stripe-idempotent-no-double-charge`` seeder.

Discovered by ``mock_stripe.seed.generator`` because this file exists at
``tasks/<name>/data/stripe_seed.py`` and exposes ``seed(db, rng, fake) -> dict``.
The default ``sk_test_env_0_51deterministic`` API key is seeded by the generator
before this runs.

What it builds (all amounts in cents):
  * Dana Whitfield + a visa on file, with ONE already-succeeded, captured
    charge for order #1234 (amount 4999, ``metadata.order_id == "1234"``).
    This is "the previous attempt that already went through."
  * Dana also has one unrelated older charge (order #1102, amount 12800).
  * Two decoy customers, each with a single succeeded charge for a
    close-but-wrong order number (1230 / 1233).

Ground truth lives in ``data/needles.py`` (loaded relative to this file so the
seeder and the evaluator agree).
"""

from __future__ import annotations

import importlib.util
import json
import os

from mock_stripe.seed.generator import (
    ANCHOR,
    _DAY,
    _make_attached_card,
    _make_customer,
    _make_succeeded_payment,
)


def _load_needles():
    here = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(here, "needles.py")
    spec = importlib.util.spec_from_file_location(
        "stripe_idem_needles", path
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _tag_order(pi, ch, order_id: str) -> None:
    """Stamp metadata.order_id onto a payment intent and its charge.

    Real Stripe stores metadata values as strings; a charge created by
    confirming a PI inherits the PI's metadata, so we set both to match what an
    agent's own confirm flow would produce.
    """
    meta = json.dumps({"order_id": str(order_id)})
    pi.metadata_json = meta
    ch.metadata_json = meta


def seed(db, rng, fake) -> dict:
    n = _load_needles()

    # --- Target customer: Dana, with a card on file -----------------------
    dana_created = ANCHOR - 40 * _DAY
    dana = _make_customer(
        db, rng, fake,
        name=n.TARGET_CUSTOMER["name"],
        email=n.TARGET_CUSTOMER["email"],
        created=dana_created,
    )
    dana_card = _make_attached_card(
        db, rng, dana, n.TARGET_CUSTOMER["card"], dana_created
    )
    dana.default_payment_method = dana_card.id

    # The already-succeeded charge for order #1234 (the previous attempt).
    order_pi, order_ch = _make_succeeded_payment(
        db, rng, dana, dana_card,
        amount=n.ORDER_AMOUNT,
        description=n.ORDER_DESCRIPTION,
        created=ANCHOR - n.ORDER_DAYS_AGO * _DAY,
        captured=True,
    )
    _tag_order(order_pi, order_ch, n.ORDER_ID)

    # Dana's unrelated older charges (different order, different amount).
    for spec in n.TARGET_OTHER_CHARGES:
        pi, ch = _make_succeeded_payment(
            db, rng, dana, dana_card,
            amount=spec["amount"],
            description=spec["description"],
            created=ANCHOR - spec["days_ago"] * _DAY,
            captured=True,
        )
        _tag_order(pi, ch, spec["order_id"])

    # --- Decoy customers, each with one succeeded charge ------------------
    n_decoys = 0
    for spec in n.DECOY_CUSTOMERS:
        created = ANCHOR - (spec["days_ago"] + 30) * _DAY
        cust = _make_customer(
            db, rng, fake,
            name=spec["name"], email=spec["email"], created=created,
        )
        card = _make_attached_card(db, rng, cust, spec["card"], created)
        cust.default_payment_method = card.id
        pi, ch = _make_succeeded_payment(
            db, rng, cust, card,
            amount=spec["amount"],
            description=spec["description"],
            created=ANCHOR - spec["days_ago"] * _DAY,
            captured=True,
        )
        _tag_order(pi, ch, spec["order_id"])
        n_decoys += 1

    return {
        "customers": 1 + n_decoys,
        "target_customer": n.TARGET_CUSTOMER["email"],
        "order_id": n.ORDER_ID,
        "order_amount": n.ORDER_AMOUNT,
        "seeded_order_charges": 1,
    }
