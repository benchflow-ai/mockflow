"""Balance ledger helpers: Stripe's standard test fee model + balance txns.

Fee model (documented in API_NOTES.md): fee = round_half_up(2.9% of amount) + 30c
on captured charges; refunds carry no fee and a negative amount.
"""

from __future__ import annotations

import json
import time

from sqlalchemy.orm import Session

from mock_stripe.ids import generate_id
from mock_stripe.models import BalanceTransaction


def fee_for_charge(amount: int) -> int:
    """2.9% + 30c, half-up integer rounding in cents."""
    return (amount * 29 + 500) // 1000 + 30


def create_charge_balance_transaction(
    db: Session,
    *,
    charge_id: str,
    amount: int,
    currency: str,
    created: int | None = None,
    rng=None,
) -> BalanceTransaction:
    fee = fee_for_charge(amount)
    created = created if created is not None else int(time.time())
    txn = BalanceTransaction(
        id=generate_id("txn", rng=rng),
        amount=amount,
        currency=currency,
        fee=fee,
        net=amount - fee,
        type="charge",
        reporting_category="charge",
        source_id=charge_id,
        status="available",
        description=None,
        fee_details_json=json.dumps(
            [
                {
                    "amount": fee,
                    "application": None,
                    "currency": currency,
                    "description": "Stripe processing fees",
                    "type": "stripe_fee",
                }
            ]
        ),
        available_on=created,
        created=created,
    )
    db.add(txn)
    return txn


def create_refund_balance_transaction(
    db: Session,
    *,
    refund_id: str,
    amount: int,
    currency: str,
    created: int | None = None,
    rng=None,
) -> BalanceTransaction:
    created = created if created is not None else int(time.time())
    txn = BalanceTransaction(
        id=generate_id("txn", rng=rng),
        amount=-amount,
        currency=currency,
        fee=0,
        net=-amount,
        type="refund",
        reporting_category="refund",
        source_id=refund_id,
        status="available",
        description=None,
        fee_details_json="[]",
        available_on=created,
        created=created,
    )
    db.add(txn)
    return txn
