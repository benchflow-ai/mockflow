"""Functional tests for the mock Stripe API.

Covers: auth, the bracket-notation form parser, every resource endpoint, the
PaymentIntent status machine (incl. declines), idempotency, pagination
cursors, expand[], and balance math.
"""

from __future__ import annotations

import base64


from mock_stripe.api.forms import parse_form, split_key, unflatten
from mock_stripe.api.ledger import fee_for_charge
from mock_stripe.seed.generator import DEFAULT_API_KEY

AUTH = {"Authorization": f"Bearer {DEFAULT_API_KEY}"}

FORM = {"Content-Type": "application/x-www-form-urlencoded"}


def _basic_auth_header(key: str) -> dict:
    token = base64.b64encode(f"{key}:".encode()).decode()
    return {"Authorization": f"Basic {token}"}


def _create_pi(client, body: str, headers=None) -> dict:
    r = client.post("/v1/payment_intents", headers={**AUTH, **FORM, **(headers or {})}, content=body)
    assert r.status_code == 200, r.text
    return r.json()


# ---------------------------------------------------------------------------
# Form parser (bracket notation)
# ---------------------------------------------------------------------------
class TestFormParser:
    def test_flat_pairs(self):
        assert parse_form("amount=2000&currency=usd") == {"amount": "2000", "currency": "usd"}

    def test_nested_bracket(self):
        assert parse_form("metadata[order_id]=6735") == {"metadata": {"order_id": "6735"}}

    def test_nested_bool_value_stays_string(self):
        assert parse_form("automatic_payment_methods[enabled]=true") == {
            "automatic_payment_methods": {"enabled": "true"}
        }

    def test_deep_nesting(self):
        assert parse_form("a[b][c][d]=1") == {"a": {"b": {"c": {"d": "1"}}}}

    def test_array_notation(self):
        assert parse_form("expand[]=latest_charge&expand[]=customer") == {
            "expand": ["latest_charge", "customer"]
        }

    def test_indexed_array_of_objects(self):
        parsed = parse_form("line_items[0][price]=price_a&line_items[1][price]=price_b")
        assert parsed == {"line_items": [{"price": "price_a"}, {"price": "price_b"}]}

    def test_indexed_array_out_of_order(self):
        parsed = parse_form("items[1]=b&items[0]=a&items[2]=c")
        assert parsed == {"items": ["a", "b", "c"]}

    def test_repeated_scalar_last_wins(self):
        assert parse_form("name=first&name=second") == {"name": "second"}

    def test_empty_value_kept(self):
        assert parse_form("metadata=&name=x") == {"metadata": "", "name": "x"}

    def test_url_encoding(self):
        assert parse_form("email=jenny%40example.com&name=Jenny+Rosen") == {
            "email": "jenny@example.com",
            "name": "Jenny Rosen",
        }

    def test_mixed_nesting_with_arrays(self):
        parsed = parse_form("card[number]=4242&expand[]=customer&metadata[a]=1&metadata[b]=2")
        assert parsed == {
            "card": {"number": "4242"},
            "expand": ["customer"],
            "metadata": {"a": "1", "b": "2"},
        }

    def test_malformed_brackets_treated_literally(self):
        assert split_key("a[b") == ["a[b"]
        assert split_key("a]b[") == ["a]b["]

    def test_split_key(self):
        assert split_key("a[b][c][]") == ["a", "b", "c", ""]

    def test_unflatten_pairs(self):
        assert unflatten([("a[x]", "1"), ("a[y]", "2")]) == {"a": {"x": "1", "y": "2"}}


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------
class TestAuth:
    def test_missing_key_401(self, client):
        r = client.get("/v1/customers")
        assert r.status_code == 401
        err = r.json()["error"]
        assert err["type"] == "invalid_request_error"
        assert "did not provide an API key" in err["message"]

    def test_unknown_key_401(self, client):
        r = client.get("/v1/customers", headers={"Authorization": "Bearer sk_test_wrongwrongwrong"})
        assert r.status_code == 401
        err = r.json()["error"]
        assert err["type"] == "invalid_request_error"
        assert err["code"] == "api_key_invalid"
        assert "Invalid API Key provided" in err["message"]

    def test_bearer_auth_ok(self, client):
        assert client.get("/v1/customers", headers=AUTH).status_code == 200

    def test_basic_auth_key_as_username(self, client):
        r = client.get("/v1/customers", headers=_basic_auth_header(DEFAULT_API_KEY))
        assert r.status_code == 200

    def test_basic_auth_bad_key(self, client):
        r = client.get("/v1/customers", headers=_basic_auth_header("sk_test_nope"))
        assert r.status_code == 401

    def test_health_needs_no_auth(self, client):
        assert client.get("/health").json() == {"status": "ok"}

    def test_admin_needs_no_auth(self, client):
        assert client.get("/_admin/state").status_code == 200


# ---------------------------------------------------------------------------
# Customers
# ---------------------------------------------------------------------------
class TestCustomers:
    def test_create_minimal(self, client):
        r = client.post("/v1/customers", headers=AUTH,
                        data={"name": "Jenny Rosen", "email": "jennyrosen@example.com"})
        assert r.status_code == 200
        body = r.json()
        assert body["id"].startswith("cus_")
        assert len(body["id"]) == 4 + 24
        assert body["object"] == "customer"
        assert body["livemode"] is False
        assert body["name"] == "Jenny Rosen"
        assert body["email"] == "jennyrosen@example.com"
        assert body["metadata"] == {}
        assert isinstance(body["created"], int)

    def test_create_with_metadata_and_address(self, client):
        r = client.post(
            "/v1/customers", headers={**AUTH, **FORM},
            content="name=Meta&metadata[order_id]=6735&address[city]=Berlin&address[country]=DE",
        )
        assert r.status_code == 200
        body = r.json()
        assert body["metadata"] == {"order_id": "6735"}
        assert body["address"]["city"] == "Berlin"

    def test_retrieve(self, client):
        created = client.post("/v1/customers", headers=AUTH, data={"name": "R"}).json()
        got = client.get(f"/v1/customers/{created['id']}", headers=AUTH).json()
        assert got["id"] == created["id"]
        assert got["name"] == "R"

    def test_retrieve_missing_404_envelope(self, client):
        r = client.get("/v1/customers/cus_unknown", headers=AUTH)
        assert r.status_code == 404
        err = r.json()["error"]
        assert err["type"] == "invalid_request_error"
        assert err["code"] == "resource_missing"
        assert err["param"] == "id"
        assert err["message"] == "No such customer: 'cus_unknown'"

    def test_update(self, client):
        created = client.post("/v1/customers", headers=AUTH, data={"name": "Before"}).json()
        r = client.post(f"/v1/customers/{created['id']}", headers=AUTH,
                        data={"name": "After", "description": "vip"})
        assert r.status_code == 200
        assert r.json()["name"] == "After"
        assert r.json()["description"] == "vip"

    def test_update_metadata_merge_and_unset(self, client):
        created = client.post(
            "/v1/customers", headers={**AUTH, **FORM},
            content="metadata[a]=1&metadata[b]=2",
        ).json()
        updated = client.post(
            f"/v1/customers/{created['id']}", headers={**AUTH, **FORM},
            content="metadata[a]=&metadata[c]=3",
        ).json()
        assert updated["metadata"] == {"b": "2", "c": "3"}

    def test_update_metadata_clear_all(self, client):
        created = client.post(
            "/v1/customers", headers={**AUTH, **FORM}, content="metadata[a]=1",
        ).json()
        updated = client.post(
            f"/v1/customers/{created['id']}", headers={**AUTH, **FORM}, content="metadata=",
        ).json()
        assert updated["metadata"] == {}

    def test_delete(self, client):
        created = client.post("/v1/customers", headers=AUTH, data={"name": "Gone"}).json()
        r = client.delete(f"/v1/customers/{created['id']}", headers=AUTH)
        assert r.status_code == 200
        assert r.json() == {"id": created["id"], "object": "customer", "deleted": True}
        # Deleted customers remain retrievable as a stub
        got = client.get(f"/v1/customers/{created['id']}", headers=AUTH).json()
        assert got["deleted"] is True

    def test_unknown_param_rejected(self, client):
        r = client.post("/v1/customers", headers=AUTH, data={"frobnicate": "yes"})
        assert r.status_code == 400
        err = r.json()["error"]
        assert err["code"] == "parameter_unknown"
        assert err["param"] == "frobnicate"

    def test_list_seeded(self, client):
        body = client.get("/v1/customers", headers=AUTH).json()
        assert body["object"] == "list"
        assert body["url"] == "/v1/customers"
        assert body["has_more"] is False
        assert len(body["data"]) == 3

    def test_list_filter_email(self, client):
        body = client.get("/v1/customers?email=ada@example.com", headers=AUTH).json()
        assert len(body["data"]) == 1
        assert body["data"][0]["name"] == "Ada Lovelace"

    def test_list_reverse_chronological(self, client):
        data = client.get("/v1/customers", headers=AUTH).json()["data"]
        created = [c["created"] for c in data]
        assert created == sorted(created, reverse=True)

    def test_list_limit_and_starting_after(self, client):
        first = client.get("/v1/customers?limit=1", headers=AUTH).json()
        assert len(first["data"]) == 1
        assert first["has_more"] is True
        second = client.get(
            f"/v1/customers?limit=1&starting_after={first['data'][0]['id']}", headers=AUTH
        ).json()
        assert len(second["data"]) == 1
        assert second["data"][0]["id"] != first["data"][0]["id"]

    def test_list_ending_before(self, client):
        all_data = client.get("/v1/customers", headers=AUTH).json()["data"]
        last_id = all_data[-1]["id"]
        prev = client.get(f"/v1/customers?limit=1&ending_before={last_id}", headers=AUTH).json()
        assert len(prev["data"]) == 1
        assert prev["data"][0]["id"] == all_data[-2]["id"]

    def test_list_limit_validation(self, client):
        r = client.get("/v1/customers?limit=0", headers=AUTH)
        assert r.status_code == 400
        assert r.json()["error"]["param"] == "limit"
        r = client.get("/v1/customers?limit=101", headers=AUTH)
        assert r.status_code == 400

    def test_list_bad_cursor(self, client):
        r = client.get("/v1/customers?starting_after=cus_nonexistent", headers=AUTH)
        assert r.status_code == 400
        assert r.json()["error"]["code"] == "resource_missing"

    def test_customer_payment_methods_list(self, client):
        customer = client.get("/v1/customers?email=ada@example.com", headers=AUTH).json()["data"][0]
        body = client.get(f"/v1/customers/{customer['id']}/payment_methods", headers=AUTH).json()
        assert body["object"] == "list"
        assert len(body["data"]) == 1
        assert body["data"][0]["card"]["brand"] == "visa"


