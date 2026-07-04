"""PaymentIntents: create/list/retrieve/update/confirm/capture/cancel + 3DS.

Status machine implemented:
    requires_payment_method -> (payment_method attached) requires_confirmation
    -> confirm -> [decline -> requires_payment_method + last_payment_error (402)]
               |  [3DS pm  -> requires_action + next_action (nothing charged)]
               |  [capture_method=manual -> requires_capture (amount_capturable set)]
               |  [succeeded (charge created)]
    requires_action -> POST {id}/_complete_authentication (MOCK-ONLY endpoint;
        real Stripe completes 3DS via Stripe.js — see API_NOTES.md)
        -> succeed=true  -> succeeded (or requires_capture when manual) + charge
        -> succeed=false -> requires_payment_method + last_payment_error
                            authentication_required + failed charge
    requires_capture -> capture -> succeeded (partial capture refunds remainder)
    cancelable statuses -> cancel -> canceled
"""

from __future__ import annotations

import hashlib
import json
import time

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from mock_stripe.ids import client_secret_for, generate_id
from mock_stripe.models import Charge, Customer, PaymentIntent, PaymentMethod, Refund

from .customers import _merge_metadata
from .deps import get_db, require_api_key
from .errors import StripeError, as_bool, as_int, check_unknown_params, missing_param, resource_missing
from .forms import parse_query, read_body
from .ledger import create_charge_balance_transaction
from .pagination import apply_created_filter, paginate
from .pm_store import resolve_payment_method
from .recording import record_event
from .serializers import (
    apply_expand,
    apply_list_expand,
    charge_to_dict,
    payment_intent_to_dict,
    payment_method_to_dict,
)

router = APIRouter(dependencies=[Depends(require_api_key)])

_CREATE_PARAMS = {
    "amount", "currency", "automatic_payment_methods", "capture_method", "confirm",
    "confirmation_method", "customer", "description", "metadata", "off_session",
    "payment_method", "payment_method_data", "payment_method_options",
    "payment_method_types", "receipt_email", "return_url", "setup_future_usage",
    "shipping", "statement_descriptor", "statement_descriptor_suffix",
    "transfer_data", "transfer_group", "error_on_requires_action", "mandate",
    "mandate_data", "confirmation_token", "application_fee_amount", "on_behalf_of",
    "excluded_payment_method_types",
}

_CONFIRM_PARAMS = {
    "payment_method", "return_url", "off_session", "receipt_email",
    "setup_future_usage", "shipping", "capture_method", "amount_to_confirm",
    "confirmation_token", "error_on_requires_action", "mandate", "mandate_data",
    "payment_method_data", "payment_method_options", "excluded_payment_method_types",
}

_CAPTURE_PARAMS = {
    "amount_to_capture", "final_capture", "application_fee_amount", "metadata",
    "statement_descriptor", "statement_descriptor_suffix", "transfer_data",
    "amount_details", "payment_details", "hooks",
}

_UPDATE_PARAMS = _CREATE_PARAMS - {"confirm"}

_CANCEL_REASONS = {"duplicate", "fraudulent", "requested_by_customer", "abandoned"}
_CAPTURE_METHODS = {"automatic", "automatic_async", "manual"}

_CONFIRMABLE = {"requires_confirmation", "requires_payment_method", "requires_action"}
_CANCELABLE = {
    "requires_payment_method", "requires_capture", "requires_confirmation",
    "requires_action", "processing",
}


def _get_pi_or_404(db: Session, pi_id: str) -> PaymentIntent:
    pi = db.get(PaymentIntent, pi_id)
    if pi is None:
        raise resource_missing("payment_intent", pi_id)
    return pi


def _risk_score(seed_str: str) -> int:
    return sum(seed_str.encode()) % 60 + 5


_AUTH_REQUIRED_MESSAGE = "Your card was declined. This transaction requires authentication."


