"""Charges: GET /v1/charges (list), GET /{id}, POST /{id} (metadata/description update)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from mock_stripe.models import Charge, Customer

from .customers import _merge_metadata
from .deps import get_db, require_api_key
from .errors import check_unknown_params, resource_missing
from .forms import parse_query, read_body
from .pagination import apply_created_filter, paginate
from .recording import record_event
from .serializers import apply_expand, apply_list_expand, charge_to_dict

router = APIRouter(dependencies=[Depends(require_api_key)])


def _get_charge_or_404(db: Session, charge_id: str) -> Charge:
    ch = db.get(Charge, charge_id)
    if ch is None:
        raise resource_missing("charge", charge_id)
    return ch


@router.get("/v1/charges")
def list_charges(request: Request, db: Session = Depends(get_db)):
    params = parse_query(request)
    items = db.query(Charge).order_by(Charge.seq.desc()).all()
    if params.get("customer"):
        customer_id = params["customer"]
        if db.get(Customer, customer_id) is None:
            raise resource_missing("customer", customer_id)
        items = [c for c in items if c.customer_id == customer_id]
    if params.get("payment_intent"):
        items = [c for c in items if c.payment_intent_id == params["payment_intent"]]
    items = apply_created_filter(items, params)
    envelope = paginate(
        items, params, "/v1/charges", lambda c: charge_to_dict(c, db), kind="charge"
    )
    return apply_list_expand(db, envelope, "charge", params.get("expand"))


@router.get("/v1/charges/{charge_id}")
def get_charge(charge_id: str, request: Request, db: Session = Depends(get_db)):
    params = parse_query(request)
    ch = _get_charge_or_404(db, charge_id)
    return apply_expand(db, charge_to_dict(ch, db), "charge", params.get("expand"))


@router.post("/v1/charges/{charge_id}")
async def update_charge(charge_id: str, request: Request, db: Session = Depends(get_db)):
    data = await read_body(request)
    check_unknown_params(data, {"metadata", "description", "receipt_email", "fraud_details", "shipping", "customer"})
    ch = _get_charge_or_404(db, charge_id)
    if "metadata" in data:
        ch.metadata_json = _merge_metadata(ch.metadata_json, data["metadata"])
    if "description" in data:
        ch.description = data["description"] or None
    if "receipt_email" in data:
        ch.receipt_email = data["receipt_email"] or None
    db.flush()
    record_event(db, "charge.updated", charge_to_dict(ch, db),
                 idempotency_key=request.headers.get("idempotency-key"))
    db.commit()
    return apply_expand(db, charge_to_dict(ch, db), "charge", data.get("expand"))