# ---------------------------------------------------------------------------
# PaymentMethods
# ---------------------------------------------------------------------------
class TestPaymentMethods:
    def test_create_card(self, client):
        r = client.post(
            "/v1/payment_methods", headers={**AUTH, **FORM},
            content="type=card&card[number]=4242424242424242&card[exp_month]=12"
                    "&card[exp_year]=2030&card[cvc]=314&billing_details[name]=John Doe",
        )
        assert r.status_code == 200
        body = r.json()
        assert body["id"].startswith("pm_")
        assert body["type"] == "card"
        assert body["card"]["brand"] == "visa"
        assert body["card"]["last4"] == "4242"
        assert body["card"]["exp_year"] == 2030
        assert body["card"]["checks"]["cvc_check"] == "pass"
        assert body["billing_details"]["name"] == "John Doe"
        assert body["customer"] is None

    def test_create_mastercard_brand_detected(self, client):
        r = client.post(
            "/v1/payment_methods", headers={**AUTH, **FORM},
            content="type=card&card[number]=5555555555554444",
        )
        assert r.json()["card"]["brand"] == "mastercard"
        assert r.json()["card"]["last4"] == "4444"

    def test_create_with_token(self, client):
        r = client.post(
            "/v1/payment_methods", headers={**AUTH, **FORM},
            content="type=card&card[token]=tok_amex",
        )
        assert r.json()["card"]["brand"] == "amex"

    def test_create_requires_type(self, client):
        r = client.post("/v1/payment_methods", headers=AUTH, data={})
        assert r.status_code == 400
        assert r.json()["error"]["code"] == "parameter_missing"
        assert r.json()["error"]["param"] == "type"

    def test_incorrect_number_fails_at_creation(self, client):
        r = client.post(
            "/v1/payment_methods", headers={**AUTH, **FORM},
            content="type=card&card[number]=4242424242424241",
        )
        assert r.status_code == 402
        assert r.json()["error"]["code"] == "incorrect_number"

    def test_retrieve(self, client):
        pm = client.post("/v1/payment_methods", headers=AUTH, data={"type": "card"}).json()
        got = client.get(f"/v1/payment_methods/{pm['id']}", headers=AUTH).json()
        assert got["id"] == pm["id"]

    def test_retrieve_virtual_pm_materializes(self, client):
        got = client.get("/v1/payment_methods/pm_card_visa", headers=AUTH).json()
        assert got["id"].startswith("pm_")
        assert got["id"] != "pm_card_visa"
        assert got["card"]["brand"] == "visa"
        assert got["card"]["last4"] == "4242"

    def test_attach(self, client):
        customer = client.post("/v1/customers", headers=AUTH, data={"name": "A"}).json()
        pm = client.post("/v1/payment_methods", headers=AUTH, data={"type": "card"}).json()
        r = client.post(f"/v1/payment_methods/{pm['id']}/attach", headers=AUTH,
                        data={"customer": customer["id"]})
        assert r.status_code == 200
        assert r.json()["customer"] == customer["id"]

    def test_attach_requires_customer_param(self, client):
        pm = client.post("/v1/payment_methods", headers=AUTH, data={"type": "card"}).json()
        r = client.post(f"/v1/payment_methods/{pm['id']}/attach", headers=AUTH, data={})
        assert r.status_code == 400
        assert r.json()["error"]["param"] == "customer"

    def test_attach_unknown_customer_404(self, client):
        pm = client.post("/v1/payment_methods", headers=AUTH, data={"type": "card"}).json()
        r = client.post(f"/v1/payment_methods/{pm['id']}/attach", headers=AUTH,
                        data={"customer": "cus_nope"})
        assert r.status_code == 404
        assert r.json()["error"]["code"] == "resource_missing"

    def test_attach_virtual_pm(self, client):
        customer = client.post("/v1/customers", headers=AUTH, data={"name": "V"}).json()
        r = client.post("/v1/payment_methods/pm_card_mastercard/attach", headers=AUTH,
                        data={"customer": customer["id"]})
        assert r.status_code == 200
        assert r.json()["customer"] == customer["id"]
        assert r.json()["card"]["brand"] == "mastercard"

    def test_detach(self, client):
        customer = client.post("/v1/customers", headers=AUTH, data={"name": "D"}).json()
        pm = client.post("/v1/payment_methods", headers=AUTH, data={"type": "card"}).json()
        client.post(f"/v1/payment_methods/{pm['id']}/attach", headers=AUTH,
                    data={"customer": customer["id"]})
        r = client.post(f"/v1/payment_methods/{pm['id']}/detach", headers=AUTH)
        assert r.status_code == 200
        assert r.json()["customer"] is None

    def test_detach_unattached_400(self, client):
        pm = client.post("/v1/payment_methods", headers=AUTH, data={"type": "card"}).json()
        r = client.post(f"/v1/payment_methods/{pm['id']}/detach", headers=AUTH)
        assert r.status_code == 400

    def test_list_by_customer_and_type(self, client):
        customer = client.get("/v1/customers?email=grace@example.com", headers=AUTH).json()["data"][0]
        body = client.get(
            f"/v1/payment_methods?customer={customer['id']}&type=card", headers=AUTH
        ).json()
        assert len(body["data"]) == 1
        assert body["data"][0]["card"]["brand"] == "mastercard"

    def test_update_metadata(self, client):
        pm = client.post("/v1/payment_methods", headers=AUTH, data={"type": "card"}).json()
        r = client.post(f"/v1/payment_methods/{pm['id']}", headers={**AUTH, **FORM},
                        content="metadata[usage]=tests")
        assert r.json()["metadata"] == {"usage": "tests"}


