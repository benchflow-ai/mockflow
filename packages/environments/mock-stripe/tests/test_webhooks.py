"""Webhook endpoints CRUD + asynchronous delivery tests.

Delivery tests register a real local HTTP receiver (thread-bound
http.server) on a port from this track's assigned range (9761-9769) and
assert that the mock POSTs the standard event JSON with a Stripe-Signature
header that verifies under Stripe's documented scheme
(v1 = HMAC-SHA256(secret, "<t>.<payload>") hex) — i.e. exactly what
stripe.Webhook.construct_event() checks.

Delivery is asynchronous (background thread, no retries), so tests poll with
a deadline instead of sleeping a fixed amount.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from mock_stripe.seed.generator import DEFAULT_API_KEY

AUTH = {"Authorization": f"Bearer {DEFAULT_API_KEY}"}
FORM = {"Content-Type": "application/x-www-form-urlencoded"}

# This track owns ports 9760-9769; 9760 is reserved for live boot checks and
# 9769 is deliberately left unbound (unreachable-URL failure tests).
_RECEIVER_PORTS = range(9761, 9769)
_UNREACHABLE_URL = "http://127.0.0.1:9769/hook"


# ---------------------------------------------------------------------------
# Local webhook receiver
# ---------------------------------------------------------------------------

class _Handler(BaseHTTPRequestHandler):
    def do_POST(self):  # noqa: N802 (http.server API)
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length)
        self.server.requests.append({
            "path": self.path,
            "headers": {k.lower(): v for k, v in self.headers.items()},
            "body": body,
        })
        status = self.server.response_status
        payload = b"ok"
        self.send_response(status)
        self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *args):  # silence per-request stderr noise
        pass


class Receiver:
    """Thread-bound local HTTP server capturing webhook POSTs."""

    def __init__(self):
        last_exc: OSError | None = None
        for port in _RECEIVER_PORTS:
            try:
                self.httpd = ThreadingHTTPServer(("127.0.0.1", port), _Handler)
                self.port = port
                break
            except OSError as exc:
                last_exc = exc
        else:  # pragma: no cover — all assigned ports busy
            raise last_exc
        self.httpd.requests = []
        self.httpd.response_status = 200
        self._thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self._thread.start()

    @property
    def requests(self) -> list[dict]:
        return self.httpd.requests

    def url(self, path: str = "/webhook") -> str:
        return f"http://127.0.0.1:{self.port}{path}"

    def set_response_status(self, status: int) -> None:
        self.httpd.response_status = status

    def close(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        self._thread.join(timeout=5)


@pytest.fixture
def receiver():
    r = Receiver()
    yield r
    r.close()


def wait_until(predicate, timeout: float = 8.0, interval: float = 0.05) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return False


def verify_stripe_signature(secret: str, header: str, body: bytes) -> None:
    """Re-implementation of stripe.Webhook.construct_event's check."""
    parts = dict(item.split("=", 1) for item in header.split(","))
    assert set(parts) >= {"t", "v1"}, f"malformed Stripe-Signature: {header}"
    signed = f"{parts['t']}.{body.decode()}".encode()
    expected = hmac.new(secret.encode(), signed, hashlib.sha256).hexdigest()
    assert hmac.compare_digest(expected, parts["v1"]), "signature mismatch"


def _create_endpoint(client, url: str, events: list[str]) -> dict:
    body = "&".join([f"url={url}"] + [f"enabled_events[]={e}" for e in events])
    r = client.post("/v1/webhook_endpoints", headers={**AUTH, **FORM}, content=body)
    assert r.status_code == 200, r.text
    return r.json()


def _deliveries(client, **params) -> list[dict]:
    r = client.get("/_admin/webhook_deliveries", params=params)
    assert r.status_code == 200
    return r.json()["deliveries"]


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------