def _three_d_secure_details(charge_id: str, result: str) -> dict:
    """`payment_method_details.card.three_d_secure` after an authentication attempt."""
    return {
        "authentication_flow": "challenge",
        "electronic_commerce_indicator": "05" if result == "authenticated" else "07",
        "exemption_indicator": None,
        "result": result,  # "authenticated" | "failed"
        "result_reason": "rejected" if result == "failed" else None,
        "transaction_id": hashlib.sha256(f"3ds:{charge_id}".encode()).hexdigest()[:32],
        "version": "2.2.0",
    }


def _build_next_action(return_url: str | None) -> dict:
    """Real-shape `next_action` for a 3DS challenge.

    Server-side confirms without a return_url get `use_stripe_sdk` (the shape
    Stripe returns for SDK-driven 3DS); with a return_url Stripe returns
    `redirect_to_url` instead.
    """
    src = generate_id("src")
    secret_body = generate_id("src")[4:]  # 24 alnum chars
    auth_url = (
        f"https://hooks.stripe.com/redirect/authenticate/{src}"
        f"?client_secret=src_client_secret_{secret_body}"
    )
    if return_url:
        return {
            "type": "redirect_to_url",
            "redirect_to_url": {"return_url": return_url, "url": auth_url},
        }
    return {
        "type": "use_stripe_sdk",
        "use_stripe_sdk": {
            "type": "three_d_secure_redirect",
            "stripe_js": auth_url,
            "source": src,
        },
    }


def _pm_details_snapshot(
    pm: PaymentMethod,
    *,
    charge_id: str | None = None,
    three_d_secure: str | None = None,
) -> dict:
    return {
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
            "three_d_secure": (
                _three_d_secure_details(charge_id, three_d_secure)
                if three_d_secure and charge_id
                else None
            ),
            "wallet": None,
        },
        "type": "card",
    }


def _create_charge(
    db: Session,
    pi: PaymentIntent,
    pm: PaymentMethod,
    *,
    failed: bool,
    captured: bool,
    failure: tuple[str, str | None, str | None] | None = None,
    three_d_secure: str | None = None,
) -> Charge:
    """Create a Charge row. `failure` overrides the pm's decline spec as
    (failure_code, decline_code, failure_message); `three_d_secure` marks the
    charge as post-authentication ("authenticated"/"failed")."""
    ch_id = generate_id("ch")
    if failed and failure is None:
        failure = (pm.failure_code, pm.decline_code, pm.failure_message)
    if failed:
        failure_code, decline_code, failure_message = failure
        outcome = {
            "network_status": "declined_by_network",
            "reason": decline_code or failure_code,
            "risk_level": "normal",
            "risk_score": _risk_score(ch_id),
            "seller_message": "The bank did not return any further details with this decline.",
            "type": "issuer_declined",
        }
    else:
        outcome = {
            "network_status": "approved_by_network",
            "reason": None,
            "risk_level": "normal",
            "risk_score": _risk_score(ch_id),
            "seller_message": "Payment complete.",
            "type": "authorized",
        }
    ch = Charge(
        id=ch_id,
        amount=pi.amount,
        amount_captured=pi.amount if (captured and not failed) else 0,
        amount_refunded=0,
        currency=pi.currency,
        status="failed" if failed else "succeeded",
        paid=not failed,
        captured=captured and not failed,
        refunded=False,
        customer_id=pi.customer_id,
        payment_intent_id=pi.id,
        payment_method_id=pm.id,
        description=pi.description,
        receipt_email=pi.receipt_email,
        receipt_url=None if failed else f"https://pay.stripe.com/receipts/payment/{ch_id}",
        failure_code=failure[0] if failed else None,
        failure_message=failure[2] if failed else None,
        calculated_statement_descriptor=None if failed else "Stripe",
        statement_descriptor=pi.statement_descriptor,
        statement_descriptor_suffix=pi.statement_descriptor_suffix,
        outcome_json=json.dumps(outcome),
        payment_method_details_json=json.dumps(
            _pm_details_snapshot(pm, charge_id=ch_id, three_d_secure=three_d_secure)
        ),
        billing_details_json=pm.billing_details_json,
        metadata_json=pi.metadata_json,
        created=int(time.time()),
    )
    db.add(ch)
    return ch