# ---------------------------------------------------------------------------
# PaymentIntents — status machine
# ---------------------------------------------------------------------------
class TestPaymentIntents:
    def test_create_minimal(self, client):
        body = _create_pi(client, "amount=2000&currency=usd")
        assert body["id"].startswith("pi_")
        assert body["object"] == "payment_intent"
        assert body["status"] == "requires_payment_method"
        assert body["amount"] == 2000
        assert body["currency"] == "usd"
        assert body["client_secret"].startswith(body["id"] + "_secret_")
        assert body["capture_method"] == "automatic"
        assert body["latest_charge"] is None

    def test_create_missing_amount(self, client):
        r = client.post("/v1/payment_intents", headers={**AUTH, **FORM}, content="currency=usd")
        assert r.status_code == 400
        err = r.json()["error"]
        assert err["code"] == "parameter_missing"
        assert err["param"] == "amount"

    def test_create_missing_currency(self, client):
        r = client.post("/v1/payment_intents", headers={**AUTH, **FORM}, content="amount=100")
        assert r.status_code == 400
        assert r.json()["error"]["param"] == "currency"

    def test_create_invalid_amount(self, client):
        r = client.post("/v1/payment_intents", headers={**AUTH, **FORM},
                        content="amount=abc&currency=usd")
        assert r.status_code == 400
        assert "Invalid integer" in r.json()["error"]["message"]

    def test_create_with_automatic_payment_methods(self, client):
        body = _create_pi(client, "amount=1099&currency=usd&automatic_payment_methods[enabled]=true")
        assert body["automatic_payment_methods"] == {"enabled": True}
        assert body["payment_method_types"] == ["card", "link"]

    def test_create_with_payment_method_requires_confirmation(self, client):
        body = _create_pi(client, "amount=500&currency=usd&payment_method=pm_card_visa")
        assert body["status"] == "requires_confirmation"
        assert body["payment_method"].startswith("pm_")

    def test_create_with_metadata_and_description(self, client):
        body = _create_pi(client, "amount=500&currency=usd&metadata[order_id]=6735&description=Tea")
        assert body["metadata"] == {"order_id": "6735"}
        assert body["description"] == "Tea"

    def test_create_with_unknown_customer(self, client):
        r = client.post("/v1/payment_intents", headers={**AUTH, **FORM},
                        content="amount=100&currency=usd&customer=cus_ghost")
        assert r.status_code == 404

    def test_retrieve_includes_client_secret(self, client):
        created = _create_pi(client, "amount=300&currency=usd")
        got = client.get(f"/v1/payment_intents/{created['id']}", headers=AUTH).json()
        assert got["client_secret"] == created["client_secret"]

    def test_confirm_success_automatic_capture(self, client):
        pi = _create_pi(client, "amount=1099&currency=usd")
        r = client.post(f"/v1/payment_intents/{pi['id']}/confirm", headers=AUTH,
                        data={"payment_method": "pm_card_visa"})
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "succeeded"
        assert body["amount_received"] == 1099
        assert body["latest_charge"].startswith("ch_")
        assert body["last_payment_error"] is None

    def test_confirm_creates_succeeded_charge(self, client):
        pi = _create_pi(client, "amount=1099&currency=usd")
        body = client.post(f"/v1/payment_intents/{pi['id']}/confirm", headers=AUTH,
                           data={"payment_method": "pm_card_visa"}).json()
        ch = client.get(f"/v1/charges/{body['latest_charge']}", headers=AUTH).json()
        assert ch["status"] == "succeeded"
        assert ch["paid"] is True
        assert ch["captured"] is True
        assert ch["amount"] == 1099
        assert ch["payment_intent"] == pi["id"]
        assert ch["balance_transaction"].startswith("txn_")
        assert ch["outcome"]["network_status"] == "approved_by_network"
        assert ch["outcome"]["type"] == "authorized"
        assert ch["payment_method_details"]["card"]["brand"] == "visa"
        assert ch["payment_method_details"]["card"]["last4"] == "4242"

    def test_confirm_without_payment_method_400(self, client):
        pi = _create_pi(client, "amount=100&currency=usd")
        r = client.post(f"/v1/payment_intents/{pi['id']}/confirm", headers=AUTH)
        assert r.status_code == 400
        assert "missing a payment method" in r.json()["error"]["message"]

    def test_confirm_already_succeeded_400(self, client):
        pi = _create_pi(client, "amount=100&currency=usd&payment_method=pm_card_visa&confirm=true")
        assert pi["status"] == "succeeded"
        r = client.post(f"/v1/payment_intents/{pi['id']}/confirm", headers=AUTH,
                        data={"payment_method": "pm_card_visa"})
        assert r.status_code == 400
        assert r.json()["error"]["code"] == "payment_intent_unexpected_state"

    def test_inline_confirm_on_create(self, client):
        pi = _create_pi(client, "amount=750&currency=usd&payment_method=pm_card_visa&confirm=true")
        assert pi["status"] == "succeeded"
        assert pi["amount_received"] == 750

    def test_decline_generic(self, client):
        pi = _create_pi(client, "amount=900&currency=usd")
        r = client.post(f"/v1/payment_intents/{pi['id']}/confirm", headers=AUTH,
                        data={"payment_method": "pm_card_chargeDeclined"})
        assert r.status_code == 402
        err = r.json()["error"]
        assert err["type"] == "card_error"
        assert err["code"] == "card_declined"
        assert err["decline_code"] == "generic_decline"
        assert err["charge"].startswith("ch_")
        assert err["payment_intent"]["id"] == pi["id"]
        assert err["payment_method"]["card"]["brand"] == "visa"

    def test_decline_sets_last_payment_error_and_status(self, client):
        pi = _create_pi(client, "amount=900&currency=usd")
        client.post(f"/v1/payment_intents/{pi['id']}/confirm", headers=AUTH,
                    data={"payment_method": "pm_card_visa_chargeDeclined"})
        got = client.get(f"/v1/payment_intents/{pi['id']}", headers=AUTH).json()
        assert got["status"] == "requires_payment_method"
        assert got["payment_method"] is None
        lpe = got["last_payment_error"]
        assert lpe["type"] == "card_error"
        assert lpe["code"] == "card_declined"
        assert lpe["decline_code"] == "generic_decline"
        assert lpe["payment_method"]["object"] == "payment_method"

    def test_decline_creates_failed_charge(self, client):
        pi = _create_pi(client, "amount=900&currency=usd")
        r = client.post(f"/v1/payment_intents/{pi['id']}/confirm", headers=AUTH,
                        data={"payment_method": "pm_card_chargeDeclined"})
        ch_id = r.json()["error"]["charge"]
        ch = client.get(f"/v1/charges/{ch_id}", headers=AUTH).json()
        assert ch["status"] == "failed"
        assert ch["paid"] is False
        assert ch["failure_code"] == "card_declined"
        assert ch["failure_message"]
        assert ch["outcome"]["type"] == "issuer_declined"
        assert ch["outcome"]["network_status"] == "declined_by_network"

    def test_decline_insufficient_funds(self, client):
        pi = _create_pi(client, "amount=900&currency=usd")
        r = client.post(f"/v1/payment_intents/{pi['id']}/confirm", headers=AUTH,
                        data={"payment_method": "pm_card_chargeDeclinedInsufficientFunds"})
        assert r.status_code == 402
        assert r.json()["error"]["decline_code"] == "insufficient_funds"

    def test_decline_visa_infix_spelling(self, client):
        pi = _create_pi(client, "amount=900&currency=usd")
        r = client.post(f"/v1/payment_intents/{pi['id']}/confirm", headers=AUTH,
                        data={"payment_method": "pm_card_visa_chargeDeclinedInsufficientFunds"})
        assert r.status_code == 402
        assert r.json()["error"]["decline_code"] == "insufficient_funds"

    def test_retry_after_decline_succeeds(self, client):
        pi = _create_pi(client, "amount=900&currency=usd")
        client.post(f"/v1/payment_intents/{pi['id']}/confirm", headers=AUTH,
                    data={"payment_method": "pm_card_chargeDeclined"})
        r = client.post(f"/v1/payment_intents/{pi['id']}/confirm", headers=AUTH,
                        data={"payment_method": "pm_card_visa"})
        assert r.status_code == 200
        assert r.json()["status"] == "succeeded"
        assert r.json()["last_payment_error"] is None

    def test_manual_capture_flow(self, client):
        pi = _create_pi(client, "amount=5000&currency=usd&capture_method=manual"
                                "&payment_method=pm_card_visa&confirm=true")
        assert pi["status"] == "requires_capture"
        assert pi["amount_capturable"] == 5000
        assert pi["amount_received"] == 0
        ch = client.get(f"/v1/charges/{pi['latest_charge']}", headers=AUTH).json()
        assert ch["captured"] is False
        assert ch["paid"] is True
        assert ch["balance_transaction"] is None

        r = client.post(f"/v1/payment_intents/{pi['id']}/capture", headers=AUTH)
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "succeeded"
        assert body["amount_received"] == 5000
        assert body["amount_capturable"] == 0
        ch = client.get(f"/v1/charges/{pi['latest_charge']}", headers=AUTH).json()
        assert ch["captured"] is True
        assert ch["amount_captured"] == 5000
        assert ch["balance_transaction"].startswith("txn_")

    def test_partial_capture_refunds_remainder(self, client):
        pi = _create_pi(client, "amount=5000&currency=usd&capture_method=manual"
                                "&payment_method=pm_card_visa&confirm=true")
        r = client.post(f"/v1/payment_intents/{pi['id']}/capture", headers=AUTH,
                        data={"amount_to_capture": "3000"})
        body = r.json()
        assert body["status"] == "succeeded"
        assert body["amount_received"] == 3000
        ch = client.get(f"/v1/charges/{pi['latest_charge']}", headers=AUTH).json()
        assert ch["amount_captured"] == 3000
        assert ch["amount_refunded"] == 2000
        assert ch["refunds"]["data"][0]["amount"] == 2000

    def test_capture_too_much_400(self, client):
        pi = _create_pi(client, "amount=5000&currency=usd&capture_method=manual"
                                "&payment_method=pm_card_visa&confirm=true")
        r = client.post(f"/v1/payment_intents/{pi['id']}/capture", headers=AUTH,
                        data={"amount_to_capture": "6000"})
        assert r.status_code == 400
        assert r.json()["error"]["param"] == "amount_to_capture"

    def test_capture_wrong_state_400(self, client):
        pi = _create_pi(client, "amount=100&currency=usd")
        r = client.post(f"/v1/payment_intents/{pi['id']}/capture", headers=AUTH)
        assert r.status_code == 400
        assert r.json()["error"]["code"] == "payment_intent_unexpected_state"

    def test_cancel_requires_payment_method(self, client):
        pi = _create_pi(client, "amount=100&currency=usd")
        r = client.post(f"/v1/payment_intents/{pi['id']}/cancel", headers=AUTH,
                        data={"cancellation_reason": "requested_by_customer"})
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "canceled"
        assert body["cancellation_reason"] == "requested_by_customer"
        assert isinstance(body["canceled_at"], int)

    def test_cancel_succeeded_400(self, client):
        pi = _create_pi(client, "amount=100&currency=usd&payment_method=pm_card_visa&confirm=true")
        r = client.post(f"/v1/payment_intents/{pi['id']}/cancel", headers=AUTH)
        assert r.status_code == 400
        assert r.json()["error"]["code"] == "payment_intent_unexpected_state"

    def test_cancel_invalid_reason_400(self, client):
        pi = _create_pi(client, "amount=100&currency=usd")
        r = client.post(f"/v1/payment_intents/{pi['id']}/cancel", headers=AUTH,
                        data={"cancellation_reason": "because"})
        assert r.status_code == 400
        assert r.json()["error"]["param"] == "cancellation_reason"

    def test_cancel_requires_capture_releases_hold(self, client):
        pi = _create_pi(client, "amount=2000&currency=usd&capture_method=manual"
                                "&payment_method=pm_card_visa&confirm=true")
        r = client.post(f"/v1/payment_intents/{pi['id']}/cancel", headers=AUTH)
        assert r.status_code == 200
        assert r.json()["status"] == "canceled"
        assert r.json()["amount_capturable"] == 0
        ch = client.get(f"/v1/charges/{pi['latest_charge']}", headers=AUTH).json()
        assert ch["refunded"] is True
        assert ch["amount_refunded"] == 2000

    def test_update_metadata(self, client):
        pi = _create_pi(client, "amount=100&currency=usd")
        r = client.post(f"/v1/payment_intents/{pi['id']}", headers={**AUTH, **FORM},
                        content="metadata[invoice]=inv_42&description=updated")
        assert r.json()["metadata"] == {"invoice": "inv_42"}
        assert r.json()["description"] == "updated"

    def test_update_amount_pre_confirm(self, client):
        pi = _create_pi(client, "amount=100&currency=usd")
        r = client.post(f"/v1/payment_intents/{pi['id']}", headers=AUTH, data={"amount": "250"})
        assert r.json()["amount"] == 250

    def test_update_amount_after_succeeded_400(self, client):
        pi = _create_pi(client, "amount=100&currency=usd&payment_method=pm_card_visa&confirm=true")
        r = client.post(f"/v1/payment_intents/{pi['id']}", headers=AUTH, data={"amount": "250"})
        assert r.status_code == 400
        assert r.json()["error"]["code"] == "payment_intent_unexpected_state"

    def test_get_missing_404(self, client):
        r = client.get("/v1/payment_intents/pi_missing", headers=AUTH)
        assert r.status_code == 404
        assert r.json()["error"]["message"] == "No such payment_intent: 'pi_missing'"

    def test_list_seeded(self, client):
        body = client.get("/v1/payment_intents", headers=AUTH).json()
        assert body["object"] == "list"
        assert len(body["data"]) == 5

    def test_list_filter_customer(self, client):
        customer = client.get("/v1/customers?email=ada@example.com", headers=AUTH).json()["data"][0]
        body = client.get(f"/v1/payment_intents?customer={customer['id']}", headers=AUTH).json()
        assert len(body["data"]) == 2
        assert all(pi["customer"] == customer["id"] for pi in body["data"])

    def test_seeded_requires_capture_intent_exists(self, client):
        body = client.get("/v1/payment_intents", headers=AUTH).json()
        statuses = [pi["status"] for pi in body["data"]]
        assert statuses.count("requires_capture") == 1
        assert statuses.count("succeeded") == 4


