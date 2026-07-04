"""stripe task seeder for stripe-refund-correct-customer.

Discovered by ``mock_stripe.seed.generator`` via
``--scenario task:stripe-refund-correct-customer`` (it looks for this file at
``<TASKS_DIR>/<task>/data/stripe_seed.py`` and calls ``seed(db, rng, fake)``).
The default API key (``sk_test_env_0_51deterministic``) is already added by the
scenario wrapper before ``seed`` runs - do NOT re-seed it here.

This reuses the exact construction helpers the built-in ``default`` scenario
uses (``_make_customer`` / ``_make_attached_card`` / ``_make_succeeded_payment``)
so the seeded customers, payment methods, payment intents, charges, balance
transactions and events are byte-for-byte faithful to a real Stripe account.

The three customers + amounts are defined in the sibling ``needles.py`` manifest
so the evaluator can resolve them without importing the environment package.
"""

from __future__ import annotations

import importlib.util
import pathlib


def _load_needles():
    here = pathlib.Path(__file__).resolve().parent
    spec = importlib.util.spec_from_file_location(
        "stripe_refund_correct_customer_needles", here / "needles.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def seed(db, rng, fake) -> dict:
    # Imported lazily so the manifest module (needles.py) stays free of any
    # mock_stripe dependency for the evaluator's sake.
    from mock_stripe.seed.generator import (
        ANCHOR,
        _DAY,
        _make_attached_card,
        _make_customer,
        _make_succeeded_payment,
    )

    needles = _load_needles()

    for entry in needles.ALL:
        created = ANCHOR - entry["days_ago"] * _DAY
        customer = _make_customer(
            db, rng, fake,
            name=entry["customer_name"],
            email=entry["customer_email"],
            created=created,
        )
        pm = _make_attached_card(db, rng, customer, entry["card_number"], created)
        _make_succeeded_payment(
            db, rng, customer, pm,
            amount=entry["amount"],
            description=entry["description"],
            created=created,
            captured=True,
        )

    return {
        "customers": len(needles.ALL),
        "payment_methods": len(needles.ALL),
        "payment_intents": len(needles.ALL),
        "charges": len(needles.ALL),
        "refunds": 0,
    }