def _do_confirm(db: Session, pi: PaymentIntent, data: dict, request: Request):
    """Run the confirm transition. Raises StripeError(402) on declines."""
    idem = request.headers.get("idempotency-key")
    if pi.status not in _CONFIRMABLE:
        raise StripeError(
            400,
            f"You cannot confirm this PaymentIntent because it has a status of "
            f"{pi.status}. Only a PaymentIntent with one of the following statuses "
            f"may be confirmed: requires_confirmation, requires_action, "
            f"requires_payment_method.",
            code="payment_intent_unexpected_state",
        )

    if data.get("capture_method"):
        if data["capture_method"] not in _CAPTURE_METHODS:
            raise StripeError(400, f"Invalid capture_method: {data['capture_method']}", param="capture_method")
        pi.capture_method = data["capture_method"]
    if data.get("receipt_email"):
        pi.receipt_email = data["receipt_email"]
    if data.get("setup_future_usage"):
        pi.setup_future_usage = data["setup_future_usage"]
    if data.get("shipping"):
        pi.shipping_json = json.dumps(data["shipping"])

    pm: PaymentMethod | None = None
    if data.get("payment_method"):
        pm = resolve_payment_method(db, data["payment_method"])
    elif pi.payment_method_id:
        pm = db.get(PaymentMethod, pi.payment_method_id)
    if pm is None:
        raise StripeError(
            400,
            "You cannot confirm this PaymentIntent because it's missing a payment "
            "method. You can either update the PaymentIntent with a payment method "
            "and then confirm it again, or confirm it again directly with a payment "
            "method.",
            code="payment_intent_unexpected_state",
        )
    pi.payment_method_id = pm.id

    if pm.failure_code:
        # --- Decline path: failed charge + last_payment_error + HTTP 402 ---
        ch = _create_charge(db, pi, pm, failed=True, captured=False)
        pi.latest_charge_id = ch.id
        pi.status = "requires_payment_method"
        pi.payment_method_id = None
        pi.next_action_json = None
        pm_snapshot = payment_method_to_dict(pm)
        last_error = {
            "type": "card_error",
            "code": pm.failure_code,
            "message": pm.failure_message,
            "param": None,
            "charge": ch.id,
            "doc_url": f"https://stripe.com/docs/error-codes/{pm.failure_code.replace('_', '-')}",
            "payment_method": pm_snapshot,
        }
        if pm.decline_code:
            last_error["decline_code"] = pm.decline_code
        pi.last_payment_error_json = json.dumps(last_error)
        db.flush()
        record_event(db, "charge.failed", charge_to_dict(ch, db), idempotency_key=idem)
        record_event(db, "payment_intent.payment_failed", payment_intent_to_dict(pi), idempotency_key=idem)
        db.commit()
        raise StripeError(
            402,
            pm.failure_message or "Your card was declined.",
            type="card_error",
            code=pm.failure_code,
            decline_code=pm.decline_code,
            charge=ch.id,
            payment_intent=payment_intent_to_dict(pi),
            payment_method=pm_snapshot,
            include_param_null=True,
        )

    if pm.authentication_required:
        # --- 3DS/SCA path: requires_action + next_action; NOTHING is charged
        # until authentication completes (see _complete_authentication). ---
        pi.status = "requires_action"
        pi.next_action_json = json.dumps(_build_next_action(data.get("return_url") or None))
        pi.last_payment_error_json = None
        db.flush()
        record_event(db, "payment_intent.requires_action", payment_intent_to_dict(pi),
                     idempotency_key=idem)
        db.commit()
        return

    _finalize_success(db, pi, pm, idem)


