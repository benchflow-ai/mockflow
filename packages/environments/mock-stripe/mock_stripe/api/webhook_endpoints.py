"""WebhookEndpoints CRUD: /v1/webhook_endpoints.

Real-Stripe-faithful behaviors:
- `secret` (whsec_...) is returned ONLY by create — retrieve/update/list/delete
  never include it.
- `enabled_events` is a list of full event-type names, or `["*"]` for all
  events; `"*"` cannot be combined with other types.
- update accepts `disabled=true|false` to toggle `status`.
- delete returns the `{id, object, deleted: true}` stub.

Delivery itself lives in webhook_dispatch.py (hooked into record_event).
"""

from __future__ import annotations

import json
import time
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from mock_stripe.ids import generate_id, generate_webhook_secret
from mock_stripe.models import WebhookEndpoint

from .customers import _merge_metadata
from .deps import get_db, require_api_key
from .errors import StripeError, as_bool, check_unknown_params, missing_param
from .forms import parse_query, read_body
from .pagination import apply_created_filter, paginate
from .serializers import webhook_endpoint_to_dict

router = APIRouter(dependencies=[Depends(require_api_key)])

_CREATE_PARAMS = {"url", "enabled_events", "description", "metadata", "api_version", "connect"}
_UPDATE_PARAMS = {"url", "enabled_events", "description", "metadata", "disabled"}


def _get_endpoint_or_404(db: Session, we_id: str) -> WebhookEndpoint:
    ep = db.get(WebhookEndpoint, we_id)
    if ep is None:
        raise StripeError(
            404,
            f"No such webhook endpoint: '{we_id}'",
            code="resource_missing",
            param="id",
        )
    return ep


def _validate_url(url) -> str:
    url = str(url or "")
    scheme = urlparse(url).scheme
    if scheme not in ("http", "https") or not urlparse(url).netloc:
        # Real Stripe message; http URLs are allowed in test mode (this whole
        # mock is test mode), so local receivers work.
        raise StripeError(
            400,
            "Invalid URL: An explicit scheme (such as https) must be provided.",
            param="url",
        )
    return url


def _normalize_enabled_events(value) -> list[str]:
    if isinstance(value, str):
        value = [value]
    elif isinstance(value, dict):  # indexed form enabled_events[0]=...
        value = [value[k] for k in sorted(value)]
    if not isinstance(value, list) or not value or not all(isinstance(v, str) and v for v in value):
        raise StripeError(
            400,
            "Invalid array: enabled_events must be a non-empty list of event types.",
            param="enabled_events",
        )
    events = [str(v) for v in value]
    if "*" in events and len(events) > 1:
        raise StripeError(
            400,
            "You cannot specify '*' along with other event types.",
            param="enabled_events",
        )
    return events


@router.post("/v1/webhook_endpoints")
async def create_webhook_endpoint(request: Request, db: Session = Depends(get_db)):
    data = await read_body(request)
    check_unknown_params(data, _CREATE_PARAMS)
    if not data.get("url"):
        raise missing_param("url")
    if "enabled_events" not in data:
        raise missing_param("enabled_events")
    url = _validate_url(data["url"])
    enabled_events = _normalize_enabled_events(data["enabled_events"])

    ep = WebhookEndpoint(
        id=generate_id("we"),
        url=url,
        description=data.get("description") or None,
        enabled_events_json=json.dumps(enabled_events),
        secret=generate_webhook_secret(),
        status="enabled",
        api_version=data.get("api_version") or None,
        metadata_json=_merge_metadata("{}", data.get("metadata")),
        created=int(time.time()),
    )
    db.add(ep)
    db.commit()
    # The ONLY response that ever includes the whsec_ signing secret.
    return webhook_endpoint_to_dict(ep, include_secret=True)


@router.get("/v1/webhook_endpoints")
def list_webhook_endpoints(request: Request, db: Session = Depends(get_db)):
    params = parse_query(request)
    items = db.query(WebhookEndpoint).order_by(WebhookEndpoint.seq.desc()).all()
    items = apply_created_filter(items, params)
    return paginate(items, params, "/v1/webhook_endpoints", webhook_endpoint_to_dict,
                    kind="webhook_endpoint")


@router.get("/v1/webhook_endpoints/{we_id}")
def get_webhook_endpoint(we_id: str, db: Session = Depends(get_db)):
    return webhook_endpoint_to_dict(_get_endpoint_or_404(db, we_id))


@router.post("/v1/webhook_endpoints/{we_id}")
async def update_webhook_endpoint(we_id: str, request: Request, db: Session = Depends(get_db)):
    data = await read_body(request)
    check_unknown_params(data, _UPDATE_PARAMS)
    ep = _get_endpoint_or_404(db, we_id)

    if "url" in data:
        ep.url = _validate_url(data["url"])
    if "enabled_events" in data:
        ep.enabled_events_json = json.dumps(_normalize_enabled_events(data["enabled_events"]))
    if "description" in data:
        ep.description = data["description"] or None
    if "metadata" in data:
        ep.metadata_json = _merge_metadata(ep.metadata_json, data["metadata"])
    if "disabled" in data:
        disabled = as_bool(data, "disabled")
        if disabled is not None:
            ep.status = "disabled" if disabled else "enabled"

    db.commit()
    return webhook_endpoint_to_dict(ep)


@router.delete("/v1/webhook_endpoints/{we_id}")
def delete_webhook_endpoint(we_id: str, db: Session = Depends(get_db)):
    ep = _get_endpoint_or_404(db, we_id)
    db.delete(ep)
    db.commit()
    return {"id": we_id, "object": "webhook_endpoint", "deleted": True}
