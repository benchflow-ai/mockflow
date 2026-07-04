"""Asynchronous webhook delivery (background threads + httpx).

Implements Stripe's documented signature scheme exactly, so
`stripe.Webhook.construct_event(payload, sig_header, secret)` verifies:

    Stripe-Signature: t=<unix ts>,v1=<HMAC-SHA256 hex of "<ts>.<payload>"
                                       keyed by the endpoint's whsec_ secret>

Divergences vs real Stripe (documented in API_NOTES.md):
- exactly ONE delivery attempt per (event, endpoint) — no retries/backoff
  (real Stripe retries with exponential backoff for up to ~3 days);
- 5s request timeout (real Stripe allows considerably longer);
- delivery attempts are recorded in the mock-only `webhook_deliveries` table
  exposed at `GET /_admin/webhook_deliveries`.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import threading
import time

import httpx
from sqlalchemy.orm import Session

from mock_stripe.ids import generate_id
from mock_stripe.models import Event, WebhookEndpoint

TIMEOUT_SECONDS = 5.0
USER_AGENT = "Stripe/1.0 (+https://stripe.com/docs/webhooks)"


def compute_signature_header(secret: str, payload: str, timestamp: int) -> str:
    """Stripe-Signature header value for `payload` at `timestamp`."""
    signed = f"{timestamp}.{payload}".encode()
    v1 = hmac.new(secret.encode(), signed, hashlib.sha256).hexdigest()
    return f"t={timestamp},v1={v1}"


def _endpoint_matches(enabled_events: list, event_type: str) -> bool:
    return "*" in enabled_events or event_type in enabled_events


def dispatch_event(db: Session, event: Event) -> int:
    """Deliver `event` to every enabled endpoint whose enabled_events match.

    Called synchronously from `record_event`; the actual HTTP POSTs run on
    daemon background threads so the API request is never blocked. Returns the
    number of matched endpoints.
    """
    endpoints = (
        db.query(WebhookEndpoint).filter(WebhookEndpoint.status == "enabled").all()
    )
    matched = [
        ep
        for ep in endpoints
        if _endpoint_matches(json.loads(ep.enabled_events_json or "[]"), event.type)
    ]
    if not matched:
        return 0

    from .serializers import event_to_dict

    payload = event_to_dict(event)
    # Real Stripe payloads carry the number of still-pending deliveries.
    payload["pending_webhooks"] = len(matched)
    body = json.dumps(payload)

    for ep in matched:
        threading.Thread(
            target=_deliver,
            args=(ep.id, ep.url, ep.secret, event.id, event.type, body),
            daemon=True,
            name=f"webhook-delivery-{ep.id}",
        ).start()
    return len(matched)


def _deliver(
    endpoint_id: str,
    url: str,
    secret: str,
    event_id: str,
    event_type: str,
    body: str,
) -> None:
    """One delivery attempt: POST the signed payload, then record the result."""
    timestamp = int(time.time())
    headers = {
        "Content-Type": "application/json",
        "Stripe-Signature": compute_signature_header(secret, body, timestamp),
        "User-Agent": USER_AGENT,
    }
    status_code: int | None = None
    error: str | None = None
    try:
        response = httpx.post(url, content=body, headers=headers, timeout=TIMEOUT_SECONDS)
        status_code = response.status_code
    except Exception as exc:  # transport-level failure (refused/timeout/DNS/...)
        error = f"{type(exc).__name__}: {exc}"
    _record_delivery(endpoint_id, event_id, event_type, url, status_code, error)


def _record_delivery(
    endpoint_id: str,
    event_id: str,
    event_type: str,
    url: str,
    status_code: int | None,
    error: str | None,
) -> None:
    """Write the webhook_deliveries row from the delivery thread.

    Retries briefly on SQLite write contention; any other failure is swallowed
    (a delivery thread must never crash the process or block forever).
    """
    from sqlalchemy.exc import OperationalError

    from mock_stripe.models import WebhookDelivery, get_session_factory

    row_kwargs = dict(
        id=generate_id("whd"),
        endpoint_id=endpoint_id,
        event_id=event_id,
        event_type=event_type,
        url=url,
        status_code=status_code,
        error=error,
        success=status_code is not None and 200 <= status_code < 300,
        created=int(time.time()),
    )
    for _attempt in range(20):
        try:
            db = get_session_factory()()
        except Exception:
            return  # engine torn down (e.g. test teardown) — nothing to record into
        try:
            db.add(WebhookDelivery(**row_kwargs))
            db.commit()
            return
        except OperationalError:
            db.rollback()
            time.sleep(0.05)
        except Exception:
            db.rollback()
            return
        finally:
            db.close()
