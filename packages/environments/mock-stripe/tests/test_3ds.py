"""3DS / SCA tests: requires_action flow + mock authentication completion.

`pm_card_authenticationRequired` (and `pm_card_authenticationRequiredOnSetup`,
card numbers 4000002760003184 / 4000002500003155) make confirm return
status=requires_action with a real-shape `next_action`; nothing is charged
until POST /v1/payment_intents/{id}/_complete_authentication (mock-only
endpoint — real Stripe completes 3DS via Stripe.js; see API_NOTES.md).
"""

from __future__ import annotations

from mock_stripe.seed.generator import DEFAULT_API_KEY

AUTH = {"Authorization": f"Bearer {DEFAULT_API_KEY}"}
FORM = {"Content-Type": "application/x-www-form-urlencoded"}


def _balance(client) -> int:
    body = client.get("/v1/balance", headers=AUTH).json()
    return sum(b["amount"] for b in body["available"] if b["currency"] == "usd")


def _requires_action_pi(client, *, amount=2000, extra="") -> dict:
    pi = client.post(
        "/v1/payment_intents", headers={**AUTH, **FORM},
        content=f"amount={amount}&currency=usd{extra}",
    ).json()
    r = client.post(f"/v1/payment_intents/{pi['id']}/confirm", headers=AUTH,
                    data={"payment_method": "pm_card_authenticationRequired"})
    assert r.status_code == 200, r.text
    return r.json()


def _complete(client, pi_id: str, succeed: str | None = None):
    data = {} if succeed is None else {"succeed": succeed}
    return client.post(f"/v1/payment_intents/{pi_id}/_complete_authentication",
                       headers=AUTH, data=data)


class TestRequiresAction:
    def test_confirm_yields_requires_action_nothing_charged(self, client):
        before = _balance(client)
        pi = _requires_action_pi(client)

        assert pi["status"] == "requires_action"
        assert pi["amount_received"] == 0
        assert pi["amount_capturable"] == 0
        assert pi["latest_charge"] is None
        assert pi["last_payment_error"] is None
        assert pi["payment_method"].startswith("pm_")

        na = pi["next_action"]
        assert na["type"] == "use_stripe_sdk"
        sdk = na["use_stripe_sdk"]
        assert sdk["type"] == "three_d_secure_redirect"
        assert sdk["source"].startswith("src_")
        assert sdk["stripe_js"].startswith("https://hooks.stripe.com/redirect/authenticate/src_")
        assert "client_secret=src_client_secret_" in sdk["stripe_js"]

        # amount NOT charged: no charge rows for this PI, balance unchanged
        charges = client.get(f"/v1/charges?payment_intent={pi['id']}", headers=AUTH).json()
        assert charges["data"] == []
        assert _balance(client) == before

        # payment_intent.requires_action event recorded
        events = client.get("/v1/events?type=payment_intent.requires_action",
                            headers=AUTH).json()
        match = [e for e in events["data"] if e["data"]["object"]["id"] == pi["id"]]
        assert len(match) == 1
        assert match[0]["data"]["object"]["status"] == "requires_action"

    def test_create_with_confirm_inline(self, client):
        r = client.post(
            "/v1/payment_intents", headers={**AUTH, **FORM},
            content="amount=3000&currency=usd&confirm=true"
                    "&payment_method=pm_card_authenticationRequired",
        )
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "requires_action"
        assert body["next_action"]["type"] == "use_stripe_sdk"

    def test_return_url_switches_to_redirect_to_url(self, client):
        pi = client.post("/v1/payment_intents", headers={**AUTH, **FORM},
                         content="amount=2000&currency=usd").json()
        body = client.post(
            f"/v1/payment_intents/{pi['id']}/confirm", headers={**AUTH, **FORM},
            content="payment_method=pm_card_authenticationRequired"
                    "&return_url=https://example.com/return",
        ).json()
        assert body["status"] == "requires_action"
        na = body["next_action"]
        assert na["type"] == "redirect_to_url"
        assert na["redirect_to_url"]["return_url"] == "https://example.com/return"
        assert na["redirect_to_url"]["url"].startswith("https://hooks.stripe.com/")

    def test_on_setup_token_also_requires_action(self, client):
        pi = client.post("/v1/payment_intents", headers={**AUTH, **FORM},
                         content="amount=2000&currency=usd").json()
        body = client.post(f"/v1/payment_intents/{pi['id']}/confirm", headers=AUTH,
                           data={"payment_method": "pm_card_authenticationRequiredOnSetup"}).json()
        assert body["status"] == "requires_action"

    def test_raw_card_number_requires_action(self, client):
        pm = client.post("/v1/payment_methods", headers={**AUTH, **FORM},
                         content="type=card&card[number]=4000002760003184").json()
        pi = client.post("/v1/payment_intents", headers={**AUTH, **FORM},
                         content="amount=2000&currency=usd").json()
        body = client.post(f"/v1/payment_intents/{pi['id']}/confirm", headers=AUTH,
                           data={"payment_method": pm["id"]}).json()
        assert body["status"] == "requires_action"
        assert body["payment_method"] == pm["id"]

    def test_cancel_clears_next_action(self, client):
        pi = _requires_action_pi(client)
        body = client.post(f"/v1/payment_intents/{pi['id']}/cancel", headers=AUTH).json()
        assert body["status"] == "canceled"
        assert body["next_action"] is None

    def test_retry_with_normal_card_succeeds(self, client):
        pi = _requires_action_pi(client)
        # requires_action is a confirmable status; switching to a normal card succeeds
        body = client.post(f"/v1/payment_intents/{pi['id']}/confirm", headers=AUTH,
                           data={"payment_method": "pm_card_visa"}).json()
        assert body["status"] == "succeeded"
        assert body["next_action"] is None


