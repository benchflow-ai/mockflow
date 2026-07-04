"""Products and Prices."""

from __future__ import annotations

import json
import time

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from mock_stripe.ids import generate_id
from mock_stripe.models import Price, Product

from .customers import _merge_metadata
from .deps import get_db, require_api_key
from .errors import StripeError, as_bool, as_int, check_unknown_params, missing_param, resource_missing
from .forms import parse_query, read_body
from .pagination import apply_created_filter, paginate
from .recording import record_event
from .serializers import apply_expand, apply_list_expand, price_to_dict, product_to_dict

router = APIRouter(dependencies=[Depends(require_api_key)])

_PRODUCT_PARAMS = {
    "name", "active", "description", "id", "metadata", "default_price_data",
    "images", "url", "shippable", "statement_descriptor", "unit_label",
    "tax_code", "marketing_features", "package_dimensions",
}

_PRICE_CREATE_PARAMS = {
    "currency", "unit_amount", "unit_amount_decimal", "custom_unit_amount",
    "product", "product_data", "recurring", "nickname", "lookup_key", "metadata",
    "active", "tax_behavior", "billing_scheme", "tiers", "tiers_mode",
    "transform_quantity", "transfer_lookup_key",
}

_PRICE_UPDATE_PARAMS = {"active", "metadata", "nickname", "lookup_key", "tax_behavior"}

_RECURRING_INTERVALS = {"day", "week", "month", "year"}


def _get_product_or_404(db: Session, product_id: str) -> Product:
    product = db.get(Product, product_id)
    if product is None:
        raise resource_missing("product", product_id)
    return product


def _get_price_or_404(db: Session, price_id: str) -> Price:
    price = db.get(Price, price_id)
    if price is None:
        raise resource_missing("price", price_id)
    return price


def _build_recurring(recurring: dict) -> dict:
    interval = recurring.get("interval")
    if interval not in _RECURRING_INTERVALS:
        raise StripeError(
            400,
            "Invalid interval: must be one of day, week, month, or year",
            param="recurring[interval]",
        )
    out = {
        "interval": interval,
        "interval_count": int(recurring.get("interval_count", 1)),
        "trial_period_days": None,
        "usage_type": recurring.get("usage_type", "licensed"),
    }
    if recurring.get("trial_period_days"):
        out["trial_period_days"] = int(recurring["trial_period_days"])
    return out


def _create_price(db: Session, data: dict, product_id: str) -> Price:
    currency = data.get("currency")
    if not currency:
        raise missing_param("currency")
    currency = str(currency).lower()
    unit_amount = as_int(data, "unit_amount", default=None)
    unit_amount_decimal = data.get("unit_amount_decimal")
    if unit_amount is None and unit_amount_decimal is not None:
        unit_amount = int(float(unit_amount_decimal))
    if unit_amount is None:
        raise missing_param("unit_amount")
    recurring_json = None
    price_type = "one_time"
    if isinstance(data.get("recurring"), dict):
        recurring_json = json.dumps(_build_recurring(data["recurring"]))
        price_type = "recurring"
    price = Price(
        id=generate_id("price"),
        product_id=product_id,
        active=as_bool(data, "active", default=True),
        currency=currency,
        unit_amount=unit_amount,
        unit_amount_decimal=str(unit_amount) if unit_amount_decimal is None else str(unit_amount_decimal),
        type=price_type,
        billing_scheme=data.get("billing_scheme", "per_unit"),
        tax_behavior=data.get("tax_behavior", "unspecified"),
        nickname=data.get("nickname") or None,
        lookup_key=data.get("lookup_key") or None,
        recurring_json=recurring_json,
        metadata_json=_merge_metadata("{}", data.get("metadata")),
        created=int(time.time()),
    )
    db.add(price)
    return price


# --- Products ---

@router.post("/v1/products")
async def create_product(request: Request, db: Session = Depends(get_db)):
    data = await read_body(request)
    check_unknown_params(data, _PRODUCT_PARAMS)
    name = data.get("name")
    if not name:
        raise missing_param("name")
    now = int(time.time())
    product = Product(
        id=data.get("id") or generate_id("prod"),
        name=name,
        active=as_bool(data, "active", default=True),
        description=data.get("description") or None,
        url=data.get("url") or None,
        unit_label=data.get("unit_label") or None,
        statement_descriptor=data.get("statement_descriptor") or None,
        shippable=as_bool(data, "shippable", default=None),
        images_json=json.dumps(data["images"]) if isinstance(data.get("images"), list) else "[]",
        metadata_json=_merge_metadata("{}", data.get("metadata")),
        created=now,
        updated=now,
    )
    db.add(product)
    if isinstance(data.get("default_price_data"), dict):
        price = _create_price(db, data["default_price_data"], product.id)
        db.flush()
        record_event(db, "price.created", price_to_dict(price),
                     idempotency_key=request.headers.get("idempotency-key"))
        product.default_price_id = price.id
    db.flush()
    record_event(db, "product.created", product_to_dict(product),
                 idempotency_key=request.headers.get("idempotency-key"))
    db.commit()
    return apply_expand(db, product_to_dict(product), "product", data.get("expand"))


@router.get("/v1/products")
def list_products(request: Request, db: Session = Depends(get_db)):
    params = parse_query(request)
    items = db.query(Product).order_by(Product.seq.desc()).all()
    if "active" in params:
        active = str(params["active"]).lower() == "true"
        items = [p for p in items if p.active == active]
    items = apply_created_filter(items, params)
    envelope = paginate(items, params, "/v1/products", product_to_dict, kind="product")
    return apply_list_expand(db, envelope, "product", params.get("expand"))


