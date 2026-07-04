"""PaymentMethod creation/materialization shared by routers.

Canonical test tokens (pm_card_visa, pm_card_chargeDeclined, ...) are
"virtual": they can be referenced anywhere a payment method is expected
without prior creation. Like real Stripe, each reference materializes a fresh
concrete `pm_...` object.
"""

from __future__ import annotations

import json
import time

from sqlalchemy.orm import Session

from mock_stripe import testcards
from mock_stripe.ids import generate_id
from mock_stripe.models import PaymentMethod

from .errors import StripeError, resource_missing


def create_pm_from_spec(
    db: Session,
    spec: dict,
    *,
    exp_month: int = 12,
    exp_year: int = 2034,
    cvc_check: str | None = None,
    billing_details: dict | None = None,
    metadata: dict | None = None,
    customer_id: str | None = None,
    created: int | None = None,
    rng=None,
) -> PaymentMethod:
    pm = PaymentMethod(
        id=generate_id("pm", rng=rng),
        type="card",
        customer_id=customer_id,
        card_brand=spec["brand"],
        card_last4=spec["last4"],
        card_exp_month=exp_month,
        card_exp_year=exp_year,
        card_fingerprint=spec["fingerprint"],
        card_funding=spec["funding"],
        card_country=spec["country"],
        card_cvc_check=cvc_check,
        billing_details_json=json.dumps(billing_details) if billing_details else None,
        metadata_json=json.dumps(metadata or {}),
        failure_code=spec.get("failure_code"),
        decline_code=spec.get("decline_code"),
        failure_message=spec.get("failure_message"),
        authentication_required=bool(spec.get("authentication_required")),
        created=created if created is not None else int(time.time()),
    )
    db.add(pm)
    return pm


def resolve_payment_method(db: Session, pm_id: str, *, param: str = "payment_method") -> PaymentMethod:
    """Resolve a pm id, materializing virtual test tokens; 404-style error if unknown."""
    if testcards.is_virtual_pm(pm_id):
        spec = testcards.spec_for_token(pm_id)
        pm = create_pm_from_spec(db, spec)
        db.flush()
        return pm
    pm = db.get(PaymentMethod, pm_id)
    if pm is None:
        raise resource_missing("PaymentMethod", pm_id)
    return pm


def card_data_to_spec(card: dict) -> dict:
    """Build a card spec from card[number]/card[token] create params."""
    token = card.get("token")
    if token:
        spec = testcards.spec_for_token(token)
        if spec is None:
            raise StripeError(400, f"No such token: '{token}'", code="resource_missing", param="card[token]")
        return spec
    number = str(card.get("number") or "").replace(" ", "")
    if not number:
        # Lenient default (documented): no card data -> 4242 visa test card.
        number = "4242424242424242"
    if number == testcards.INCORRECT_NUMBER:
        raise StripeError(
            402,
            "Your card number is incorrect.",
            type="card_error",
            code="incorrect_number",
            param="card[number]",
        )
    return testcards.spec_for_number(number)
