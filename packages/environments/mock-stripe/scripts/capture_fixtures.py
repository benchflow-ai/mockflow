#!/usr/bin/env python3
"""Capture golden fixtures from the REAL Stripe API.

Usage:
    STRIPE_SECRET_KEY=sk_test_... python scripts/capture_fixtures.py

Without STRIPE_SECRET_KEY this exits gracefully (status 0) — the committed
fixtures, authored from docs.stripe.com reference examples, remain in place
(see tests/fixtures/real_stripe/_capture_metadata.json for provenance).

With a key it creates test objects against api.stripe.com (test mode),
captures every fixture, cleans up after itself, and rewrites
_capture_metadata.json with the real capture provenance.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import httpx

API_BASE = "https://api.stripe.com"
FIXTURES_DIR = Path(__file__).parent.parent / "tests" / "fixtures" / "real_stripe"

KEY = os.environ.get("STRIPE_SECRET_KEY", "").strip()

_captured: list[str] = []


def save(name: str, data) -> None:
    FIXTURES_DIR.mkdir(parents=True, exist_ok=True)
    if isinstance(data, dict):
        data["_captured_at"] = datetime.now(timezone.utc).isoformat()
    (FIXTURES_DIR / f"{name}.json").write_text(json.dumps(data, indent=2, default=str))
    _captured.append(f"{name}.json")
    print(f"  Saved {name}.json")


def main() -> int:
    if not KEY:
        print("STRIPE_SECRET_KEY not set — skipping live capture.")
        print("The committed fixtures (authored from docs.stripe.com reference examples)")
        print("remain in place. Set STRIPE_SECRET_KEY=sk_test_... to overwrite them with")
        print("real captures.")
        return 0

    if KEY.startswith("sk_live_"):
        print("Refusing to run against a LIVE key. Use a sk_test_ key.", file=sys.stderr)
        return 1

    client = httpx.Client(
        base_url=API_BASE,
        headers={"Authorization": f"Bearer {KEY}"},
        timeout=30.0,
    )

    def post(path: str, data: dict | None = None, ok: bool = True) -> httpx.Response:
        r = client.post(path, data=data or {})
        if ok:
            r.raise_for_status()
        return r

    def get(path: str, params: dict | None = None, ok: bool = True) -> httpx.Response:
        r = client.get(path, params=params or {})
        if ok:
            r.raise_for_status()
        return r

    customer_id = None
    product_id = None
    price_id = None
    webhook_endpoint_id = None

    try:
        print("Capturing fixtures from real Stripe (test mode)...")

        # --- Customers ---
        r = post("/v1/customers", {"name": "Jenny Rosen", "email": "jennyrosen@example.com"})
        customer = r.json()
        customer_id = customer["id"]
        save("customer_create", customer)
        save("customer_retrieve", get(f"/v1/customers/{customer_id}").json())
        save("customers_list", get("/v1/customers", {"limit": 1}).json())

        # --- PaymentMethods (attach/detach) ---
        pm = post("/v1/payment_methods/pm_card_visa/attach", {"customer": customer_id}).json()
        save("payment_method_attach", pm)
        save("payment_method_detach", post(f"/v1/payment_methods/{pm['id']}/detach").json())

        # --- PaymentIntents: create -> confirm -> refund ---
        pi = post("/v1/payment_intents", {
            "amount": "2000", "currency": "usd",
            "automatic_payment_methods[enabled]": "true",
            "automatic_payment_methods[allow_redirects]": "never",
        }).json()
        save("payment_intent_create", pi)
        confirmed = post(f"/v1/payment_intents/{pi['id']}/confirm",
                         {"payment_method": "pm_card_visa"}).json()
        save("payment_intent_confirm", confirmed)

        charge_id = confirmed["latest_charge"]
        save("charge", get(f"/v1/charges/{charge_id}").json())
        save("charges_list", get("/v1/charges", {"limit": 1}).json())

        refund = post("/v1/refunds", {"charge": charge_id}).json()
        save("refund", refund)
        if refund.get("balance_transaction"):
            save("balance_transaction",
                 get(f"/v1/balance_transactions/{refund['balance_transaction']}").json())

        # --- Manual capture flow ---
        hold = post("/v1/payment_intents", {
            "amount": "1000", "currency": "usd", "capture_method": "manual",
            "payment_method": "pm_card_visa", "confirm": "true",
            "automatic_payment_methods[enabled]": "true",
            "automatic_payment_methods[allow_redirects]": "never",
        }).json()
        save("payment_intent_capture",
             post(f"/v1/payment_intents/{hold['id']}/capture").json())

        # --- Cancel flow ---
        cancelme = post("/v1/payment_intents", {
            "amount": "2000", "currency": "usd",
            "automatic_payment_methods[enabled]": "true",
            "automatic_payment_methods[allow_redirects]": "never",
        }).json()
        save("payment_intent_cancel",
             post(f"/v1/payment_intents/{cancelme['id']}/cancel").json())

        # --- 3DS: requires_action PaymentIntent ---
        tds = post("/v1/payment_intents", {
            "amount": "2000", "currency": "usd",
            "automatic_payment_methods[enabled]": "true",
            "automatic_payment_methods[allow_redirects]": "never",
        }).json()
        r = post(f"/v1/payment_intents/{tds['id']}/confirm",
                 {"payment_method": "pm_card_authenticationRequired"}, ok=False)
        if r.status_code == 200 and r.json().get("status") == "requires_action":
            save("payment_intent_requires_action", r.json())
        post(f"/v1/payment_intents/{tds['id']}/cancel", ok=False)

        # --- Webhook endpoint (create carries the whsec_ secret) ---
        we = post("/v1/webhook_endpoints", {
            "url": "https://example.com/my/webhook/endpoint",
            "enabled_events[]": "charge.succeeded",
        }).json()
        webhook_endpoint_id = we["id"]
        save("webhook_endpoint", we)

        # --- Products / Prices ---
        product = post("/v1/products", {"name": "Gold Plan"}).json()
        product_id = product["id"]
        save("product", product)
        price = post("/v1/prices", {
            "currency": "usd", "unit_amount": "1000", "product": product_id,
            "recurring[interval]": "month",
        }).json()
        price_id = price["id"]
        save("price", price)

        # --- Balance / Events ---
        save("balance", get("/v1/balance").json())
        events = get("/v1/events", {"type": "customer.created", "limit": 1}).json()
        if events.get("data"):
            save("event", events["data"][0])

        # --- Errors ---
        r = get("/v1/customers/cus_unknown", ok=False)
        save("error_resource_missing", r.json())

        bad = httpx.get(f"{API_BASE}/v1/customers",
                        headers={"Authorization": "Bearer sk_test_invalid_key_for_capture"})
        save("error_invalid_api_key", bad.json())

        decline_pi = post("/v1/payment_intents", {
            "amount": "900", "currency": "usd",
            "automatic_payment_methods[enabled]": "true",
            "automatic_payment_methods[allow_redirects]": "never",
        }).json()
        r = post(f"/v1/payment_intents/{decline_pi['id']}/confirm",
                 {"payment_method": "pm_card_visa_chargeDeclined"}, ok=False)
        save("error_card_declined", r.json())
        post(f"/v1/payment_intents/{decline_pi['id']}/cancel", ok=False)

        # --- Metadata ---
        meta = {
            "captured_at": datetime.now(timezone.utc).isoformat(),
            "account": "(stripe test-mode account for key sk_test_...)",
            "api_version": "account default",
            "api_base": f"{API_BASE}/v1",
            "auth_method": "Bearer sk_test_ secret key via STRIPE_SECRET_KEY env var",
            "capture_script": "scripts/capture_fixtures.py",
            "fixture_count": len(_captured),
            "note": "Live capture from the real Stripe API (test mode). "
                    "Test objects were created and cleaned up by the script.",
        }
        (FIXTURES_DIR / "_capture_metadata.json").write_text(json.dumps(meta, indent=2))
        print(f"Done: {len(_captured)} fixtures captured.")
        return 0

    finally:
        # --- Cleanup ---
        print("Cleaning up test objects...")
        try:
            if price_id:
                post(f"/v1/prices/{price_id}", {"active": "false"}, ok=False)
            if product_id:
                # products with prices can't be deleted; deactivate instead
                r = client.delete(f"/v1/products/{product_id}")
                if r.status_code >= 400:
                    post(f"/v1/products/{product_id}", {"active": "false"}, ok=False)
            if customer_id:
                client.delete(f"/v1/customers/{customer_id}")
            if webhook_endpoint_id:
                client.delete(f"/v1/webhook_endpoints/{webhook_endpoint_id}")
        except Exception as exc:  # pragma: no cover
            print(f"WARNING: cleanup incomplete ({exc}) — check the Stripe test dashboard.",
                  file=sys.stderr)
        client.close()


if __name__ == "__main__":
    sys.exit(main())