@router.get("/v1/products/{product_id}")
def get_product(product_id: str, request: Request, db: Session = Depends(get_db)):
    params = parse_query(request)
    product = _get_product_or_404(db, product_id)
    return apply_expand(db, product_to_dict(product), "product", params.get("expand"))


@router.post("/v1/products/{product_id}")
async def update_product(product_id: str, request: Request, db: Session = Depends(get_db)):
    data = await read_body(request)
    check_unknown_params(data, _PRODUCT_PARAMS | {"default_price"})
    product = _get_product_or_404(db, product_id)
    if "name" in data and data["name"]:
        product.name = data["name"]
    if "active" in data:
        product.active = as_bool(data, "active", default=product.active)
    if "description" in data:
        product.description = data["description"] or None
    if "url" in data:
        product.url = data["url"] or None
    if "unit_label" in data:
        product.unit_label = data["unit_label"] or None
    if "default_price" in data:
        if data["default_price"]:
            price = _get_price_or_404(db, data["default_price"])
            if price.product_id != product.id:
                raise StripeError(
                    400,
                    f"The price {price.id} does not belong to product {product.id}.",
                    param="default_price",
                )
            product.default_price_id = price.id
        else:
            product.default_price_id = None
    if "images" in data and isinstance(data["images"], list):
        product.images_json = json.dumps(data["images"])
    if "metadata" in data:
        product.metadata_json = _merge_metadata(product.metadata_json, data["metadata"])
    product.updated = int(time.time())
    db.flush()
    record_event(db, "product.updated", product_to_dict(product),
                 idempotency_key=request.headers.get("idempotency-key"))
    db.commit()
    return apply_expand(db, product_to_dict(product), "product", data.get("expand"))


@router.delete("/v1/products/{product_id}")
def delete_product(product_id: str, request: Request, db: Session = Depends(get_db)):
    product = _get_product_or_404(db, product_id)
    has_prices = db.query(Price).filter(Price.product_id == product_id).count() > 0
    if has_prices:
        raise StripeError(
            400,
            "This product cannot be deleted because it has one or more prices. "
            "Deactivate it instead by setting active=false.",
            param="id",
        )
    snapshot = product_to_dict(product)
    db.delete(product)
    record_event(db, "product.deleted", snapshot,
                 idempotency_key=request.headers.get("idempotency-key"))
    db.commit()
    return {"id": product_id, "object": "product", "deleted": True}


# --- Prices ---

@router.post("/v1/prices")
async def create_price(request: Request, db: Session = Depends(get_db)):
    data = await read_body(request)
    check_unknown_params(data, _PRICE_CREATE_PARAMS)
    product_id = data.get("product")
    if not product_id and isinstance(data.get("product_data"), dict):
        name = data["product_data"].get("name")
        if not name:
            raise missing_param("product_data[name]")
        now = int(time.time())
        product = Product(id=generate_id("prod"), name=name, created=now, updated=now)
        db.add(product)
        db.flush()
        record_event(db, "product.created", product_to_dict(product),
                     idempotency_key=request.headers.get("idempotency-key"))
        product_id = product.id
    if not product_id:
        raise missing_param("product")
    _get_product_or_404(db, product_id)
    price = _create_price(db, data, product_id)
    db.flush()
    record_event(db, "price.created", price_to_dict(price),
                 idempotency_key=request.headers.get("idempotency-key"))
    db.commit()
    return apply_expand(db, price_to_dict(price), "price", data.get("expand"))


@router.get("/v1/prices")
def list_prices(request: Request, db: Session = Depends(get_db)):
    params = parse_query(request)
    items = db.query(Price).order_by(Price.seq.desc()).all()
    if params.get("product"):
        items = [p for p in items if p.product_id == params["product"]]
    if "active" in params:
        active = str(params["active"]).lower() == "true"
        items = [p for p in items if p.active == active]
    if params.get("type"):
        items = [p for p in items if p.type == params["type"]]
    if params.get("currency"):
        items = [p for p in items if p.currency == str(params["currency"]).lower()]
    items = apply_created_filter(items, params)
    envelope = paginate(items, params, "/v1/prices", price_to_dict, kind="price")
    return apply_list_expand(db, envelope, "price", params.get("expand"))


@router.get("/v1/prices/{price_id}")
def get_price(price_id: str, request: Request, db: Session = Depends(get_db)):
    params = parse_query(request)
    price = _get_price_or_404(db, price_id)
    return apply_expand(db, price_to_dict(price), "price", params.get("expand"))


@router.post("/v1/prices/{price_id}")
async def update_price(price_id: str, request: Request, db: Session = Depends(get_db)):
    data = await read_body(request)
    price = _get_price_or_404(db, price_id)
    for immutable in ("unit_amount", "unit_amount_decimal", "currency", "product", "recurring"):
        if immutable in data:
            raise StripeError(
                400,
                f"You cannot update the `{immutable}` of a Price. Create a new Price "
                f"instead and deactivate this one.",
                param=immutable,
            )
    check_unknown_params(data, _PRICE_UPDATE_PARAMS)
    if "active" in data:
        price.active = as_bool(data, "active", default=price.active)
    if "nickname" in data:
        price.nickname = data["nickname"] or None
    if "lookup_key" in data:
        price.lookup_key = data["lookup_key"] or None
    if "tax_behavior" in data and data["tax_behavior"]:
        price.tax_behavior = data["tax_behavior"]
    if "metadata" in data:
        price.metadata_json = _merge_metadata(price.metadata_json, data["metadata"])
    db.flush()
    record_event(db, "price.updated", price_to_dict(price),
                 idempotency_key=request.headers.get("idempotency-key"))
    db.commit()
    return apply_expand(db, price_to_dict(price), "price", data.get("expand"))