# ---------------------------------------------------------------------------
# Charges
# ---------------------------------------------------------------------------
class TestCharges:
    def test_list_seeded(self, client):
        body = client.get("/v1/charges", headers=AUTH).json()
        assert body["object"] == "list"
        assert body["url"] == "/v1/charges"
        assert len(body["data"]) == 5

    def test_list_reverse_chronological(self, client):
        data = client.get("/v1/charges", headers=AUTH).json()["data"]
        created = [c["created"] for c in data]
        assert created == sorted(created, reverse=True)

    def test_list_filter_customer(self, client):
        customer = client.get("/v1/customers?email=grace@example.com", headers=AUTH).json()["data"][0]
        body = client.get(f"/v1/charges?customer={customer['id']}", headers=AUTH).json()
        assert len(body["data"]) == 2

    def test_list_filter_payment_intent(self, client):
        pi = client.get("/v1/payment_intents?limit=1", headers=AUTH).json()["data"][0]
        body = client.get(f"/v1/charges?payment_intent={pi['id']}", headers=AUTH).json()
        assert len(body["data"]) == 1
        assert body["data"][0]["id"] == pi["latest_charge"]

    def test_get_charge_fields(self, client):
        ch = client.get("/v1/charges?limit=1", headers=AUTH).json()["data"][0]
        assert ch["object"] == "charge"
        assert ch["currency"] == "usd"
        assert ch["payment_method_details"]["type"] == "card"
        assert "refunds" in ch

    def test_get_missing_404(self, client):
        r = client.get("/v1/charges/ch_missing", headers=AUTH)
        assert r.status_code == 404
        assert r.json()["error"]["code"] == "resource_missing"

    def test_update_metadata_and_description(self, client):
        ch = client.get("/v1/charges?limit=1", headers=AUTH).json()["data"][0]
        r = client.post(f"/v1/charges/{ch['id']}", headers={**AUTH, **FORM},
                        content="metadata[note]=checked&description=updated desc")
        assert r.status_code == 200
        assert r.json()["metadata"]["note"] == "checked"
        assert r.json()["description"] == "updated desc"

    def test_update_amount_rejected(self, client):
        ch = client.get("/v1/charges?limit=1", headers=AUTH).json()["data"][0]
        r = client.post(f"/v1/charges/{ch['id']}", headers=AUTH, data={"amount": "1"})
        assert r.status_code == 400
        assert r.json()["error"]["code"] == "parameter_unknown"

    def test_pagination_cursor(self, client):
        page1 = client.get("/v1/charges?limit=2", headers=AUTH).json()
        assert page1["has_more"] is True
        page2 = client.get(
            f"/v1/charges?limit=2&starting_after={page1['data'][-1]['id']}", headers=AUTH
        ).json()
        ids1 = {c["id"] for c in page1["data"]}
        ids2 = {c["id"] for c in page2["data"]}
        assert not ids1 & ids2


# ---------------------------------------------------------------------------
# Refunds
# ---------------------------------------------------------------------------
class TestRefunds:
    def _succeeded_charge(self, client, amount=1500) -> str:
        pi = _create_pi(client, f"amount={amount}&currency=usd&payment_method=pm_card_visa&confirm=true")
        return pi["latest_charge"]

    def test_create_by_charge_full(self, client):
        ch_id = self._succeeded_charge(client)
        r = client.post("/v1/refunds", headers=AUTH, data={"charge": ch_id})
        assert r.status_code == 200
        body = r.json()
        assert body["id"].startswith("re_")
        assert body["object"] == "refund"
        assert body["amount"] == 1500
        assert body["status"] == "succeeded"
        assert body["charge"] == ch_id
        assert body["balance_transaction"].startswith("txn_")
        ch = client.get(f"/v1/charges/{ch_id}", headers=AUTH).json()
        assert ch["refunded"] is True
        assert ch["amount_refunded"] == 1500

    def test_create_by_payment_intent(self, client):
        pi = _create_pi(client, "amount=800&currency=usd&payment_method=pm_card_visa&confirm=true")
        r = client.post("/v1/refunds", headers=AUTH, data={"payment_intent": pi["id"]})
        assert r.status_code == 200
        assert r.json()["payment_intent"] == pi["id"]
        assert r.json()["amount"] == 800

    def test_partial_refund(self, client):
        ch_id = self._succeeded_charge(client, amount=2000)
        r = client.post("/v1/refunds", headers=AUTH, data={"charge": ch_id, "amount": "500"})
        assert r.json()["amount"] == 500
        ch = client.get(f"/v1/charges/{ch_id}", headers=AUTH).json()
        assert ch["refunded"] is False
        assert ch["amount_refunded"] == 500
        assert ch["refunds"]["total_count"] == 1
        assert ch["refunds"]["object"] == "list"

    def test_over_refund_400(self, client):
        ch_id = self._succeeded_charge(client, amount=1000)
        r = client.post("/v1/refunds", headers=AUTH, data={"charge": ch_id, "amount": "2000"})
        assert r.status_code == 400
        assert "greater than unrefunded amount" in r.json()["error"]["message"]

    def test_double_full_refund_400(self, client):
        ch_id = self._succeeded_charge(client)
        client.post("/v1/refunds", headers=AUTH, data={"charge": ch_id})
        r = client.post("/v1/refunds", headers=AUTH, data={"charge": ch_id})
        assert r.status_code == 400
        assert r.json()["error"]["code"] == "charge_already_refunded"

    def test_requires_charge_or_payment_intent(self, client):
        r = client.post("/v1/refunds", headers=AUTH, data={})
        assert r.status_code == 400

    def test_invalid_reason_400(self, client):
        ch_id = self._succeeded_charge(client)
        r = client.post("/v1/refunds", headers=AUTH,
                        data={"charge": ch_id, "reason": "felt_like_it"})
        assert r.status_code == 400
        assert r.json()["error"]["param"] == "reason"

    def test_refund_uncaptured_charge_400(self, client):
        pi = _create_pi(client, "amount=900&currency=usd&capture_method=manual"
                                "&payment_method=pm_card_visa&confirm=true")
        r = client.post("/v1/refunds", headers=AUTH, data={"charge": pi["latest_charge"]})
        assert r.status_code == 400
        assert "not been captured" in r.json()["error"]["message"]

    def test_creates_negative_balance_transaction(self, client):
        ch_id = self._succeeded_charge(client, amount=1200)
        refund = client.post("/v1/refunds", headers=AUTH, data={"charge": ch_id}).json()
        txn = client.get(
            f"/v1/balance_transactions/{refund['balance_transaction']}", headers=AUTH
        ).json()
        assert txn["amount"] == -1200
        assert txn["net"] == -1200
        assert txn["fee"] == 0
        assert txn["type"] == "refund"
        assert txn["reporting_category"] == "refund"
        assert txn["source"] == refund["id"]

    def test_retrieve_and_list(self, client):
        ch_id = self._succeeded_charge(client)
        refund = client.post("/v1/refunds", headers=AUTH, data={"charge": ch_id}).json()
        got = client.get(f"/v1/refunds/{refund['id']}", headers=AUTH).json()
        assert got["id"] == refund["id"]
        listed = client.get(f"/v1/refunds?charge={ch_id}", headers=AUTH).json()
        assert len(listed["data"]) == 1

    def test_update_metadata(self, client):
        ch_id = self._succeeded_charge(client)
        refund = client.post("/v1/refunds", headers=AUTH, data={"charge": ch_id}).json()
        r = client.post(f"/v1/refunds/{refund['id']}", headers={**AUTH, **FORM},
                        content="metadata[ticket]=T-99")
        assert r.json()["metadata"] == {"ticket": "T-99"}

    def test_cancel_succeeded_refund_400(self, client):
        ch_id = self._succeeded_charge(client)
        refund = client.post("/v1/refunds", headers=AUTH, data={"charge": ch_id}).json()
        r = client.post(f"/v1/refunds/{refund['id']}/cancel", headers=AUTH)
        assert r.status_code == 400


