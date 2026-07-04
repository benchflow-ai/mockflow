"""Seed scenarios for the mock Stripe environment.

Scenarios:
- ``default``: 3 customers with attached cards, 2 products (+prices),
  4 succeeded PaymentIntents (+charges, balance transactions, events),
  1 partial refund, 1 requires_capture PaymentIntent. Deterministic via a
  seeded RNG (ids, timestamps anchored at a fixed epoch).
- ``fresh``: only the API key.
- ``task:<name>``: auto-discovered from ``tasks/<name>/data/stripe_seed.py``
  (module must define ``seed(db, rng, fake) -> dict``).

The default API key is ``sk_test_env_0_51deterministic``.
"""

from __future__ import annotations

import importlib.util
import json
import os
import pathlib
import random
import sys

from faker import Faker

from mock_stripe.api.ledger import fee_for_charge
from mock_stripe.api.serializers import (
    charge_to_dict,
    customer_to_dict,
    payment_intent_to_dict,
    payment_method_to_dict,
    price_to_dict,
    product_to_dict,
    refund_to_dict,
)
from mock_stripe.ids import client_secret_for, generate_id
from mock_stripe.models import (
    ApiKey,
    BalanceTransaction,
    Charge,
    Customer,
    Event,
    PaymentIntent,
    PaymentMethod,
    Price,
    Product,
    Refund,
    get_session_factory,
    init_db,
)
from mock_stripe import testcards

DEFAULT_API_KEY = "sk_test_env_0_51deterministic"

# Fixed anchor so seeded `created` timestamps are deterministic (2026-05-28 UTC-ish).
ANCHOR = 1_780_000_000
_DAY = 86_400

API_VERSION = "2026-05-27.dahlia"


def _event(db, rng, event_type: str, obj: dict, created: int):
    db.add(Event(
        id=generate_id("evt", rng=rng),
        type=event_type,
        api_version=API_VERSION,
        data_json=json.dumps({"object": obj}),
        request_idempotency_key=None,
        created=created,
    ))


def _seed_api_key(db, created: int = ANCHOR - 30 * _DAY) -> ApiKey:
    key = ApiKey(id=DEFAULT_API_KEY, name="default", livemode=False, created=created)
    db.add(key)
    return key


def _make_customer(db, rng, fake, *, name, email, created) -> Customer:
    customer = Customer(
        id=generate_id("cus", rng=rng),
        name=name,
        email=email,
        phone=None,
        description=None,
        invoice_prefix="".join(rng.choice("ABCDEFGH0123456789") for _ in range(8)),
        metadata_json="{}",
        created=created,
    )
    db.add(customer)
    _event(db, rng, "customer.created", customer_to_dict(customer), created)
    return customer


def _make_attached_card(db, rng, customer: Customer, number: str, created: int) -> PaymentMethod:
    spec = testcards.spec_for_number(number)
    pm = PaymentMethod(
        id=generate_id("pm", rng=rng),
        type="card",
        customer_id=customer.id,
        card_brand=spec["brand"],
        card_last4=spec["last4"],
        card_exp_month=rng.randint(1, 12),
        card_exp_year=rng.randint(2030, 2036),
        card_fingerprint=spec["fingerprint"],
        card_funding=spec["funding"],
        card_country=spec["country"],
        card_cvc_check="pass",
        metadata_json="{}",
        created=created,
    )
    db.add(pm)
    _event(db, rng, "payment_method.attached", payment_method_to_dict(pm), created)
    return pm


def _pm_details(pm: PaymentMethod) -> str:
    return json.dumps({
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
            "three_d_secure": None,
            "wallet": None,
        },
        "type": "card",
    })


