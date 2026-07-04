"""Conformance tests: mock response *shapes* vs golden fixtures.

Fixtures live in tests/fixtures/real_stripe/. They were authored from
docs.stripe.com reference examples (see _capture_metadata.json — no live
capture was possible). `strict=True` asserts exact key parity; `strict=False`
is used where the mock intentionally carries extra keys (documented in
API_NOTES.md) or where the doc example comes from an older API version.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from mock_stripe.seed.generator import DEFAULT_API_KEY

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "real_stripe"

AUTH = {"Authorization": f"Bearer {DEFAULT_API_KEY}"}
FORM = {"Content-Type": "application/x-www-form-urlencoded"}


def load_fixture(name: str) -> dict:
    path = FIXTURES_DIR / name
    if not path.exists():
        pytest.skip(f"Golden fixture {name} not found")
    data = json.loads(path.read_text())
    data.pop("_captured_at", None)
    return data


def _assert_shape(real, mock, path="", strict=True):
    """Recursively assert mock response shape matches real fixture.

    - Missing keys: real_keys - mock_keys (always)
    - Extra keys: mock_keys - real_keys (when strict=True)
    - Type mismatches at leaf nodes (skipped when either side is null)
    """
    if isinstance(real, dict) and isinstance(mock, dict):
        missing = set(real) - set(mock)
        assert not missing, f"Mock MISSING keys at {path or 'root'}: {missing}"
        if strict:
            extra = set(mock) - set(real)
            assert not extra, f"Mock has EXTRA keys at {path or 'root'}: {extra}"
        for key in set(real) & set(mock):
            _assert_shape(real[key], mock[key], f"{path}.{key}" if path else key, strict)
    elif isinstance(real, list) and isinstance(mock, list):
        if real and mock:
            _assert_shape(real[0], mock[0], f"{path}[0]", strict)
    else:
        if real is not None and mock is not None:
            assert type(real).__name__ == type(mock).__name__, (
                f"TYPE MISMATCH at {path}: real={type(real).__name__} "
                f"mock={type(mock).__name__}"
            )


def _confirmed_pi(client, body="amount=2000&currency=usd&automatic_payment_methods[enabled]=true"):
    pi = client.post("/v1/payment_intents", headers={**AUTH, **FORM}, content=body).json()
    return client.post(
        f"/v1/payment_intents/{pi['id']}/confirm", headers=AUTH,
        data={"payment_method": "pm_card_visa"},
    ).json()


class TestCustomerConformance:
    def test_customer_create_shape(self, client):
        real = load_fixture("customer_create.json")
        mock = client.post(
            "/v1/customers", headers=AUTH,
            data={"name": "Jenny Rosen", "email": "jennyrosen@example.com"},
        ).json()
        _assert_shape(real, mock, strict=True)
        assert set(real.keys()) == set(mock.keys())

    def test_customer_retrieve_shape(self, client):
        real = load_fixture("customer_retrieve.json")
        created = client.post("/v1/customers", headers=AUTH, data={"name": "R"}).json()
        mock = client.get(f"/v1/customers/{created['id']}", headers=AUTH).json()
        _assert_shape(real, mock, strict=True)

    def test_customer_delete_shape(self, client):
        real = load_fixture("customer_delete.json")
        created = client.post("/v1/customers", headers=AUTH, data={"name": "D"}).json()
        mock = client.delete(f"/v1/customers/{created['id']}", headers=AUTH).json()
        _assert_shape(real, mock, strict=True)
        assert mock["deleted"] is True

    def test_customers_list_shape(self, client):
        real = load_fixture("customers_list.json")
        mock = client.get("/v1/customers", headers=AUTH).json()
        _assert_shape(real, mock, strict=True)
        assert mock["object"] == "list"
        assert mock["url"] == "/v1/customers"


class TestPaymentIntentConformance:
    def test_create_shape_strict(self, client):
        real = load_fixture("payment_intent_create.json")
        mock = client.post(
            "/v1/payment_intents", headers={**AUTH, **FORM},
            content="amount=2000&currency=usd&automatic_payment_methods[enabled]=true",
        ).json()
        _assert_shape(real, mock, strict=True)
        assert set(real.keys()) == set(mock.keys())

    def test_confirm_shape(self, client):
        real = load_fixture("payment_intent_confirm.json")
        mock = _confirmed_pi(client)
        _assert_shape(real, mock, strict=True)
        assert mock["status"] == "succeeded"

    def test_capture_shape(self, client):
        # Doc example is from an older API version: it includes a `redaction`
        # key and omits `source` — see API_NOTES.md "API Quirks".
        real = load_fixture("payment_intent_capture.json")
        real.pop("redaction", None)
        pi = client.post(
            "/v1/payment_intents", headers={**AUTH, **FORM},
            content="amount=1000&currency=usd&capture_method=manual"
                    "&payment_method=pm_card_visa&confirm=true",
        ).json()
        mock = client.post(f"/v1/payment_intents/{pi['id']}/capture", headers=AUTH).json()
        _assert_shape(real, mock, strict=False)
        assert mock["status"] == "succeeded"
        assert mock["amount_received"] == 1000

    def test_cancel_shape_strict(self, client):
        real = load_fixture("payment_intent_cancel.json")
        pi = client.post(
            "/v1/payment_intents", headers={**AUTH, **FORM},
            content="amount=2000&currency=usd&automatic_payment_methods[enabled]=true",
        ).json()
        mock = client.post(f"/v1/payment_intents/{pi['id']}/cancel", headers=AUTH).json()
        _assert_shape(real, mock, strict=True)
        assert mock["status"] == "canceled"

    def test_requires_action_shape_strict(self, client):
        # 3DS card: confirm -> requires_action with a use_stripe_sdk next_action.
        real = load_fixture("payment_intent_requires_action.json")
        pi = client.post(
            "/v1/payment_intents", headers={**AUTH, **FORM},
            content="amount=2000&currency=usd&automatic_payment_methods[enabled]=true",
        ).json()
        mock = client.post(
            f"/v1/payment_intents/{pi['id']}/confirm", headers=AUTH,
            data={"payment_method": "pm_card_authenticationRequired"},
        ).json()
        _assert_shape(real, mock, strict=True)
        assert mock["status"] == "requires_action"
        assert mock["next_action"]["type"] == "use_stripe_sdk"
        assert set(mock["next_action"]["use_stripe_sdk"]) == set(
            real["next_action"]["use_stripe_sdk"]
        )


class TestChargeConformance:
    def test_charge_shape(self, client):
        # Mock carries an extra `refunds` sublist (older-API convenience field,
        # see API_NOTES.md) -> strict=False; no fixture key may be missing.
        real = load_fixture("charge.json")
        pi = _confirmed_pi(client, body="amount=1099&currency=usd")
        mock = client.get(f"/v1/charges/{pi['latest_charge']}", headers=AUTH).json()
        _assert_shape(real, mock, strict=False)
        extra = set(mock) - set(real)
        assert extra == {"refunds"}

    def test_charges_list_shape(self, client):
        real = load_fixture("charges_list.json")
        mock = client.get("/v1/charges", headers=AUTH).json()
        _assert_shape(real, mock, strict=False)
        assert set(real.keys()) == set(mock.keys())  # envelope itself is exact


class TestRefundConformance:
    def test_refund_shape_strict(self, client):
        real = load_fixture("refund.json")
        pi = _confirmed_pi(client, body="amount=1000&currency=usd")
        mock = client.post("/v1/refunds", headers=AUTH,
                           data={"charge": pi["latest_charge"]}).json()
        _assert_shape(real, mock, strict=True)
        assert mock["status"] == "succeeded"


class TestPaymentMethodConformance:
    def test_attach_shape_strict(self, client):
        real = load_fixture("payment_method_attach.json")
        customer = client.post("/v1/customers", headers=AUTH, data={"name": "PM"}).json()
        pm = client.post(
            "/v1/payment_methods", headers={**AUTH, **FORM},
            content="type=card&card[number]=4242424242424242&card[cvc]=123",
        ).json()
        mock = client.post(f"/v1/payment_methods/{pm['id']}/attach", headers=AUTH,
                           data={"customer": customer["id"]}).json()
        _assert_shape(real, mock, strict=True)
        assert mock["customer"] == customer["id"]

    def test_detach_shape_strict(self, client):
        real = load_fixture("payment_method_detach.json")
        customer = client.post("/v1/customers", headers=AUTH, data={"name": "PM2"}).json()
        pm = client.post("/v1/payment_methods", headers=AUTH, data={"type": "card"}).json()
        client.post(f"/v1/payment_methods/{pm['id']}/attach", headers=AUTH,
                    data={"customer": customer["id"]})
        mock = client.post(f"/v1/payment_methods/{pm['id']}/detach", headers=AUTH).json()
        _assert_shape(real, mock, strict=True)
        assert mock["customer"] is None


class TestProductPriceConformance:
    def test_product_shape_strict(self, client):
        real = load_fixture("product.json")
        mock = client.post("/v1/products", headers=AUTH, data={"name": "Gold Plan"}).json()
        _assert_shape(real, mock, strict=True)
        assert set(real.keys()) == set(mock.keys())

    def test_price_shape_strict(self, client):
        real = load_fixture("price.json")
        product = client.post("/v1/products", headers=AUTH, data={"name": "Gold Plan"}).json()
        mock = client.post(
            "/v1/prices", headers={**AUTH, **FORM},
            content=f"currency=usd&unit_amount=1000&product={product['id']}"
                    "&recurring[interval]=month",
        ).json()
        _assert_shape(real, mock, strict=True)
        assert set(real.keys()) == set(mock.keys())


class TestBalanceConformance:
    def test_balance_shape_strict(self, client):
        real = load_fixture("balance.json")
        mock = client.get("/v1/balance", headers=AUTH).json()
        _assert_shape(real, mock, strict=True)
        assert set(real.keys()) == set(mock.keys())

    def test_balance_transaction_shape_strict(self, client):
        real = load_fixture("balance_transaction.json")
        pi = _confirmed_pi(client, body="amount=1000&currency=usd")
        ch = client.get(f"/v1/charges/{pi['latest_charge']}", headers=AUTH).json()
        mock = client.get(
            f"/v1/balance_transactions/{ch['balance_transaction']}", headers=AUTH
        ).json()
        _assert_shape(real, mock, strict=True)
        assert set(real.keys()) == set(mock.keys())


class TestWebhookEndpointConformance:
    def test_webhook_endpoint_create_shape_strict(self, client):
        # The create response is the ONLY one that carries `secret`.
        real = load_fixture("webhook_endpoint.json")
        mock = client.post(
            "/v1/webhook_endpoints", headers={**AUTH, **FORM},
            content="url=https://example.com/my/webhook/endpoint"
                    "&enabled_events[]=charge.succeeded&enabled_events[]=charge.failed",
        ).json()
        _assert_shape(real, mock, strict=True)
        assert set(real.keys()) == set(mock.keys())
        assert mock["secret"].startswith("whsec_")
        # retrieve drops the secret (real behavior)
        got = client.get(f"/v1/webhook_endpoints/{mock['id']}", headers=AUTH).json()
        assert set(got.keys()) == set(real.keys()) - {"secret"}


class TestEventConformance:
    def test_event_shape(self, client):
        real = load_fixture("event.json")
        created = client.post("/v1/customers", headers=AUTH, data={"name": "Evt"}).json()
        events = client.get("/v1/events?type=customer.created", headers=AUTH).json()
        mock = [e for e in events["data"] if e["data"]["object"]["id"] == created["id"]][0]
        # data.object in the fixture is a truncated snapshot; the mock embeds the
        # full object -> strict=False below data, exact at the top level.
        assert set(real.keys()) == set(mock.keys())
        _assert_shape(real, mock, strict=False)


class TestErrorConformance:
    def test_resource_missing_shape_strict(self, client):
        real = load_fixture("error_resource_missing.json")
        mock = client.get("/v1/customers/cus_unknown", headers=AUTH)
        assert mock.status_code == 404
        _assert_shape(real, mock.json(), strict=True)
        assert mock.json()["error"]["message"] == real["error"]["message"]

    def test_card_declined_shape(self, client):
        # Mock adds payment_intent/payment_method objects (real confirm errors
        # carry them too; doc example omits them) -> strict=False.
        real = load_fixture("error_card_declined.json")
        pi = client.post("/v1/payment_intents", headers={**AUTH, **FORM},
                         content="amount=900&currency=usd").json()
        mock = client.post(f"/v1/payment_intents/{pi['id']}/confirm", headers=AUTH,
                           data={"payment_method": "pm_card_visa_chargeDeclined"})
        assert mock.status_code == 402
        _assert_shape(real, mock.json(), strict=False)
        err = mock.json()["error"]
        assert err["type"] == "card_error"
        assert err["code"] == "card_declined"
        assert err["decline_code"] == "generic_decline"

    def test_invalid_api_key_shape(self, client):
        # Mock adds code="api_key_invalid" (documented divergence) -> strict=False.
        real = load_fixture("error_invalid_api_key.json")
        mock = client.get("/v1/customers", headers={"Authorization": "Bearer sk_test_bad"})
        assert mock.status_code == 401
        _assert_shape(real, mock.json(), strict=False)
        assert mock.json()["error"]["message"].startswith("Invalid API Key provided")