class TestCompleteAuthentication:
    def test_succeed_charges_and_succeeds(self, client):
        before = _balance(client)
        pi = _requires_action_pi(client, amount=2000)
        r = _complete(client, pi["id"], "true")
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "succeeded"
        assert body["amount_received"] == 2000
        assert body["next_action"] is None
        assert body["latest_charge"].startswith("ch_")

        ch = client.get(f"/v1/charges/{body['latest_charge']}", headers=AUTH).json()
        assert ch["status"] == "succeeded"
        assert ch["paid"] is True
        assert ch["captured"] is True
        assert ch["balance_transaction"].startswith("txn_")
        tds = ch["payment_method_details"]["card"]["three_d_secure"]
        assert tds["result"] == "authenticated"
        assert tds["authentication_flow"] == "challenge"

        # fee model applies: 2000 -> fee 88, net 1912
        assert _balance(client) == before + 2000 - 88

        # events: charge.succeeded + payment_intent.succeeded
        for ev_type, obj_id in [("charge.succeeded", ch["id"]),
                                ("payment_intent.succeeded", pi["id"])]:
            events = client.get(f"/v1/events?type={ev_type}", headers=AUTH).json()
            assert any(e["data"]["object"]["id"] == obj_id for e in events["data"])

    def test_succeed_default_true(self, client):
        pi = _requires_action_pi(client)
        body = _complete(client, pi["id"]).json()
        assert body["status"] == "succeeded"

    def test_succeed_manual_capture_goes_to_requires_capture(self, client):
        pi = _requires_action_pi(client, amount=5000, extra="&capture_method=manual")
        body = _complete(client, pi["id"], "true").json()
        assert body["status"] == "requires_capture"
        assert body["amount_capturable"] == 5000
        assert body["amount_received"] == 0
        ch = client.get(f"/v1/charges/{body['latest_charge']}", headers=AUTH).json()
        assert ch["captured"] is False

        captured = client.post(f"/v1/payment_intents/{pi['id']}/capture", headers=AUTH).json()
        assert captured["status"] == "succeeded"
        assert captured["amount_received"] == 5000

    def test_fail_records_authentication_required(self, client):
        before = _balance(client)
        pi = _requires_action_pi(client, amount=2000)
        r = _complete(client, pi["id"], "false")
        assert r.status_code == 200
        body = r.json()

        assert body["status"] == "requires_payment_method"
        assert body["next_action"] is None
        assert body["payment_method"] is None

        err = body["last_payment_error"]
        assert err["type"] == "card_error"
        assert err["code"] == "authentication_required"
        assert err["decline_code"] == "authentication_required"
        assert err["charge"].startswith("ch_")
        assert err["payment_method"]["id"].startswith("pm_")

        # failed charge recorded; nothing hit the balance
        ch = client.get(f"/v1/charges/{err['charge']}", headers=AUTH).json()
        assert ch["status"] == "failed"
        assert ch["paid"] is False
        assert ch["failure_code"] == "authentication_required"
        assert ch["outcome"]["type"] == "issuer_declined"
        assert ch["outcome"]["reason"] == "authentication_required"
        assert ch["balance_transaction"] is None
        tds = ch["payment_method_details"]["card"]["three_d_secure"]
        assert tds["result"] == "failed"
        assert _balance(client) == before

        # events: charge.failed + payment_intent.payment_failed
        events = client.get("/v1/events?type=payment_intent.payment_failed",
                            headers=AUTH).json()
        assert any(e["data"]["object"]["id"] == pi["id"] for e in events["data"])
        events = client.get("/v1/events?type=charge.failed", headers=AUTH).json()
        assert any(e["data"]["object"]["id"] == ch["id"] for e in events["data"])

    def test_retry_after_failed_authentication(self, client):
        pi = _requires_action_pi(client)
        _complete(client, pi["id"], "false")
        body = client.post(f"/v1/payment_intents/{pi['id']}/confirm", headers=AUTH,
                           data={"payment_method": "pm_card_visa"}).json()
        assert body["status"] == "succeeded"
        assert body["last_payment_error"] is None

    def test_wrong_state_400(self, client):
        pi = client.post("/v1/payment_intents", headers={**AUTH, **FORM},
                         content="amount=1000&currency=usd").json()
        r = _complete(client, pi["id"], "true")
        assert r.status_code == 400
        err = r.json()["error"]
        assert err["code"] == "payment_intent_unexpected_state"
        assert "requires_payment_method" in err["message"]

    def test_unknown_pi_404(self, client):
        r = _complete(client, "pi_doesnotexist", "true")
        assert r.status_code == 404
        assert r.json()["error"]["code"] == "resource_missing"

    def test_invalid_succeed_400(self, client):
        pi = _requires_action_pi(client)
        r = _complete(client, pi["id"], "maybe")
        assert r.status_code == 400
        assert r.json()["error"]["param"] == "succeed"

    def test_unknown_param_400(self, client):
        pi = _requires_action_pi(client)
        r = client.post(f"/v1/payment_intents/{pi['id']}/_complete_authentication",
                        headers=AUTH, data={"bogus": "1"})
        assert r.status_code == 400
        assert r.json()["error"]["code"] == "parameter_unknown"

    def test_double_complete_400(self, client):
        pi = _requires_action_pi(client)
        assert _complete(client, pi["id"], "true").status_code == 200
        r = _complete(client, pi["id"], "true")
        assert r.status_code == 400
        assert r.json()["error"]["code"] == "payment_intent_unexpected_state"


class TestThreeDSWebhookIntegration:
    def test_requires_action_event_delivered(self, client):
        """payment_intent.requires_action is a deliverable event type."""
        # No receiver needed: unreachable endpoint still records the attempt.
        ep = client.post(
            "/v1/webhook_endpoints", headers={**AUTH, **FORM},
            content="url=http://127.0.0.1:9769/hook"
                    "&enabled_events[]=payment_intent.requires_action",
        ).json()
        pi = _requires_action_pi(client)

        import time
        deadline = time.monotonic() + 8.0
        rows = []
        while time.monotonic() < deadline:
            rows = client.get("/_admin/webhook_deliveries",
                              params={"endpoint": ep["id"]}).json()["deliveries"]
            if rows:
                break
            time.sleep(0.05)
        assert rows and rows[0]["event_type"] == "payment_intent.requires_action"
        evt = client.get(f"/v1/events/{rows[0]['event']}", headers=AUTH).json()
        assert evt["data"]["object"]["id"] == pi["id"]