def _make_succeeded_payment(db, rng, customer: Customer, pm: PaymentMethod,
                            *, amount: int, description: str, created: int,
                            captured: bool = True) -> tuple[PaymentIntent, Charge]:
    pi_id = generate_id("pi", rng=rng)
    pi = PaymentIntent(
        id=pi_id,
        amount=amount,
        currency="usd",
        status="succeeded" if captured else "requires_capture",
        client_secret=client_secret_for(pi_id, rng=rng),
        customer_id=customer.id,
        payment_method_id=pm.id,
        description=description,
        capture_method="automatic" if captured else "manual",
        amount_received=amount if captured else 0,
        amount_capturable=0 if captured else amount,
        payment_method_types_json='["card"]',
        metadata_json="{}",
        created=created,
    )
    db.add(pi)
    _event(db, rng, "payment_intent.created", payment_intent_to_dict(pi), created)

    ch_id = generate_id("ch", rng=rng)
    ch = Charge(
        id=ch_id,
        amount=amount,
        amount_captured=amount if captured else 0,
        amount_refunded=0,
        currency="usd",
        status="succeeded",
        paid=True,
        captured=captured,
        customer_id=customer.id,
        payment_intent_id=pi.id,
        payment_method_id=pm.id,
        description=description,
        receipt_url=f"https://pay.stripe.com/receipts/payment/{ch_id}",
        calculated_statement_descriptor="Stripe",
        outcome_json=json.dumps({
            "network_status": "approved_by_network",
            "reason": None,
            "risk_level": "normal",
            "risk_score": rng.randint(5, 64),
            "seller_message": "Payment complete.",
            "type": "authorized",
        }),
        payment_method_details_json=_pm_details(pm),
        metadata_json="{}",
        created=created,
    )
    db.add(ch)
    pi.latest_charge_id = ch.id

    if captured:
        fee = fee_for_charge(amount)
        txn = BalanceTransaction(
            id=generate_id("txn", rng=rng),
            amount=amount,
            currency="usd",
            fee=fee,
            net=amount - fee,
            type="charge",
            reporting_category="charge",
            source_id=ch.id,
            status="available",
            fee_details_json=json.dumps([{
                "amount": fee,
                "application": None,
                "currency": "usd",
                "description": "Stripe processing fees",
                "type": "stripe_fee",
            }]),
            available_on=created,
            created=created,
        )
        db.add(txn)
        ch.balance_transaction_id = txn.id
        _event(db, rng, "charge.succeeded", charge_to_dict(ch), created)
        _event(db, rng, "payment_intent.succeeded", payment_intent_to_dict(pi), created)
    else:
        _event(db, rng, "charge.succeeded", charge_to_dict(ch), created)
        _event(db, rng, "payment_intent.amount_capturable_updated", payment_intent_to_dict(pi), created)
    return pi, ch


def _make_refund(db, rng, ch: Charge, *, amount: int, created: int) -> Refund:
    refund = Refund(
        id=generate_id("re", rng=rng),
        amount=amount,
        currency=ch.currency,
        charge_id=ch.id,
        payment_intent_id=ch.payment_intent_id,
        status="succeeded",
        reason="requested_by_customer",
        metadata_json="{}",
        created=created,
    )
    db.add(refund)
    txn = BalanceTransaction(
        id=generate_id("txn", rng=rng),
        amount=-amount,
        currency=ch.currency,
        fee=0,
        net=-amount,
        type="refund",
        reporting_category="refund",
        source_id=refund.id,
        status="available",
        fee_details_json="[]",
        available_on=created,
        created=created,
    )
    db.add(txn)
    refund.balance_transaction_id = txn.id
    ch.amount_refunded += amount
    if ch.amount_refunded >= ch.amount:
        ch.refunded = True
    _event(db, rng, "refund.created", refund_to_dict(refund), created)
    _event(db, rng, "charge.refunded", charge_to_dict(ch), created)
    return refund


def seed_fresh_scenario(db, rng, fake) -> dict:
    """Only the API key — a pristine Stripe account."""
    _seed_api_key(db)
    return {"customers": 0, "payment_intents": 0}