class TestWebhookEndpointCrud:
    def test_create_returns_secret_once(self, client):
        ep = _create_endpoint(client, "https://example.com/my/webhook/endpoint",
                              ["charge.succeeded", "charge.failed"])
        assert ep["object"] == "webhook_endpoint"
        assert ep["id"].startswith("we_")
        assert ep["secret"].startswith("whsec_") and len(ep["secret"]) == 38
        assert ep["enabled_events"] == ["charge.succeeded", "charge.failed"]
        assert ep["status"] == "enabled"
        assert ep["livemode"] is False

        # secret is NEVER returned again — retrieve, list, update (real behavior)
        got = client.get(f"/v1/webhook_endpoints/{ep['id']}", headers=AUTH).json()
        assert "secret" not in got
        assert got["url"] == "https://example.com/my/webhook/endpoint"
        listed = client.get("/v1/webhook_endpoints", headers=AUTH).json()
        assert listed["object"] == "list"
        assert all("secret" not in item for item in listed["data"])
        updated = client.post(f"/v1/webhook_endpoints/{ep['id']}", headers=AUTH,
                              data={"description": "main"}).json()
        assert "secret" not in updated
        assert updated["description"] == "main"

    def test_create_missing_url(self, client):
        r = client.post("/v1/webhook_endpoints", headers={**AUTH, **FORM},
                        content="enabled_events[]=charge.succeeded")
        assert r.status_code == 400
        assert r.json()["error"]["param"] == "url"
        assert r.json()["error"]["code"] == "parameter_missing"

    def test_create_missing_enabled_events(self, client):
        r = client.post("/v1/webhook_endpoints", headers=AUTH,
                        data={"url": "https://example.com/hook"})
        assert r.status_code == 400
        assert r.json()["error"]["param"] == "enabled_events"

    def test_create_url_requires_scheme(self, client):
        r = client.post("/v1/webhook_endpoints", headers={**AUTH, **FORM},
                        content="url=example.com/hook&enabled_events[]=*")
        assert r.status_code == 400
        assert "explicit scheme" in r.json()["error"]["message"]

    def test_wildcard_must_be_alone(self, client):
        r = client.post("/v1/webhook_endpoints", headers={**AUTH, **FORM},
                        content="url=https://example.com/h&enabled_events[]=*"
                                "&enabled_events[]=charge.succeeded")
        assert r.status_code == 400
        assert "'*'" in r.json()["error"]["message"]

    def test_unknown_param_rejected(self, client):
        r = client.post("/v1/webhook_endpoints", headers={**AUTH, **FORM},
                        content="url=https://example.com/h&enabled_events[]=*&bogus=1")
        assert r.status_code == 400
        assert r.json()["error"]["code"] == "parameter_unknown"

    def test_update_events_url_and_disabled(self, client):
        ep = _create_endpoint(client, "https://example.com/a", ["charge.succeeded"])
        r = client.post(
            f"/v1/webhook_endpoints/{ep['id']}", headers={**AUTH, **FORM},
            content="url=https://example.com/b&enabled_events[]=customer.created"
                    "&disabled=true&metadata[env]=test",
        )
        assert r.status_code == 200
        body = r.json()
        assert body["url"] == "https://example.com/b"
        assert body["enabled_events"] == ["customer.created"]
        assert body["status"] == "disabled"
        assert body["metadata"] == {"env": "test"}
        # re-enable
        body = client.post(f"/v1/webhook_endpoints/{ep['id']}", headers=AUTH,
                           data={"disabled": "false"}).json()
        assert body["status"] == "enabled"

    def test_delete(self, client):
        ep = _create_endpoint(client, "https://example.com/h", ["*"])
        r = client.delete(f"/v1/webhook_endpoints/{ep['id']}", headers=AUTH)
        assert r.status_code == 200
        assert r.json() == {"id": ep["id"], "object": "webhook_endpoint", "deleted": True}
        r = client.get(f"/v1/webhook_endpoints/{ep['id']}", headers=AUTH)
        assert r.status_code == 404
        assert r.json()["error"]["code"] == "resource_missing"

    def test_unknown_endpoint_404(self, client):
        r = client.get("/v1/webhook_endpoints/we_nope", headers=AUTH)
        assert r.status_code == 404
        assert "No such webhook endpoint" in r.json()["error"]["message"]

    def test_requires_auth(self, client):
        assert client.get("/v1/webhook_endpoints").status_code == 401
        assert client.post("/v1/webhook_endpoints",
                           data={"url": "https://x.test"}).status_code == 401