# ---------------------------------------------------------------------------
# Products & Prices
# ---------------------------------------------------------------------------
class TestProducts:
    def test_create(self, client):
        r = client.post("/v1/products", headers=AUTH, data={"name": "Gold Plan"})
        assert r.status_code == 200
        body = r.json()
        assert body["id"].startswith("prod_")
        assert body["object"] == "product"
        assert body["name"] == "Gold Plan"
        assert body["active"] is True

    def test_create_requires_name(self, client):
        r = client.post("/v1/products", headers=AUTH, data={})
        assert r.status_code == 400
        assert r.json()["error"]["param"] == "name"

    def test_create_with_default_price_data(self, client):
        r = client.post(
            "/v1/products", headers={**AUTH, **FORM},
            content="name=Bundle&default_price_data[currency]=usd"
                    "&default_price_data[unit_amount]=1500",
        )
        body = r.json()
        assert body["default_price"].startswith("price_")

    def test_retrieve_update(self, client):
        product = client.post("/v1/products", headers=AUTH, data={"name": "P1"}).json()
        got = client.get(f"/v1/products/{product['id']}", headers=AUTH).json()
        assert got["name"] == "P1"
        updated = client.post(f"/v1/products/{product['id']}", headers=AUTH,
                              data={"description": "desc", "active": "false"}).json()
        assert updated["description"] == "desc"
        assert updated["active"] is False

    def test_delete_without_prices(self, client):
        product = client.post("/v1/products", headers=AUTH, data={"name": "Bye"}).json()
        r = client.delete(f"/v1/products/{product['id']}", headers=AUTH)
        assert r.json() == {"id": product["id"], "object": "product", "deleted": True}

    def test_delete_with_prices_400(self, client):
        product = client.post("/v1/products", headers=AUTH, data={"name": "Keeper"}).json()
        client.post("/v1/prices", headers=AUTH,
                    data={"currency": "usd", "unit_amount": "100", "product": product["id"]})
        r = client.delete(f"/v1/products/{product['id']}", headers=AUTH)
        assert r.status_code == 400

    def test_list_active_filter(self, client):
        product = client.post("/v1/products", headers=AUTH, data={"name": "Off"}).json()
        client.post(f"/v1/products/{product['id']}", headers=AUTH, data={"active": "false"})
        active = client.get("/v1/products?active=true", headers=AUTH).json()
        inactive = client.get("/v1/products?active=false", headers=AUTH).json()
        assert all(p["active"] for p in active["data"])
        assert any(p["id"] == product["id"] for p in inactive["data"])

    def test_seeded_products(self, client):
        body = client.get("/v1/products", headers=AUTH).json()
        names = {p["name"] for p in body["data"]}
        assert names == {"Starter Plan", "Pro Widget"}


class TestPrices:
    def test_create_one_time(self, client):
        product = client.post("/v1/products", headers=AUTH, data={"name": "OT"}).json()
        r = client.post("/v1/prices", headers=AUTH,
                        data={"currency": "usd", "unit_amount": "2500", "product": product["id"]})
        body = r.json()
        assert body["id"].startswith("price_")
        assert body["type"] == "one_time"
        assert body["recurring"] is None
        assert body["unit_amount"] == 2500
        assert body["unit_amount_decimal"] == "2500"
        assert body["currency"] == "usd"

    def test_create_recurring_stored_verbatim(self, client):
        product = client.post("/v1/products", headers=AUTH, data={"name": "Sub"}).json()
        r = client.post(
            "/v1/prices", headers={**AUTH, **FORM},
            content=f"currency=usd&unit_amount=999&product={product['id']}"
                    "&recurring[interval]=month",
        )
        body = r.json()
        assert body["type"] == "recurring"
        assert body["recurring"]["interval"] == "month"
        assert body["recurring"]["interval_count"] == 1
        assert body["recurring"]["usage_type"] == "licensed"

    def test_create_invalid_interval(self, client):
        product = client.post("/v1/products", headers=AUTH, data={"name": "Bad"}).json()
        r = client.post(
            "/v1/prices", headers={**AUTH, **FORM},
            content=f"currency=usd&unit_amount=999&product={product['id']}"
                    "&recurring[interval]=fortnight",
        )
        assert r.status_code == 400

    def test_create_unknown_product_404(self, client):
        r = client.post("/v1/prices", headers=AUTH,
                        data={"currency": "usd", "unit_amount": "100", "product": "prod_nope"})
        assert r.status_code == 404

    def test_list_filter_product_and_type(self, client):
        starter = [p for p in client.get("/v1/products", headers=AUTH).json()["data"]
                   if p["name"] == "Starter Plan"][0]
        body = client.get(f"/v1/prices?product={starter['id']}", headers=AUTH).json()
        assert len(body["data"]) == 1
        assert body["data"][0]["type"] == "recurring"
        recurring = client.get("/v1/prices?type=recurring", headers=AUTH).json()
        assert all(p["type"] == "recurring" for p in recurring["data"])

    def test_update_nickname_and_metadata(self, client):
        price = client.get("/v1/prices?limit=1", headers=AUTH).json()["data"][0]
        r = client.post(f"/v1/prices/{price['id']}", headers={**AUTH, **FORM},
                        content="nickname=primary&metadata[tier]=1")
        assert r.json()["nickname"] == "primary"
        assert r.json()["metadata"] == {"tier": "1"}

    def test_unit_amount_immutable(self, client):
        price = client.get("/v1/prices?limit=1", headers=AUTH).json()["data"][0]
        r = client.post(f"/v1/prices/{price['id']}", headers=AUTH, data={"unit_amount": "1"})
        assert r.status_code == 400
        assert r.json()["error"]["param"] == "unit_amount"


