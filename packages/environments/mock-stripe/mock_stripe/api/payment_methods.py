"""PaymentMethods: create/retrieve/update/attach/detach/list."""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from mock_stripe.models import Customer, PaymentMethod

from .customers import _merge_metadata
from .deps import get_db, require_api_key
from .errors import StripeError, as_int, check_unknown_params, missing_param, resource_missing
from .forms import parse_query, read_body
from .pagination import paginate
from .pm_store import card_data_to_spec, create_pm_from_spec, resolve_payment_method
from .recording import record_event
from .serializers import apply_expand, apply_list_expand, payment_method_to_dict

router = APIRouter(dependencies=[Depends(require_api_key)])

_CREATE_PARAMS = {"type", "card", "billing_details", "metadata", "allow_redisplay"}


@router.post("/v1/payment_methods")
async def create_payment_method(request: Request, db: Session = Depends(get_db)):
    data = await read_body(request)
    check_unknown_params(data, _CREATE_PARAMS)
    pm_type = data.get("type")
    if not pm_type:
        raise missing_param("type")
    if pm_type != "card":
        raise StripeError(
            400,
            f"Invalid type: must be one of card (this mock implements card only; "
            f"received '{pm_type}')",
            param="type",
        )
    card = data.get("card") or {}
    if not isinstance(card, dict):
        card = {}
    spec = card_data_to_spec(card)
    exp_month = as_int(card, "exp_month", default=12) or 12
    exp_year = as_int(card, "exp_year", default=2034) or 2034
    cvc_check = "pass" if card.get("cvc") else None
    billing_details = data.get("billing_details") if isinstance(data.get("billing_details"), dict) else None
    metadata = data.get("metadata") if isinstance(data.get("metadata"), dict) else {}
    pm = create_pm_from_spec(
        db,
        spec,
        exp_month=exp_month,
        exp_year=exp_year,
        cvc_check=cvc_check,
        billing_details=billing_details,
        metadata={k: str(v) for k, v in (metadata or {}).items()},
    )
    db.commit()
    return apply_expand(db, payment_method_to_dict(pm), "payment_method", data.get("expand"))


@router.get("/v1/payment_methods")
def list_payment_methods(request: Request, db: Session = Depends(get_db)):
    params = parse_query(request)
    query = db.query(PaymentMethod).order_by(PaymentMethod.seq.desc())
    items = query.all()
    if params.get("customer"):
        customer_id = params["customer"]
        if db.get(Customer, customer_id) is None:
            raise resource_missing("customer", customer_id)
        items = [pm for pm in items if pm.customer_id == customer_id]
    if params.get("type"):
        items = [pm for pm in items if pm.type == params["type"]]
    envelope = paginate(items, params, "/v1/payment_methods", payment_method_to_dict, kind="payment_method")
    return apply_list_expand(db, envelope, "payment_method", params.get("expand"))


@router.get("/v1/payment_methods/{pm_id}")
def get_payment_method(pm_id: str, request: Request, db: Session = Depends(get_db)):
    params = parse_query(request)
    pm = resolve_payment_method(db, pm_id)
    db.commit()  # persist a materialized virtual pm
    return apply_expand(db, payment_method_to_dict(pm), "payment_method", params.get("expand"))


@router.post("/v1/payment_methods/{pm_id}")
async def update_payment_method(pm_id: str, request: Request, db: Session = Depends(get_db)):
    data = await read_body(request)
    check_unknown_params(data, {"billing_details", "card", "metadata", "allow_redisplay"})
    pm = resolve_payment_method(db, pm_id)
    if "metadata" in data:
        pm.metadata_json = _merge_metadata(pm.metadata_json, data["metadata"])
    if "billing_details" in data and isinstance(data["billing_details"], dict):
        pm.billing_details_json = json.dumps(data["billing_details"])
    if "card" in data and isinstance(data["card"], dict):
        if "exp_month" in data["card"]:
            pm.card_exp_month = as_int(data["card"], "exp_month", default=pm.card_exp_month)
        if "exp_year" in data["card"]:
            pm.card_exp_year = as_int(data["card"], "exp_year", default=pm.card_exp_year)
    db.commit()
    return apply_expand(db, payment_method_to_dict(pm), "payment_method", data.get("expand"))


@router.post("/v1/payment_methods/{pm_id}/attach")
async def attach_payment_method(pm_id: str, request: Request, db: Session = Depends(get_db)):
    data = await read_body(request)
    check_unknown_params(data, {"customer", "customer_account"})
    customer_id = data.get("customer")
    if not customer_id:
        raise missing_param("customer")
    customer = db.get(Customer, customer_id)
    if customer is None or customer.deleted:
        raise resource_missing("customer", customer_id)
    pm = resolve_payment_method(db, pm_id)
    if pm.customer_id is not None:
        raise StripeError(
            400,
            "The payment method you provided has already been attached to a customer.",
            param="payment_method",
        )
    pm.customer_id = customer_id
    db.flush()
    record_event(db, "payment_method.attached", payment_method_to_dict(pm),
                 idempotency_key=request.headers.get("idempotency-key"))
    db.commit()
    return apply_expand(db, payment_method_to_dict(pm), "payment_method", data.get("expand"))


@router.post("/v1/payment_methods/{pm_id}/detach")
async def detach_payment_method(pm_id: str, request: Request, db: Session = Depends(get_db)):
    data = await read_body(request)
    pm = db.get(PaymentMethod, pm_id)
    if pm is None:
        raise resource_missing("PaymentMethod", pm_id)
    if pm.customer_id is None:
        raise StripeError(
            400,
            "The payment method you provided is not attached to a customer so detachment "
            "is impossible.",
            param="payment_method",
        )
    pm.customer_id = None
    db.flush()
    record_event(db, "payment_method.detached", payment_method_to_dict(pm),
                 idempotency_key=request.headers.get("idempotency-key"))
    db.commit()
    return apply_expand(db, payment_method_to_dict(pm), "payment_method", data.get("expand"))
