"""Customers: POST/GET/POST(update)/DELETE /v1/customers[/{id}] + list."""

from __future__ import annotations

import json
import time

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from mock_stripe.ids import generate_id
from mock_stripe.models import Customer, PaymentMethod

from .deps import get_db, require_api_key
from .errors import StripeError, as_int, check_unknown_params, resource_missing
from .forms import parse_query, read_body
from .pagination import apply_created_filter, paginate
from .recording import record_event
from .serializers import (
    apply_expand,
    apply_list_expand,
    customer_to_dict,
    payment_method_to_dict,
)

router = APIRouter(dependencies=[Depends(require_api_key)])

_CREATE_PARAMS = {
    "address", "balance", "business_name", "cash_balance", "description", "email",
    "individual_name", "invoice_prefix", "invoice_settings", "metadata", "name",
    "next_invoice_sequence", "payment_method", "phone", "preferred_locales",
    "shipping", "source", "tax", "tax_exempt", "tax_id_data", "test_clock", "validate",
}

_TAX_EXEMPT_VALUES = {"none", "exempt", "reverse"}


def _get_customer_or_404(db: Session, customer_id: str) -> Customer:
    customer = db.get(Customer, customer_id)
    if customer is None:
        raise resource_missing("customer", customer_id)
    return customer


def _merge_metadata(existing_json: str, incoming) -> str:
    """Stripe metadata semantics: merge keys; empty value unsets a key;
    `metadata=` (empty string) clears all."""
    if incoming is None:
        return existing_json
    if incoming == "":
        return "{}"
    if not isinstance(incoming, dict):
        return existing_json
    current = json.loads(existing_json or "{}")
    for k, v in incoming.items():
        if v == "" or v is None:
            current.pop(k, None)
        else:
            current[k] = str(v)
    return json.dumps(current)


def _apply_customer_params(db: Session, customer: Customer, data: dict) -> None:
    if "email" in data:
        customer.email = data["email"] or None
    if "name" in data:
        customer.name = data["name"] or None
    if "description" in data:
        customer.description = data["description"] or None
    if "phone" in data:
        customer.phone = data["phone"] or None
    if "balance" in data:
        customer.balance = as_int(data, "balance", default=0) or 0
    if "address" in data:
        customer.address_json = json.dumps(data["address"]) if data["address"] else None
    if "shipping" in data:
        customer.shipping_json = json.dumps(data["shipping"]) if data["shipping"] else None
    if "tax_exempt" in data:
        value = data["tax_exempt"] or "none"
        if value not in _TAX_EXEMPT_VALUES:
            raise StripeError(
                400,
                "Invalid tax_exempt value: must be one of none, exempt, or reverse",
                param="tax_exempt",
            )
        customer.tax_exempt = value
    if "preferred_locales" in data:
        locales = data["preferred_locales"]
        if isinstance(locales, list):
            customer.preferred_locales_json = json.dumps(locales)
    if "invoice_prefix" in data:
        customer.invoice_prefix = data["invoice_prefix"] or ""
    if "next_invoice_sequence" in data:
        customer.next_invoice_sequence = as_int(data, "next_invoice_sequence", default=1) or 1
    if "invoice_settings" in data and isinstance(data["invoice_settings"], dict):
        dpm = data["invoice_settings"].get("default_payment_method")
        if dpm is not None:
            customer.default_payment_method = dpm or None
    if "payment_method" in data and data["payment_method"]:
        pm = db.get(PaymentMethod, data["payment_method"])
        if pm is None:
            raise resource_missing("PaymentMethod", data["payment_method"])
        pm.customer_id = customer.id
    if "metadata" in data:
        customer.metadata_json = _merge_metadata(customer.metadata_json, data["metadata"])


@router.post("/v1/customers")
async def create_customer(request: Request, db: Session = Depends(get_db)):
    data = await read_body(request)
    check_unknown_params(data, _CREATE_PARAMS)
    customer = Customer(
        id=generate_id("cus"),
        invoice_prefix=generate_id("", length=8).strip("_").upper(),
        created=int(time.time()),
    )
    db.add(customer)
    _apply_customer_params(db, customer, data)
    db.flush()
    snapshot = customer_to_dict(customer)
    record_event(db, "customer.created", snapshot,
                 idempotency_key=request.headers.get("idempotency-key"))
    db.commit()
    return apply_expand(db, customer_to_dict(customer), "customer", data.get("expand"))


@router.get("/v1/customers")
def list_customers(request: Request, db: Session = Depends(get_db)):
    params = parse_query(request)
    items = db.query(Customer).filter(Customer.deleted == False).order_by(Customer.seq.desc()).all()  # noqa: E712
    if params.get("email"):
        items = [c for c in items if (c.email or "").lower() == str(params["email"]).lower()]
    items = apply_created_filter(items, params)
    envelope = paginate(items, params, "/v1/customers", customer_to_dict, kind="customer")
    return apply_list_expand(db, envelope, "customer", params.get("expand"))


@router.get("/v1/customers/{customer_id}")
def get_customer(customer_id: str, request: Request, db: Session = Depends(get_db)):
    params = parse_query(request)
    customer = _get_customer_or_404(db, customer_id)
    return apply_expand(db, customer_to_dict(customer), "customer", params.get("expand"))


@router.post("/v1/customers/{customer_id}")
async def update_customer(customer_id: str, request: Request, db: Session = Depends(get_db)):
    data = await read_body(request)
    check_unknown_params(data, _CREATE_PARAMS | {"default_source"})
    customer = _get_customer_or_404(db, customer_id)
    if customer.deleted:
        raise StripeError(
            400,
            f"Customer {customer_id} has been deleted and cannot be updated.",
            param="id",
        )
    _apply_customer_params(db, customer, data)
    db.flush()
    record_event(db, "customer.updated", customer_to_dict(customer),
                 idempotency_key=request.headers.get("idempotency-key"))
    db.commit()
    return apply_expand(db, customer_to_dict(customer), "customer", data.get("expand"))


@router.delete("/v1/customers/{customer_id}")
def delete_customer(customer_id: str, request: Request, db: Session = Depends(get_db)):
    customer = _get_customer_or_404(db, customer_id)
    snapshot = customer_to_dict(customer)
    customer.deleted = True
    # Detach payment methods
    for pm in db.query(PaymentMethod).filter(PaymentMethod.customer_id == customer_id).all():
        pm.customer_id = None
    record_event(db, "customer.deleted", snapshot,
                 idempotency_key=request.headers.get("idempotency-key"))
    db.commit()
    return {"id": customer.id, "object": "customer", "deleted": True}


@router.get("/v1/customers/{customer_id}/payment_methods")
def list_customer_payment_methods(customer_id: str, request: Request, db: Session = Depends(get_db)):
    params = parse_query(request)
    _get_customer_or_404(db, customer_id)
    items = (
        db.query(PaymentMethod)
        .filter(PaymentMethod.customer_id == customer_id)
        .order_by(PaymentMethod.seq.desc())
        .all()
    )
    if params.get("type"):
        items = [pm for pm in items if pm.type == params["type"]]
    envelope = paginate(
        items, params, f"/v1/customers/{customer_id}/payment_methods",
        payment_method_to_dict, kind="payment_method",
    )
    return apply_list_expand(db, envelope, "payment_method", params.get("expand"))
