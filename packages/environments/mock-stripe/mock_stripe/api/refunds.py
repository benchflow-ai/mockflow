"""Refunds: POST /v1/refunds, GET list, GET/{id}, POST/{id} (metadata), POST/{id}/cancel."""

from __future__ import annotations

import time

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from mock_stripe.ids import generate_id
from mock_stripe.models import Charge, PaymentIntent, Refund

from .customers import _merge_metadata
from .deps import get_db, require_api_key
from .errors import StripeError, as_int, check_unknown_params, resource_missing
from .forms import parse_query, read_body
from .ledger import create_refund_balance_transaction
from .pagination import apply_created_filter, paginate
from .recording import record_event
from .serializers import apply_expand, apply_list_expand, charge_to_dict, refund_to_dict

router = APIRouter(dependencies=[Depends(require_api_key)])

_CREATE_PARAMS = {
    "charge", "payment_intent", "amount", "reason", "metadata",
    "refund_application_fee", "reverse_transfer", "instructions_email", "origin",
}

_REASONS = {"duplicate", "fraudulent", "requested_by_customer"}


def _get_refund_or_404(db: Session, refund_id: str) -> Refund:
    refund = db.get(Refund, refund_id)
    if refund is None:
        raise resource_missing("refund", refund_id)
    return refund


@router.post("/v1/refunds")
async def create_refund(request: Request, db: Session = Depends(get_db)):
    data = await read_body(request)
    check_unknown_params(data, _CREATE_PARAMS)
    idem = request.headers.get("idempotency-key")

    charge_id = data.get("charge")
    pi_id = data.get("payment_intent")
    if not charge_id and not pi_id:
        raise StripeError(
            400,
            "One of the following params should be provided for this request: "
            "payment_intent or charge.",
            param="charge",
        )

    ch: Charge | None = None
    if charge_id:
        ch = db.get(Charge, charge_id)
        if ch is None:
            raise resource_missing("charge", charge_id)
    else:
        pi = db.get(PaymentIntent, pi_id)
        if pi is None:
            raise resource_missing("payment_intent", pi_id)
        if pi.latest_charge_id:
            ch = db.get(Charge, pi.latest_charge_id)
        if ch is None or ch.status != "succeeded":
            raise StripeError(
                400,
                f"The PaymentIntent {pi_id} does not have a successful charge to refund.",
                param="payment_intent",
            )

    if ch.status != "succeeded":
        raise StripeError(400, f"The charge {ch.id} has failed and cannot be refunded.", param="charge")
    if not ch.captured:
        raise StripeError(
            400,
            f"Charge {ch.id} has not been captured. To release an uncaptured charge, "
            f"cancel the PaymentIntent instead.",
            param="charge",
        )

    refundable = ch.amount - ch.amount_refunded
    # For partially-captured charges, only the captured portion can be refunded.
    if ch.amount_captured and ch.amount_captured < ch.amount:
        refundable = ch.amount_captured - max(0, ch.amount_refunded - (ch.amount - ch.amount_captured))
    if refundable <= 0:
        raise StripeError(
            400,
            f"Charge {ch.id} has already been refunded.",
            code="charge_already_refunded",
        )

    amount = as_int(data, "amount", default=refundable)
    if amount is None or amount <= 0:
        raise StripeError(400, "Invalid positive integer", param="amount")
    if amount > refundable:
        raise StripeError(
            400,
            f"Refund amount ({amount}) is greater than unrefunded amount on charge ({refundable})",
            param="amount",
        )

    reason = data.get("reason") or None
    if reason is not None and reason not in _REASONS:
        raise StripeError(
            400,
            "Invalid reason: must be one of duplicate, fraudulent, or requested_by_customer",
            param="reason",
        )

    refund = Refund(
        id=generate_id("re"),
        amount=amount,
        currency=ch.currency,
        charge_id=ch.id,
        payment_intent_id=ch.payment_intent_id,
        status="succeeded",
        reason=reason,
        metadata_json=_merge_metadata("{}", data.get("metadata")),
        created=int(time.time()),
    )
    db.add(refund)
    refund.balance_transaction_id = create_refund_balance_transaction(
        db, refund_id=refund.id, amount=amount, currency=ch.currency
    ).id

    ch.amount_refunded += amount
    if ch.amount_refunded >= ch.amount:
        ch.refunded = True
    db.flush()
    record_event(db, "refund.created", refund_to_dict(refund), idempotency_key=idem)
    record_event(db, "charge.refunded", charge_to_dict(ch, db), idempotency_key=idem)
    db.commit()
    return apply_expand(db, refund_to_dict(refund), "refund", data.get("expand"))


@router.get("/v1/refunds")
def list_refunds(request: Request, db: Session = Depends(get_db)):
    params = parse_query(request)
    items = db.query(Refund).order_by(Refund.seq.desc()).all()
    if params.get("charge"):
        items = [r for r in items if r.charge_id == params["charge"]]
    if params.get("payment_intent"):
        items = [r for r in items if r.payment_intent_id == params["payment_intent"]]
    items = apply_created_filter(items, params)
    envelope = paginate(items, params, "/v1/refunds", refund_to_dict, kind="refund")
    return apply_list_expand(db, envelope, "refund", params.get("expand"))


@router.get("/v1/refunds/{refund_id}")
def get_refund(refund_id: str, request: Request, db: Session = Depends(get_db)):
    params = parse_query(request)
    refund = _get_refund_or_404(db, refund_id)
    return apply_expand(db, refund_to_dict(refund), "refund", params.get("expand"))


@router.post("/v1/refunds/{refund_id}")
async def update_refund(refund_id: str, request: Request, db: Session = Depends(get_db)):
    data = await read_body(request)
    check_unknown_params(data, {"metadata"})
    refund = _get_refund_or_404(db, refund_id)
    if "metadata" in data:
        refund.metadata_json = _merge_metadata(refund.metadata_json, data["metadata"])
    db.commit()
    return apply_expand(db, refund_to_dict(refund), "refund", data.get("expand"))


@router.post("/v1/refunds/{refund_id}/cancel")
async def cancel_refund(refund_id: str, request: Request, db: Session = Depends(get_db)):
    refund = _get_refund_or_404(db, refund_id)
    # Mock refunds succeed immediately, so cancellation is never possible —
    # matches real Stripe's error for non-pending refunds.
    raise StripeError(
        400,
        f"Refunds can only be canceled while processing; this refund has a status of "
        f"{refund.status}.",
        param="refund",
    )