# ---------------------------------------------------------------------------
# Balance & BalanceTransactions
# ---------------------------------------------------------------------------
class TestBalance:
    SEEDED_NET = (
        (1099 - fee_for_charge(1099))
        + (2500 - fee_for_charge(2500))
        + (999 - fee_for_charge(999))
        + (4200 - fee_for_charge(4200))
        - 500  # seeded partial refund
    )

    def test_seeded_balance(self, client):
        body = client.get("/v1/balance", headers=AUTH).json()
        assert body["object"] == "balance"
        assert body["livemode"] is False
        usd = [b for b in body["available"] if b["currency"] == "usd"][0]
        assert usd["amount"] == self.SEEDED_NET == 7922
        pending = [b for b in body["pending"] if b["currency"] == "usd"][0]
        assert pending["amount"] == 0

    def test_fee_model(self, client):
        # fee = round_half_up(2.9%) + 30c
        assert fee_for_charge(1099) == 62
        assert fee_for_charge(2500) == 103
        assert fee_for_charge(100) == 33

    def test_balance_after_new_charge(self, client):
        pi = _create_pi(client, "amount=1000&currency=usd&payment_method=pm_card_visa&confirm=true")
        assert pi["status"] == "succeeded"
        body = client.get("/v1/balance", headers=AUTH).json()
        usd = [b for b in body["available"] if b["currency"] == "usd"][0]
        assert usd["amount"] == self.SEEDED_NET + 1000 - fee_for_charge(1000)

    def test_balance_after_refund(self, client):
        pi = _create_pi(client, "amount=1000&currency=usd&payment_method=pm_card_visa&confirm=true")
        client.post("/v1/refunds", headers=AUTH, data={"charge": pi["latest_charge"]})
        body = client.get("/v1/balance", headers=AUTH).json()
        usd = [b for b in body["available"] if b["currency"] == "usd"][0]
        # The charge's net stays, minus the full refund amount
        assert usd["amount"] == self.SEEDED_NET + 1000 - fee_for_charge(1000) - 1000

    def test_charge_balance_transaction_fields(self, client):
        pi = _create_pi(client, "amount=1000&currency=usd&payment_method=pm_card_visa&confirm=true")
        ch = client.get(f"/v1/charges/{pi['latest_charge']}", headers=AUTH).json()
        txn = client.get(f"/v1/balance_transactions/{ch['balance_transaction']}", headers=AUTH).json()
        assert txn["object"] == "balance_transaction"
        assert txn["amount"] == 1000
        assert txn["fee"] == fee_for_charge(1000)
        assert txn["net"] == 1000 - fee_for_charge(1000)
        assert txn["type"] == "charge"
        assert txn["reporting_category"] == "charge"
        assert txn["status"] == "available"
        assert txn["source"] == ch["id"]
        assert txn["fee_details"][0]["type"] == "stripe_fee"

    def test_list_filter_type(self, client):
        refunds = client.get("/v1/balance_transactions?type=refund", headers=AUTH).json()
        assert len(refunds["data"]) == 1
        charges = client.get("/v1/balance_transactions?type=charge", headers=AUTH).json()
        assert len(charges["data"]) == 4

    def test_get_missing_404(self, client):
        r = client.get("/v1/balance_transactions/txn_missing", headers=AUTH)
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# Events
# ---------------------------------------------------------------------------
class TestEvents:
    def test_customer_created_event(self, client):
        created = client.post("/v1/customers", headers=AUTH, data={"name": "Evt"}).json()
        events = client.get("/v1/events?type=customer.created", headers=AUTH).json()
        assert any(e["data"]["object"]["id"] == created["id"] for e in events["data"])

    def test_event_shape(self, client):
        event = client.get("/v1/events?limit=1", headers=AUTH).json()["data"][0]
        assert event["object"] == "event"
        assert event["id"].startswith("evt_")
        assert event["livemode"] is False
        assert event["pending_webhooks"] == 0
        assert "object" in event["data"]
        assert event["request"]["id"] is None
        assert "idempotency_key" in event["request"]

    def test_payment_lifecycle_events(self, client):
        pi = _create_pi(client, "amount=600&currency=usd&payment_method=pm_card_visa&confirm=true")
        for event_type in ("payment_intent.created", "payment_intent.succeeded", "charge.succeeded"):
            events = client.get(f"/v1/events?type={event_type}", headers=AUTH).json()
            assert any(
                e["data"]["object"]["id"] in (pi["id"], pi["latest_charge"])
                for e in events["data"]
            ), event_type

    def test_payment_failed_event(self, client):
        pi = _create_pi(client, "amount=600&currency=usd")
        client.post(f"/v1/payment_intents/{pi['id']}/confirm", headers=AUTH,
                    data={"payment_method": "pm_card_chargeDeclined"})
        events = client.get("/v1/events?type=payment_intent.payment_failed", headers=AUTH).json()
        assert any(e["data"]["object"]["id"] == pi["id"] for e in events["data"])
        failed = client.get("/v1/events?type=charge.failed", headers=AUTH).json()
        assert len(failed["data"]) == 1

    def test_refund_created_event(self, client):
        events = client.get("/v1/events?type=refund.created", headers=AUTH).json()
        assert len(events["data"]) == 1  # the seeded refund

    def test_type_glob_filter(self, client):
        events = client.get("/v1/events?type=payment_intent.*", headers=AUTH).json()
        assert events["data"]
        assert all(e["type"].startswith("payment_intent.") for e in events["data"])

    def test_types_array_filter(self, client):
        events = client.get(
            "/v1/events?types[]=customer.created&types[]=refund.created", headers=AUTH
        ).json()
        types = {e["type"] for e in events["data"]}
        assert types <= {"customer.created", "refund.created"}
        assert "refund.created" in types

    def test_get_event_by_id(self, client):
        event = client.get("/v1/events?limit=1", headers=AUTH).json()["data"][0]
        got = client.get(f"/v1/events/{event['id']}", headers=AUTH).json()
        assert got == event

    def test_pm_attach_detach_events(self, client):
        customer = client.post("/v1/customers", headers=AUTH, data={"name": "E"}).json()
        pm = client.post("/v1/payment_methods", headers=AUTH, data={"type": "card"}).json()
        client.post(f"/v1/payment_methods/{pm['id']}/attach", headers=AUTH,
                    data={"customer": customer["id"]})
        client.post(f"/v1/payment_methods/{pm['id']}/detach", headers=AUTH)
        attached = client.get("/v1/events?type=payment_method.attached", headers=AUTH).json()
        detached = client.get("/v1/events?type=payment_method.detached", headers=AUTH).json()
        assert any(e["data"]["object"]["id"] == pm["id"] for e in attached["data"])
        assert any(e["data"]["object"]["id"] == pm["id"] for e in detached["data"])


# ---------------------------------------------------------------------------
# Idempotency
# ---------------------------------------------------------------------------
class TestIdempotency:
    def test_replay_same_key_same_params(self, client):
        headers = {**AUTH, "Idempotency-Key": "idem-key-1"}
        first = client.post("/v1/customers", headers=headers, data={"name": "Once"})
        second = client.post("/v1/customers", headers=headers, data={"name": "Once"})
        assert first.status_code == second.status_code == 200
        assert first.json() == second.json()
        assert second.headers.get("idempotent-replayed") == "true"
        # Only one customer was actually created
        listed = client.get("/v1/customers?email=&limit=100", headers=AUTH).json()
        assert sum(1 for c in listed["data"] if c.get("name") == "Once") == 1

    def test_same_key_different_params_400(self, client):
        headers = {**AUTH, "Idempotency-Key": "idem-key-2"}
        client.post("/v1/customers", headers=headers, data={"name": "A"})
        r = client.post("/v1/customers", headers=headers, data={"name": "B"})
        assert r.status_code == 400
        err = r.json()["error"]
        assert err["type"] == "idempotency_error"
        assert "idem-key-2" in err["message"]

    def test_key_scoped_to_replay_errors_too(self, client):
        headers = {**AUTH, "Idempotency-Key": "idem-key-3"}
        first = client.post("/v1/payment_intents", headers={**headers, **FORM},
                            content="currency=usd")  # missing amount -> 400
        second = client.post("/v1/payment_intents", headers={**headers, **FORM},
                             content="currency=usd")
        assert first.status_code == second.status_code == 400
        assert first.json() == second.json()

    def test_get_requests_ignore_key(self, client):
        headers = {**AUTH, "Idempotency-Key": "idem-key-4"}
        r1 = client.get("/v1/customers", headers=headers)
        r2 = client.get("/v1/customers?limit=1", headers=headers)
        assert r1.status_code == r2.status_code == 200
        assert len(r2.json()["data"]) == 1  # not a replay of r1


# ---------------------------------------------------------------------------
# Expand
# ---------------------------------------------------------------------------
class TestExpand:
    def test_pi_expand_latest_charge(self, client):
        pi = _create_pi(client, "amount=700&currency=usd&payment_method=pm_card_visa&confirm=true")
        got = client.get(f"/v1/payment_intents/{pi['id']}?expand[]=latest_charge", headers=AUTH).json()
        assert isinstance(got["latest_charge"], dict)
        assert got["latest_charge"]["object"] == "charge"
        assert got["latest_charge"]["amount"] == 700

    def test_pi_expand_customer_and_payment_method(self, client):
        customer = client.post("/v1/customers", headers=AUTH, data={"name": "X"}).json()
        pi = _create_pi(
            client,
            f"amount=700&currency=usd&customer={customer['id']}"
            "&payment_method=pm_card_visa&confirm=true",
        )
        got = client.get(
            f"/v1/payment_intents/{pi['id']}?expand[]=customer&expand[]=payment_method",
            headers=AUTH,
        ).json()
        assert got["customer"]["object"] == "customer"
        assert got["customer"]["id"] == customer["id"]
        assert got["payment_method"]["object"] == "payment_method"

    def test_charge_expand_balance_transaction_and_customer(self, client):
        ch = client.get("/v1/charges?limit=1", headers=AUTH).json()["data"][0]
        got = client.get(
            f"/v1/charges/{ch['id']}?expand[]=customer&expand[]=balance_transaction",
            headers=AUTH,
        ).json()
        assert got["customer"]["object"] == "customer"
        # seeded newest charge is the uncaptured one; its balance txn is null
        if ch["balance_transaction"]:
            assert got["balance_transaction"]["object"] == "balance_transaction"

    def test_refund_expand_charge(self, client):
        refund = client.get("/v1/refunds?limit=1", headers=AUTH).json()["data"][0]
        got = client.get(f"/v1/refunds/{refund['id']}?expand[]=charge", headers=AUTH).json()
        assert got["charge"]["object"] == "charge"

    def test_nested_expand(self, client):
        pi = _create_pi(client, "amount=700&currency=usd&payment_method=pm_card_visa&confirm=true")
        got = client.get(
            f"/v1/payment_intents/{pi['id']}?expand[]=latest_charge.balance_transaction",
            headers=AUTH,
        ).json()
        assert got["latest_charge"]["balance_transaction"]["object"] == "balance_transaction"

    def test_list_data_expand(self, client):
        body = client.get("/v1/charges?expand[]=data.customer&limit=3", headers=AUTH).json()
        for ch in body["data"]:
            if ch["customer"] is not None:
                assert isinstance(ch["customer"], dict)

    def test_null_expandable_stays_null(self, client):
        pi = _create_pi(client, "amount=700&currency=usd")
        got = client.get(f"/v1/payment_intents/{pi['id']}?expand[]=latest_charge", headers=AUTH).json()
        assert got["latest_charge"] is None

    def test_bad_expand_path_400(self, client):
        pi = _create_pi(client, "amount=700&currency=usd")
        r = client.get(f"/v1/payment_intents/{pi['id']}?expand[]=frobnicator", headers=AUTH)
        assert r.status_code == 400
        assert "cannot be expanded" in r.json()["error"]["message"]

    def test_expand_via_post_body(self, client):
        r = client.post(
            "/v1/payment_intents", headers={**AUTH, **FORM},
            content="amount=700&currency=usd&payment_method=pm_card_visa&confirm=true"
                    "&expand[]=latest_charge",
        )
        assert isinstance(r.json()["latest_charge"], dict)