def _finalize_success(db: Session, pi: PaymentIntent, pm: PaymentMethod,
                      idem: str | None, *, three_d_secure: bool = False) -> None:
    """Shared success transition for confirm and completed authentication."""
    manual = pi.capture_method == "manual"
    ch = _create_charge(
        db, pi, pm, failed=False, captured=not manual,
        three_d_secure="authenticated" if three_d_secure else None,
    )
    pi.latest_charge_id = ch.id
    pi.last_payment_error_json = None
    pi.next_action_json = None
    if manual:
        pi.status = "requires_capture"
        pi.amount_capturable = pi.amount
        db.flush()
        record_event(db, "charge.succeeded", charge_to_dict(ch, db), idempotency_key=idem)
        record_event(db, "payment_intent.amount_capturable_updated", payment_intent_to_dict(pi), idempotency_key=idem)
    else:
        pi.status = "succeeded"
        pi.amount_received = pi.amount
        ch.balance_transaction_id = create_charge_balance_transaction(
            db, charge_id=ch.id, amount=ch.amount, currency=ch.currency
        ).id
        db.flush()
        record_event(db, "charge.succeeded", charge_to_dict(ch, db), idempotency_key=idem)
        record_event(db, "payment_intent.succeeded", payment_intent_to_dict(pi), idempotency_key=idem)
    db.commit()


def _fail_authentication(db: Session, pi: PaymentIntent, pm: PaymentMethod,
                         idem: str | None) -> None:
    """Failed/abandoned 3DS challenge: failed charge + authentication_required
    last_payment_error, PI back to requires_payment_method."""
    ch = _create_charge(
        db, pi, pm, failed=True, captured=False,
        failure=("authentication_required", "authentication_required", _AUTH_REQUIRED_MESSAGE),
        three_d_secure="failed",
    )
    pi.latest_charge_id = ch.id
    pi.status = "requires_payment_method"
    pi.payment_method_id = None
    pi.next_action_json = None
    pm_snapshot = payment_method_to_dict(pm)
    pi.last_payment_error_json = json.dumps({
        "type": "card_error",
        "code": "authentication_required",
        "decline_code": "authentication_required",
        "message": _AUTH_REQUIRED_MESSAGE,
        "param": None,
        "charge": ch.id,
        "doc_url": "https://stripe.com/docs/error-codes/authentication-required",
        "payment_method": pm_snapshot,
    })
    db.flush()
    record_event(db, "charge.failed", charge_to_dict(ch, db), idempotency_key=idem)
    record_event(db, "payment_intent.payment_failed", payment_intent_to_dict(pi), idempotency_key=idem)
    db.commit()


@router.post("/v1/payment_intents")
async def create_payment_intent(request: Request, db: Session = Depends(get_db)):
    data = await read_body(request)
    check_unknown_params(data, _CREATE_PARAMS)
    amount = as_int(data, "amount", required=True)
    if amount is None or amount <= 0:
        raise StripeError(400, "This value must be greater than or equal to 1.", param="amount")
    currency = data.get("currency")
    if not currency:
        raise missing_param("currency")
    currency = str(currency).lower()
    if len(currency) != 3 or not currency.isalpha():
        raise StripeError(400, f"Invalid currency: {currency}. Stripe currently supports "
                               f"three-letter ISO currency codes.", param="currency")

    capture_method = data.get("capture_method", "automatic")
    if capture_method not in _CAPTURE_METHODS:
        raise StripeError(400, f"Invalid capture_method: {capture_method}", param="capture_method")

    customer_id = data.get("customer") or None
    if customer_id:
        customer = db.get(Customer, customer_id)
        if customer is None or customer.deleted:
            raise resource_missing("customer", customer_id)

    apm = data.get("automatic_payment_methods")
    apm_json = None
    payment_method_types = ["card"]
    if isinstance(apm, dict):
        enabled = as_bool(apm, "enabled")
        if enabled is None:
            raise missing_param("automatic_payment_methods[enabled]")
        apm_obj: dict = {"enabled": enabled}
        if "allow_redirects" in apm:
            apm_obj["allow_redirects"] = apm["allow_redirects"]
        apm_json = json.dumps(apm_obj)
        if enabled:
            payment_method_types = ["card", "link"]
    if isinstance(data.get("payment_method_types"), list):
        payment_method_types = data["payment_method_types"]

    pi_id = generate_id("pi")
    pi = PaymentIntent(
        id=pi_id,
        amount=amount,
        currency=currency,
        status="requires_payment_method",
        client_secret=client_secret_for(pi_id),
        customer_id=customer_id,
        description=data.get("description") or None,
        receipt_email=data.get("receipt_email") or None,
        capture_method=capture_method,
        confirmation_method=data.get("confirmation_method", "automatic"),
        setup_future_usage=data.get("setup_future_usage") or None,
        statement_descriptor=data.get("statement_descriptor") or None,
        statement_descriptor_suffix=data.get("statement_descriptor_suffix") or None,
        automatic_payment_methods_json=apm_json,
        payment_method_types_json=json.dumps(payment_method_types),
        shipping_json=json.dumps(data["shipping"]) if data.get("shipping") else None,
        metadata_json=_merge_metadata("{}", data.get("metadata")),
        created=int(time.time()),
    )
    if data.get("payment_method"):
        pm = resolve_payment_method(db, data["payment_method"])
        pi.payment_method_id = pm.id
        pi.status = "requires_confirmation"
    db.add(pi)
    db.flush()
    record_event(db, "payment_intent.created", payment_intent_to_dict(pi),
                 idempotency_key=request.headers.get("idempotency-key"))
    db.commit()

    if as_bool(data, "confirm", default=False):
        _do_confirm(db, pi, data, request)

    return apply_expand(db, payment_intent_to_dict(pi), "payment_intent", data.get("expand"))