def seed_default_scenario(db, rng, fake) -> dict:
    _seed_api_key(db)

    personas = [
        ("Ada Lovelace", "ada@example.com", "4242424242424242"),
        ("Grace Hopper", "grace@example.com", "5555555555554444"),
        ("Alan Turing", "alan@example.com", "378282246310005"),
    ]
    customers: list[Customer] = []
    cards: list[PaymentMethod] = []
    for i, (name, email, number) in enumerate(personas):
        created = ANCHOR - (14 - i) * _DAY
        customer = _make_customer(db, rng, fake, name=name, email=email, created=created)
        pm = _make_attached_card(db, rng, customer, number, created)
        customers.append(customer)
        cards.append(pm)

    # Products + prices
    now = ANCHOR - 12 * _DAY
    starter = Product(id=generate_id("prod", rng=rng), name="Starter Plan",
                      description="Monthly starter subscription", created=now, updated=now)
    db.add(starter)
    _event(db, rng, "product.created", product_to_dict(starter), now)
    starter_price = Price(
        id=generate_id("price", rng=rng),
        product_id=starter.id,
        currency="usd",
        unit_amount=999,
        unit_amount_decimal="999",
        type="recurring",
        recurring_json=json.dumps({
            "interval": "month", "interval_count": 1,
            "trial_period_days": None, "usage_type": "licensed",
        }),
        created=now,
    )
    db.add(starter_price)
    _event(db, rng, "price.created", price_to_dict(starter_price), now)
    starter.default_price_id = starter_price.id

    widget = Product(id=generate_id("prod", rng=rng), name="Pro Widget",
                     description="One-time purchase widget", created=now, updated=now)
    db.add(widget)
    _event(db, rng, "product.created", product_to_dict(widget), now)
    widget_price = Price(
        id=generate_id("price", rng=rng),
        product_id=widget.id,
        currency="usd",
        unit_amount=2500,
        unit_amount_decimal="2500",
        type="one_time",
        created=now,
    )
    db.add(widget_price)
    _event(db, rng, "price.created", price_to_dict(widget_price), now)
    widget.default_price_id = widget_price.id

    # 4 succeeded payments
    payments = [
        (customers[0], cards[0], 1099, "Starter Plan subscription", ANCHOR - 9 * _DAY),
        (customers[1], cards[1], 2500, "Pro Widget", ANCHOR - 7 * _DAY),
        (customers[2], cards[2], 999, "Starter Plan subscription", ANCHOR - 5 * _DAY),
        (customers[0], cards[0], 4200, "Custom invoice", ANCHOR - 3 * _DAY),
    ]
    charges: list[Charge] = []
    for customer, pm, amount, description, created in payments:
        _, ch = _make_succeeded_payment(
            db, rng, customer, pm, amount=amount, description=description, created=created
        )
        charges.append(ch)

    # 1 partial refund on the Pro Widget charge
    _make_refund(db, rng, charges[1], amount=500, created=ANCHOR - 6 * _DAY)

    # 1 uncaptured (requires_capture) payment
    _make_succeeded_payment(
        db, rng, customers[1], cards[1], amount=7500,
        description="Hold for equipment rental", created=ANCHOR - 1 * _DAY,
        captured=False,
    )

    return {
        "customers": len(customers),
        "payment_methods": len(cards),
        "products": 2,
        "prices": 2,
        "payment_intents": 5,
        "charges": 5,
        "refunds": 1,
    }


SCENARIOS = {
    "default": seed_default_scenario,
    "fresh": seed_fresh_scenario,
}


def _make_task_scenario(task_dir_name: str):
    def _scenario(db, rng, fake) -> dict:
        seed_path = _harbor_dir() / task_dir_name / "data" / "stripe_seed.py"
        module_name = f"mock_stripe_task_seed_{task_dir_name.replace('-', '_')}"
        spec = importlib.util.spec_from_file_location(module_name, seed_path)
        mod = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = mod
        spec.loader.exec_module(mod)
        _seed_api_key(db)
        return mod.seed(db, rng, fake) or {}

    return _scenario


def _harbor_dir() -> pathlib.Path:
    if "TASKS_DIR" in os.environ:
        return pathlib.Path(os.environ["TASKS_DIR"])
    return pathlib.Path(__file__).resolve().parents[5] / "tasks"


def _discover_task_scenarios():
    harbor = _harbor_dir()
    if not harbor.is_dir():
        return
    for task_dir in sorted(harbor.iterdir()):
        if task_dir.is_dir() and (task_dir / "data" / "stripe_seed.py").exists():
            SCENARIOS[f"task:{task_dir.name}"] = _make_task_scenario(task_dir.name)


_discover_task_scenarios()


def seed_database(scenario: str = "default", seed: int = 42, db_path=None, **_kwargs) -> dict:
    """Single entry point used by CLI seed, /_admin/seed, and tests."""
    rng = random.Random(seed)
    random.seed(seed)
    fake = Faker()
    Faker.seed(seed)

    init_db(db_path)
    SessionLocal = get_session_factory(db_path)
    db = SessionLocal()
    try:
        scenario_fn = SCENARIOS.get(scenario)
        if not scenario_fn:
            raise ValueError(
                f"Unknown scenario: {scenario!r}. Available: {sorted(SCENARIOS.keys())}"
            )
        result = scenario_fn(db, rng, fake)
        db.commit()
        from mock_stripe.state.snapshots import take_snapshot
        take_snapshot("initial")
        return {"scenario": scenario, "api_key": DEFAULT_API_KEY, **(result or {})}
    finally:
        db.close()