# ---------------------------------------------------------------------------
# Account (sandbox-test repo parity) + JSON-body leniency
# ---------------------------------------------------------------------------
class TestAccount:
    def test_account_shape(self, client):
        body = client.get("/v1/account", headers=AUTH).json()
        assert body["id"].startswith("acct_")
        assert body["business_profile"]["name"] == "Sandbox"
        assert body["settings"]["dashboard"]["display_name"] == "dev-sandbox"


class TestSandboxRepoFlow:
    def test_sandbox_repo_flow(self, client):
        """Parity anchor: the benjasl-stripe/stripe-sandbox-test flow end-to-end."""
        # POST /v1/payment_intents amount=1099 currency=usd automatic_payment_methods[enabled]=true
        r = client.post(
            "/v1/payment_intents", headers={**AUTH, **FORM},
            content="amount=1099&currency=usd&automatic_payment_methods[enabled]=true",
        )
        assert r.status_code == 200
        pi = r.json()
        assert pi["client_secret"].startswith("pi_")
        assert "_secret_" in pi["client_secret"]

        # confirm with pm_card_visa -> succeeded
        r = client.post(f"/v1/payment_intents/{pi['id']}/confirm", headers=AUTH,
                        data={"payment_method": "pm_card_visa"})
        assert r.status_code == 200
        assert r.json()["status"] == "succeeded"

        # latest_charge expandable
        r = client.get(f"/v1/payment_intents/{pi['id']}?expand[]=latest_charge", headers=AUTH)
        charge = r.json()["latest_charge"]
        assert charge["object"] == "charge"
        assert charge["status"] == "succeeded"
        assert charge["payment_method_details"]["card"]["last4"] == "4242"

    def test_json_body_accepted_leniently(self, client):
        """The sandbox repo's Express app forwards JSON; stripe-node re-encodes as
        form, but the mock also accepts JSON bodies directly (see API_NOTES.md)."""
        r = client.post("/v1/payment_intents", headers=AUTH,
                        json={"amount": 1000, "currency": "usd"})
        assert r.status_code == 200
        assert r.json()["amount"] == 1000


# ---------------------------------------------------------------------------
# Admin & state plumbing
# ---------------------------------------------------------------------------
class TestAdmin:
    def test_health(self, client):
        assert client.get("/health").json() == {"status": "ok"}

    def test_state_dump(self, client):
        state = client.get("/_admin/state").json()
        assert len(state["customers"]) == 3
        assert len(state["payment_intents"]) == 5
        assert len(state["charges"]) == 5
        assert len(state["refunds"]) == 1
        assert state["api_keys"][0]["id"] == DEFAULT_API_KEY

    def test_diff_after_mutation(self, client):
        client.post("/v1/customers", headers=AUTH, data={"name": "DiffMe"})
        diff = client.get("/_admin/diff").json()
        added = diff["added"].get("customers", [])
        assert any(c["name"] == "DiffMe" for c in added)

    def test_reset_restores_initial(self, client):
        client.post("/v1/customers", headers=AUTH, data={"name": "Ephemeral"})
        assert len(client.get("/v1/customers", headers=AUTH).json()["data"]) == 4
        r = client.post("/_admin/reset")
        assert r.json()["status"] == "ok"
        assert len(client.get("/v1/customers", headers=AUTH).json()["data"]) == 3

    def test_action_log_records_form_body(self, client):
        client.post("/v1/customers", headers={**AUTH, **FORM},
                    content="name=Logged&metadata[k]=v")
        log = client.get("/_admin/action_log").json()
        entries = [e for e in log["entries"]
                   if e["method"] == "POST" and e["path"] == "/v1/customers"]
        assert entries
        assert entries[-1]["request_body"] == {"name": "Logged", "metadata": {"k": "v"}}
        assert entries[-1]["token_type"] == "test"

    def test_snapshot_and_restore(self, client):
        client.post("/_admin/snapshot/checkpoint")
        client.post("/v1/customers", headers=AUTH, data={"name": "AfterSnap"})
        r = client.post("/_admin/restore/checkpoint")
        assert r.json()["status"] == "ok"
        names = [c["name"] for c in client.get("/v1/customers", headers=AUTH).json()["data"]]
        assert "AfterSnap" not in names

    def test_admin_seed_fresh(self, client):
        r = client.post("/_admin/seed?scenario=fresh")
        assert r.json()["status"] == "ok"
        assert client.get("/v1/customers", headers=AUTH).json()["data"] == []
        # restore default for other assertions in this test
        client.post("/_admin/seed?scenario=default")

    def test_admin_seed_unknown_scenario_400(self, client):
        r = client.post("/_admin/seed?scenario=nope")
        assert r.status_code == 400

    def test_tasks_listed(self, client):
        body = client.get("/_admin/tasks").json()
        assert body["count"] >= 2
        names = {t["name"] for t in body["tasks"]}
        assert "refund-pro-widget" in names

    def test_task_evaluate_endpoint(self, client):
        r = client.post("/_admin/tasks/refund-pro-widget/evaluate")
        assert r.status_code == 200
        body = r.json()
        assert body["task_name"] == "refund-pro-widget"
        assert body["reward"] == 0.0  # not done yet

    def test_task_evaluate_passes_after_action(self, client):
        # Fully refund the Pro Widget charge (2500 total, 500 already refunded)
        charges = client.get("/v1/charges?limit=100", headers=AUTH).json()["data"]
        widget = [c for c in charges if c["description"] == "Pro Widget"][0]
        r = client.post("/v1/refunds", headers=AUTH, data={"charge": widget["id"]})
        assert r.status_code == 200
        body = client.post("/_admin/tasks/refund-pro-widget/evaluate").json()
        assert body["reward"] == 1.0

    def test_fresh_scenario_has_only_api_key(self, fresh_client):
        state = fresh_client.get("/_admin/state").json()
        assert state["customers"] == []
        assert state["charges"] == []
        assert len(state["api_keys"]) == 1

    def test_web_dashboard_renders(self, client):
        r = client.get("/")
        assert r.status_code == 200
        assert "Mock Stripe" in r.text
        assert "Ada Lovelace" in r.text


class TestDeterminism:
    def test_seed_is_deterministic(self, tmp_path):
        from mock_stripe.models import reset_engine
        from mock_stripe.seed.generator import seed_database
        from mock_stripe.state.snapshots import get_state_dump

        def _ids(path):
            reset_engine()
            seed_database(scenario="default", seed=42, db_path=str(path))
            state = get_state_dump()
            reset_engine()
            return {
                "customers": [c["id"] for c in state["customers"]],
                "charges": [c["id"] for c in state["charges"]],
                "intents": [p["id"] for p in state["payment_intents"]],
            }

        first = _ids(tmp_path / "a.db")
        second = _ids(tmp_path / "b.db")
        assert first == second

    def test_full_state_dump_is_deterministic(self, tmp_path):
        """Strengthened: every field of every row is identical across two seeds
        with the same --seed, EXCEPT the internal `seq` ordering column (a
        wall-clock nanosecond counter) and the dump `timestamp`. This proves
        ids, amounts, statuses, relationships, fees, balance txns and event
        snapshots are all deterministic, not just object ids."""
        from mock_stripe.models import reset_engine
        from mock_stripe.seed.generator import seed_database
        from mock_stripe.state.snapshots import get_state_dump

        def _dump(path):
            reset_engine()
            seed_database(scenario="default", seed=42, db_path=str(path))
            state = get_state_dump()
            reset_engine()
            state.pop("timestamp", None)
            for rows in state.values():
                if isinstance(rows, list):
                    for row in rows:
                        row.pop("seq", None)
            return state

        first = _dump(tmp_path / "c.db")
        second = _dump(tmp_path / "d.db")
        assert first == second
        # And the per-table ordering (newest-first when listed) is stable too.
        assert [c["id"] for c in first["charges"]] == [c["id"] for c in second["charges"]]