@router.get("/v1/payment_intents")
def list_payment_intents(request: Request, db: Session = Depends(get_db)):
    params = parse_query(request)
    items = db.query(PaymentIntent).order_by(PaymentIntent.seq.desc()).all()
    if params.get("customer"):
        items = [pi for pi in items if pi.customer_id == params["customer"]]
    items = apply_created_filter(items, params)
    envelope = paginate(items, params, "/v1/payment_intents", payment_intent_to_dict, kind="payment_intent")
    return apply_list_expand(db, envelope, "payment_intent", params.get("expand"))


@router.get("/v1/payment_intents/{pi_id}")
def get_payment_intent(pi_id: str, request: Request, db: Session = Depends(get_db)):
    params = parse_query(request)
    pi = _get_pi_or_404(db, pi_id)
    return apply_expand(db, payment_intent_to_dict(pi), "payment_intent", params.get("expand"))


@router.post("/v1/payment_intents/{pi_id}")
async def update_payment_intent(pi_id: str, request: Request, db: Session = Depends(get_db)):
    data = await read_body(request)
    check_unknown_params(data, _UPDATE_PARAMS)
    pi = _get_pi_or_404(db, pi_id)

    if "amount" in data:
        if pi.status not in ("requires_payment_method", "requires_confirmation"):
            raise StripeError(
                400,
                f"You cannot update the amount of a PaymentIntent with a status of {pi.status}.",
                code="payment_intent_unexpected_state",
            )
        amount = as_int(data, "amount", required=True)
        if amount is None or amount <= 0:
            raise StripeError(400, "This value must be greater than or equal to 1.", param="amount")
        pi.amount = amount
    if "currency" in data and data["currency"]:
        pi.currency = str(data["currency"]).lower()
    if "customer" in data:
        customer_id = data["customer"] or None
        if customer_id:
            customer = db.get(Customer, customer_id)
            if customer is None or customer.deleted:
                raise resource_missing("customer", customer_id)
        pi.customer_id = customer_id
    if "payment_method" in data:
        if data["payment_method"]:
            pm = resolve_payment_method(db, data["payment_method"])
            pi.payment_method_id = pm.id
            if pi.status == "requires_payment_method":
                pi.status = "requires_confirmation"
        else:
            pi.payment_method_id = None
    if "description" in data:
        pi.description = data["description"] or None
    if "receipt_email" in data:
        pi.receipt_email = data["receipt_email"] or None
    if "capture_method" in data and data["capture_method"]:
        if data["capture_method"] not in _CAPTURE_METHODS:
            raise StripeError(400, f"Invalid capture_method: {data['capture_method']}", param="capture_method")
        pi.capture_method = data["capture_method"]
    if "setup_future_usage" in data:
        pi.setup_future_usage = data["setup_future_usage"] or None
    if "shipping" in data:
        pi.shipping_json = json.dumps(data["shipping"]) if data["shipping"] else None
    if "statement_descriptor" in data:
        pi.statement_descriptor = data["statement_descriptor"] or None
    if "statement_descriptor_suffix" in data:
        pi.statement_descriptor_suffix = data["statement_descriptor_suffix"] or None
    if "metadata" in data:
        pi.metadata_json = _merge_metadata(pi.metadata_json, data["metadata"])

    db.commit()
    return apply_expand(db, payment_intent_to_dict(pi), "payment_intent", data.get("expand"))


