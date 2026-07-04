"""Event recording — every mutation records a Stripe Event row.

Recorded events are also dispatched to matching webhook endpoints
(see webhook_dispatch.py). Seed-time events (rng provided) are NOT
dispatched: they predate any webhook endpoint and must stay deterministic.
"""

from __future__ import annotations

import json
import time

from sqlalchemy.orm import Session

from mock_stripe.ids import generate_id
from mock_stripe.models import Event

from .serializers import API_VERSION


def record_event(
    db: Session,
    event_type: str,
    obj_snapshot: dict,
    *,
    idempotency_key: str | None = None,
    created: int | None = None,
    rng=None,
) -> Event:
    """Record an event with a full object snapshot in data.object."""
    evt = Event(
        id=generate_id("evt", rng=rng),
        type=event_type,
        api_version=API_VERSION,
        data_json=json.dumps({"object": obj_snapshot}),
        request_idempotency_key=idempotency_key,
        created=created if created is not None else int(time.time()),
    )
    db.add(evt)
    if rng is None:  # runtime API event (seeds pass rng) -> deliver webhooks
        from .webhook_dispatch import dispatch_event

        dispatch_event(db, evt)
    return evt