class TestAdversarial:
    """Attack tests added during the stripe-hardening adversarial review.
    Money math, status-machine illegal transitions, idempotency identity,
    pagination/expand boundaries, and auth envelope exactness."""

    # --- Money math ---------------------------------------------------------
    def _manual_pi(self, client, amount):
        return _create_pi(
            client,
            f"amount={amount}&currency=usd&capture_method=manual"
            "&payment_method=pm_card_visa&confirm=true",
        )

    def test_partial_capture_then_refund_captured_full_accounting(self, client):
        pi = self._manual_pi(client, 5000)
        cap = client.post(
            f"/v1/payment_intents/{pi['id']}/capture", headers=AUTH,
            data={"amount_to_capture": "3000"},
        ).json()
        assert cap["amount_received"] == 3000
        ch_id = pi["latest_charge"]
        ch = client.get(f"/v1/charges/{ch_id}", headers=AUTH).json()
        # remainder (2000) released as a no-balance-txn refund
        assert ch["amount_captured"] == 3000
        assert ch["amount_refunded"] == 2000
        assert ch["refunded"] is False
        # refund the captured 3000 in two parts; the captured portion is the cap
        r1 = client.post("/v1/refunds", headers=AUTH, data={"charge": ch_id, "amount": "1000"})
        assert r1.status_code == 200
        # only 2000 of the captured 3000 remains refundable
        over = client.post("/v1/refunds", headers=AUTH, data={"charge": ch_id, "amount": "2500"})
        assert over.status_code == 400
        assert "greater than unrefunded amount" in over.json()["error"]["message"]
        r2 = client.post("/v1/refunds", headers=AUTH, data={"charge": ch_id, "amount": "2000"})
        assert r2.status_code == 200
        ch = client.get(f"/v1/charges/{ch_id}", headers=AUTH).json()
        assert ch["amount_refunded"] == 5000  # 2000 release + 3000 captured-refund
        assert ch["refunded"] is True

    def test_multiple_partial_refunds_cannot_exceed_amount(self, client):
        pi = _create_pi(client, "amount=1000&currency=usd&payment_method=pm_card_visa&confirm=true")
        ch_id = pi["latest_charge"]
        assert client.post("/v1/refunds", headers=AUTH, data={"charge": ch_id, "amount": "400"}).status_code == 200
        assert client.post("/v1/refunds", headers=AUTH, data={"charge": ch_id, "amount": "400"}).status_code == 200
        # 200 left; asking for 300 must fail
        bad = client.post("/v1/refunds", headers=AUTH, data={"charge": ch_id, "amount": "300"})
        assert bad.status_code == 400
        # exactly 200 closes it out
        last = client.post("/v1/refunds", headers=AUTH, data={"charge": ch_id, "amount": "200"})
        assert last.status_code == 200
        ch = client.get(f"/v1/charges/{ch_id}", headers=AUTH).json()
        assert ch["amount_refunded"] == 1000
        assert ch["refunded"] is True
        # all refunded; another refund 400s
        assert client.post("/v1/refunds", headers=AUTH, data={"charge": ch_id}).status_code == 400

    def test_refund_zero_or_negative_rejected(self, client):
        pi = _create_pi(client, "amount=1000&currency=usd&payment_method=pm_card_visa&confirm=true")
        ch_id = pi["latest_charge"]
        for amt in ("0", "-100"):
            r = client.post("/v1/refunds", headers=AUTH, data={"charge": ch_id, "amount": amt})
            assert r.status_code == 400, amt
            assert r.json()["error"]["param"] == "amount"

    def test_refund_failed_charge_rejected(self, client):
        pi = _create_pi(client, "amount=900&currency=usd")
        err = client.post(f"/v1/payment_intents/{pi['id']}/confirm", headers=AUTH,
                          data={"payment_method": "pm_card_chargeDeclined"}).json()
        failed_charge = err["error"]["charge"]
        r = client.post("/v1/refunds", headers=AUTH, data={"charge": failed_charge})
        assert r.status_code == 400
        assert "failed" in r.json()["error"]["message"]

    def test_fee_is_half_up_at_tie(self, client):
        # 2.9% of 500 = 14.5 -> half-up = 15 (+30 = 45); a truncating impl gives 44.
        assert fee_for_charge(500) == 45
        pi = _create_pi(client, "amount=500&currency=usd&payment_method=pm_card_visa&confirm=true")
        ch = client.get(f"/v1/charges/{pi['latest_charge']}", headers=AUTH).json()
        txn = client.get(f"/v1/balance_transactions/{ch['balance_transaction']}", headers=AUTH).json()
        assert txn["fee"] == 45
        assert txn["net"] == 455

    def test_refund_does_not_return_the_fee(self, client):
        before = self._usd_available(client)
        pi = _create_pi(client, "amount=1000&currency=usd&payment_method=pm_card_visa&confirm=true")
        client.post("/v1/refunds", headers=AUTH, data={"charge": pi["latest_charge"]})
        after = self._usd_available(client)
        # net effect of charge+full refund = -fee (Stripe keeps the processing fee)
        assert after == before - fee_for_charge(1000)

    @staticmethod
    def _usd_available(client):
        body = client.get("/v1/balance", headers=AUTH).json()
        return [b for b in body["available"] if b["currency"] == "usd"][0]["amount"]

    # --- Status machine -----------------------------------------------------
    def test_capture_on_requires_confirmation_400(self, client):
        pi = _create_pi(client, "amount=1000&currency=usd&payment_method=pm_card_visa")
        assert pi["status"] == "requires_confirmation"
        r = client.post(f"/v1/payment_intents/{pi['id']}/capture", headers=AUTH)
        assert r.status_code == 400
        assert r.json()["error"]["code"] == "payment_intent_unexpected_state"

    def test_confirm_on_requires_capture_400(self, client):
        pi = self._manual_pi(client, 1000)
        assert pi["status"] == "requires_capture"
        r = client.post(f"/v1/payment_intents/{pi['id']}/confirm", headers=AUTH,
                        data={"payment_method": "pm_card_visa"})
        assert r.status_code == 400
        assert r.json()["error"]["code"] == "payment_intent_unexpected_state"

    def test_cancel_on_canceled_400(self, client):
        pi = _create_pi(client, "amount=1000&currency=usd")
        assert client.post(f"/v1/payment_intents/{pi['id']}/cancel", headers=AUTH).status_code == 200
        r = client.post(f"/v1/payment_intents/{pi['id']}/cancel", headers=AUTH)
        assert r.status_code == 400
        assert r.json()["error"]["code"] == "payment_intent_unexpected_state"

    def test_confirm_uses_stored_payment_method(self, client):
        pi = _create_pi(client, "amount=1234&currency=usd&payment_method=pm_card_visa")
        body = client.post(f"/v1/payment_intents/{pi['id']}/confirm", headers=AUTH).json()
        assert body["status"] == "succeeded"
        assert body["amount_received"] == 1234

    # --- Idempotency identity ----------------------------------------------
    def test_idempotent_confirm_no_double_charge(self, client):
        pi = _create_pi(client, "amount=2222&currency=usd&payment_method=pm_card_visa")
        headers = {**AUTH, "Idempotency-Key": "adv-confirm-1"}
        r1 = client.post(f"/v1/payment_intents/{pi['id']}/confirm", headers=headers,
                         data={"payment_method": "pm_card_visa"})
        r2 = client.post(f"/v1/payment_intents/{pi['id']}/confirm", headers=headers,
                         data={"payment_method": "pm_card_visa"})
        assert r1.json() == r2.json()
        assert r1.json()["latest_charge"] == r2.json()["latest_charge"]
        charges = client.get(f"/v1/charges?payment_intent={pi['id']}", headers=AUTH).json()
        assert len(charges["data"]) == 1
        assert r2.headers.get("idempotent-replayed") == "true"

    def test_idempotency_replay_preserves_object_id(self, client):
        headers = {**AUTH, "Idempotency-Key": "adv-cust-id"}
        first = client.post("/v1/customers", headers=headers, data={"name": "Same"}).json()
        second = client.post("/v1/customers", headers=headers, data={"name": "Same"}).json()
        assert first["id"] == second["id"]

    # --- Pagination boundaries ---------------------------------------------
    def test_starting_after_last_item_empty(self, client):
        data = client.get("/v1/customers", headers=AUTH).json()["data"]
        last = data[-1]["id"]
        page = client.get(f"/v1/customers?starting_after={last}", headers=AUTH).json()
        assert page["data"] == []
        assert page["has_more"] is False

    def test_has_more_false_when_limit_equals_total(self, client):
        body = client.get("/v1/customers?limit=3", headers=AUTH).json()
        assert len(body["data"]) == 3
        assert body["has_more"] is False

    def test_cannot_use_both_cursors(self, client):
        data = client.get("/v1/customers", headers=AUTH).json()["data"]
        r = client.get(
            f"/v1/customers?starting_after={data[0]['id']}&ending_before={data[-1]['id']}",
            headers=AUTH,
        )
        assert r.status_code == 400

    # --- Expand boundaries --------------------------------------------------
    def test_expand_depth_5_rejected(self, client):
        pi = _create_pi(client, "amount=700&currency=usd&payment_method=pm_card_visa&confirm=true")
        r = client.get(
            f"/v1/payment_intents/{pi['id']}"
            "?expand[]=latest_charge.payment_intent.latest_charge.payment_intent.customer",
            headers=AUTH,
        )
        assert r.status_code == 400
        assert "4 levels" in r.json()["error"]["message"]

    def test_expand_list_requires_data_prefix(self, client):
        r = client.get("/v1/charges?expand[]=customer", headers=AUTH)
        assert r.status_code == 400
        assert "cannot be expanded" in r.json()["error"]["message"]

    # --- Auth envelope exactness -------------------------------------------
    def test_missing_key_envelope_has_no_code(self, client):
        err = client.get("/v1/customers").json()["error"]
        assert set(err.keys()) == {"type", "message"}
        assert err["type"] == "invalid_request_error"

    def test_bad_key_envelope_has_no_doc_url(self, client):
        # The mock adds code="api_key_invalid" (documented divergence) but must
        # NOT add a doc_url (real Stripe omits it on invalid-key errors).
        err = client.get("/v1/customers",
                         headers={"Authorization": "Bearer sk_test_bogus"}).json()["error"]
        assert err["code"] == "api_key_invalid"
        assert "doc_url" not in err

    def test_sk_live_key_rejected(self, client):
        r = client.get("/v1/customers", headers=_basic_auth_header("sk_live_notseeded"))
        assert r.status_code == 401
        assert r.json()["error"]["type"] == "invalid_request_error"