@router.post("/v1/payment_intents/{pi_id}/confirm")
async def confirm_payment_intent(pi_id: str, request: Request, db: Session = Depends(get_db)):
    data = await read_body(request)
    check_unknown_params(data, _CONFIRM_PARAMS)
    pi = _get_pi_or_404(db, pi_id)
    _do_confirm(db, pi, data, request)
    return apply_expand(db, payment_intent_to_dict(pi), "payment_intent", data.get("expand"))


@router.post("/v1/payment_intents/{pi_id}/_complete_authentication")
async def complete_authentication(pi_id: str, request: Request, db: Session = Depends(get_db)):
    """MOCK-ONLY: complete (or fail) a pending 3DS/SCA challenge.

    Real Stripe completes authentication via Stripe.js / the mobile SDKs in
    the customer's browser; a server-side mock has no browser, so this
    endpoint stands in for the customer finishing the challenge. Documented
    as a divergence in API_NOTES.md.

    Body: `succeed=true|false` (default true).
      succeed=true  -> succeeded (or requires_capture when capture_method=manual)
                       + charge + the usual events
      succeed=false -> requires_payment_method + last_payment_error
                       authentication_required + failed charge
    Returns the updated PaymentIntent (HTTP 200 either way).
    """
    data = await read_body(request)
    check_unknown_params(data, {"succeed"})
    pi = _get_pi_or_404(db, pi_id)
    idem = request.headers.get("idempotency-key")

    if pi.status != "requires_action":
        raise StripeError(
            400,
            f"You cannot complete authentication for this PaymentIntent because "
            f"it has a status of {pi.status}. Only a PaymentIntent with one of "
            f"the following statuses may complete authentication: requires_action.",
            code="payment_intent_unexpected_state",
        )

    succeed = as_bool(data, "succeed", default=True)
    pm = db.get(PaymentMethod, pi.payment_method_id) if pi.payment_method_id else None
    if pm is None:
        raise StripeError(500, "Internal mock inconsistency: missing payment method "
                               "for authentication.", type="api_error")

    if succeed:
        _finalize_success(db, pi, pm, idem, three_d_secure=True)
    else:
        _fail_authentication(db, pi, pm, idem)
    return apply_expand(db, payment_intent_to_dict(pi), "payment_intent", data.get("expand"))