# ---------------------------------------------------------------------------
# Delivery
# ---------------------------------------------------------------------------

class TestWebhookDelivery:
    def test_event_delivered_with_verifiable_signature(self, client, receiver):
        ep = _create_endpoint(client, receiver.url(), ["*"])
        secret = ep["secret"]

        customer = client.post("/v1/customers", headers=AUTH,
                               data={"name": "Hook Test"}).json()
        assert wait_until(lambda: len(receiver.requests) >= 1)
        req = receiver.requests[0]

        # Standard event JSON payload
        payload = json.loads(req["body"])
        assert payload["object"] == "event"
        assert payload["type"] == "customer.created"
        assert payload["data"]["object"]["id"] == customer["id"]
        assert payload["api_version"]
        assert payload["pending_webhooks"] == 1
        assert req["headers"]["content-type"] == "application/json"

        # Signature verifies exactly as stripe.Webhook.construct_event would
        verify_stripe_signature(secret, req["headers"]["stripe-signature"], req["body"])

        # Recorded event matches the delivered one
        evt = client.get(f"/v1/events/{payload['id']}", headers=AUTH).json()
        assert evt["type"] == "customer.created"

    def test_signature_fails_with_wrong_secret(self, client, receiver):
        _create_endpoint(client, receiver.url(), ["*"])
        client.post("/v1/customers", headers=AUTH, data={"name": "X"})
        assert wait_until(lambda: len(receiver.requests) >= 1)
        req = receiver.requests[0]
        with pytest.raises(AssertionError):
            verify_stripe_signature("whsec_wrong", req["headers"]["stripe-signature"],
                                    req["body"])

    def test_enabled_events_filtering(self, client, receiver):
        _create_endpoint(client, receiver.url(), ["payment_intent.succeeded"])

        # Non-matching event: nothing delivered
        client.post("/v1/customers", headers=AUTH, data={"name": "NoHook"})

        # Matching flow: confirm emits payment_intent.created, charge.succeeded,
        # payment_intent.succeeded — only the last one matches.
        pi = client.post("/v1/payment_intents", headers={**AUTH, **FORM},
                         content="amount=1500&currency=usd").json()
        confirmed = client.post(f"/v1/payment_intents/{pi['id']}/confirm", headers=AUTH,
                                data={"payment_method": "pm_card_visa"}).json()
        assert confirmed["status"] == "succeeded"

        assert wait_until(lambda: len(receiver.requests) >= 1)
        time.sleep(0.3)  # grace period: any extra (wrong) deliveries would land now
        types = [json.loads(r["body"])["type"] for r in receiver.requests]
        assert types == ["payment_intent.succeeded"]
        assert json.loads(receiver.requests[0]["body"])["data"]["object"]["id"] == pi["id"]

    def test_delivery_log_records_success(self, client, receiver):
        ep = _create_endpoint(client, receiver.url(), ["customer.created"])
        client.post("/v1/customers", headers=AUTH, data={"name": "Logged"})
        assert wait_until(lambda: len(_deliveries(client, endpoint=ep["id"])) >= 1)

        rows = _deliveries(client, endpoint=ep["id"])
        assert len(rows) == 1
        row = rows[0]
        assert row["object"] == "webhook_delivery"
        assert row["id"].startswith("whd_")
        assert row["webhook_endpoint"] == ep["id"]
        assert row["event"].startswith("evt_")
        assert row["event_type"] == "customer.created"
        assert row["url"] == receiver.url()
        assert row["status_code"] == 200
        assert row["error"] is None
        assert row["success"] is True

        # event filter works too
        assert _deliveries(client, event=row["event"])[0]["id"] == row["id"]

    def test_unreachable_url_records_error_api_unaffected(self, client):
        ep = _create_endpoint(client, _UNREACHABLE_URL, ["customer.created"])

        # The API call itself is unaffected by the failing delivery
        r = client.post("/v1/customers", headers=AUTH, data={"name": "Unreachable"})
        assert r.status_code == 200

        assert wait_until(lambda: len(_deliveries(client, endpoint=ep["id"])) >= 1)
        row = _deliveries(client, endpoint=ep["id"])[0]
        assert row["status_code"] is None
        assert row["error"]  # transport error text, e.g. ConnectError
        assert row["success"] is False

        # ...and the customer + event were still recorded normally
        events = client.get("/v1/events?type=customer.created", headers=AUTH).json()
        assert any(e["data"]["object"]["name"] == "Unreachable" for e in events["data"])

    def test_non_2xx_response_recorded(self, client, receiver):
        receiver.set_response_status(500)
        ep = _create_endpoint(client, receiver.url("/fail"), ["customer.created"])
        client.post("/v1/customers", headers=AUTH, data={"name": "FiveHundred"})
        assert wait_until(lambda: len(_deliveries(client, endpoint=ep["id"])) >= 1)
        row = _deliveries(client, endpoint=ep["id"])[0]
        assert row["status_code"] == 500
        assert row["error"] is None
        assert row["success"] is False
        # v1 divergence: exactly one attempt, no retries
        time.sleep(0.3)
        assert len(_deliveries(client, endpoint=ep["id"])) == 1

    def test_disabled_endpoint_not_delivered(self, client, receiver):
        ep = _create_endpoint(client, receiver.url(), ["*"])
        client.post(f"/v1/webhook_endpoints/{ep['id']}", headers=AUTH,
                    data={"disabled": "true"})
        client.post("/v1/customers", headers=AUTH, data={"name": "Silent"})
        time.sleep(0.5)
        assert receiver.requests == []
        assert _deliveries(client, endpoint=ep["id"]) == []

    def test_multiple_endpoints_each_delivered(self, client, receiver):
        ep_a = _create_endpoint(client, receiver.url("/a"), ["*"])
        ep_b = _create_endpoint(client, receiver.url("/b"), ["customer.created"])
        client.post("/v1/customers", headers=AUTH, data={"name": "Fanout"})
        assert wait_until(lambda: len(receiver.requests) >= 2)
        paths = sorted(r["path"] for r in receiver.requests)
        assert paths == ["/a", "/b"]
        # pending_webhooks reflects the fanout size
        assert json.loads(receiver.requests[0]["body"])["pending_webhooks"] == 2
        assert {d["webhook_endpoint"] for d in _deliveries(client)} == {ep_a["id"], ep_b["id"]}


# ---------------------------------------------------------------------------
# Snapshots / reset
# ---------------------------------------------------------------------------

class TestWebhookStateManagement:
    def test_snapshot_restore_includes_endpoints_and_deliveries(self, client, receiver):
        ep = _create_endpoint(client, receiver.url(), ["customer.created"])
        client.post("/v1/customers", headers=AUTH, data={"name": "Snap"})
        assert wait_until(lambda: len(_deliveries(client, endpoint=ep["id"])) >= 1)

        assert client.post("/_admin/snapshot/with-webhooks").json()["status"] == "ok"
        client.delete(f"/v1/webhook_endpoints/{ep['id']}", headers=AUTH)
        assert client.get(f"/v1/webhook_endpoints/{ep['id']}", headers=AUTH).status_code == 404

        assert client.post("/_admin/restore/with-webhooks").json()["status"] == "ok"
        restored = client.get(f"/v1/webhook_endpoints/{ep['id']}", headers=AUTH)
        assert restored.status_code == 200
        assert restored.json()["enabled_events"] == ["customer.created"]
        # deliveries are snapshotted too (documented decision)
        assert len(_deliveries(client, endpoint=ep["id"])) >= 1
        # the signing secret survives restore (internal state)
        state = client.get("/_admin/state").json()
        row = [r for r in state["webhook_endpoints"] if r["id"] == ep["id"]][0]
        assert row["secret"] == ep["secret"]

    def test_diff_and_reset(self, client):
        ep = _create_endpoint(client, "https://example.com/h", ["*"])
        diff = client.get("/_admin/diff").json()
        assert any(row["id"] == ep["id"] for row in diff["added"]["webhook_endpoints"])

        client.post("/_admin/reset")
        assert client.get(f"/v1/webhook_endpoints/{ep['id']}", headers=AUTH).status_code == 404
        assert client.get("/v1/webhook_endpoints", headers=AUTH).json()["data"] == []
        assert _deliveries(client) == []