@router.post("/v1/payment_intents/{pi_id}/capture")
async def capture_payment_intent(pi_id: str, request: Request, db: Session = Depends(get_db)):
    data = await read_body(request)
    check_unknown_params(data, _CAPTURE_PARAMS)
    pi = _get_pi_or_404(db, pi_id)
    idem = request.headers.get("idempotency-key")

    if pi.status != "requires_capture":
        raise StripeError(
            400,
            f"This PaymentIntent could not be captured because it has a status of "
            f"{pi.status}. Only a PaymentIntent with one of the following statuses "
            f"may be captured: requires_capture.",
            code="payment_intent_unexpected_state",
        )

    amount_to_capture = as_int(data, "amount_to_capture", default=pi.amount_capturable)
    if amount_to_capture is None or amount_to_capture < 1 or amount_to_capture > pi.amount_capturable:
        raise StripeError(
            400,
            f"Amount to capture must be greater than 0 and less than or equal to the "
            f"capturable amount ({pi.amount_capturable}).",
            param="amount_to_capture",
        )

    ch = db.get(Charge, pi.latest_charge_id) if pi.latest_charge_id else None
    if ch is None:
        raise StripeError(500, "Internal mock inconsistency: missing charge for capture.", type="api_error")

    ch.captured = True
    ch.amount_captured = amount_to_capture
    ch.balance_transaction_id = create_charge_balance_transaction(
        db, charge_id=ch.id, amount=amount_to_capture, currency=ch.currency
    ).id

    remainder = pi.amount - amount_to_capture
    if remainder > 0:
        # Real semantics: the uncaptured remainder is released and surfaced as a
        # Refund with no balance transaction (those funds were never available).
        refund = Refund(
            id=generate_id("re"),
            amount=remainder,
            currency=pi.currency,
            charge_id=ch.id,
            payment_intent_id=pi.id,
            balance_transaction_id=None,
            status="succeeded",
            reason=None,
            created=int(time.time()),
        )
        db.add(refund)
        ch.amount_refunded = remainder
        db.flush()
        from .serializers import refund_to_dict
        record_event(db, "refund.created", refund_to_dict(refund), idempotency_key=idem)

    if "metadata" in data:
        pi.metadata_json = _merge_metadata(pi.metadata_json, data["metadata"])
        ch.metadata_json = pi.metadata_json
    pi.status = "succeeded"
    pi.amount_received = amount_to_capture
    pi.amount_capturable = 0
    db.flush()
    record_event(db, "charge.captured", charge_to_dict(ch, db), idempotency_key=idem)
    record_event(db, "payment_intent.succeeded", payment_intent_to_dict(pi), idempotency_key=idem)
    db.commit()
    return apply_expand(db, payment_intent_to_dict(pi), "payment_intent", data.get("expand"))


@router.post("/v1/payment_intents/{pi_id}/cancel")
async def cancel_payment_intent(pi_id: str, request: Request, db: Session = Depends(get_db)):
    data = await read_body(request)
    check_unknown_params(data, {"cancellation_reason"})
    pi = _get_pi_or_404(db, pi_id)
    idem = request.headers.get("idempotency-key")

    if pi.status not in _CANCELABLE:
        raise StripeError(
            400,
            f"You cannot cancel this PaymentIntent because it has a status of "
            f"{pi.status}. Only a PaymentIntent with one of the following statuses "
            f"may be canceled: requires_payment_method, requires_capture, "
            f"requires_confirmation, requires_action, processing.",
            code="payment_intent_unexpected_state",
        )

    reason = data.get("cancellation_reason")
    if reason is not None and reason != "" and reason not in _CANCEL_REASONS:
        raise StripeError(
            400,
            "Invalid cancellation_reason: must be one of duplicate, fraudulent, "
            "requested_by_customer, or abandoned",
            param="cancellation_reason",
        )

    if pi.status == "requires_capture" and pi.latest_charge_id:
        # Release the uncaptured authorization: full refund, no balance txn.
        ch = db.get(Charge, pi.latest_charge_id)
        if ch is not None:
            refund = Refund(
                id=generate_id("re"),
                amount=pi.amount_capturable or pi.amount,
                currency=pi.currency,
                charge_id=ch.id,
                payment_intent_id=pi.id,
                balance_transaction_id=None,
                status="succeeded",
                reason=None,
                created=int(time.time()),
            )
            db.add(refund)
            ch.amount_refunded = refund.amount
            ch.refunded = True
            db.flush()
            from .serializers import refund_to_dict
            record_event(db, "refund.created", refund_to_dict(refund), idempotency_key=idem)

    pi.status = "canceled"
    pi.canceled_at = int(time.time())
    pi.cancellation_reason = reason or None
    pi.amount_capturable = 0
    pi.next_action_json = None
    db.flush()
    record_event(db, "payment_intent.canceled", payment_intent_to_dict(pi), idempotency_key=idem)
    db.commit()
    return apply_expand(db, payment_intent_to_dict(pi), "payment_intent", data.get("expand"))
