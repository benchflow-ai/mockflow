"""Events: GET /v1/events (?type= with trailing-* glob, types[]=...), GET /{id}."""

from __future__ import annotations

import fnmatch

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from mock_stripe.models import Event

from .deps import get_db, require_api_key
from .errors import resource_missing
from .forms import parse_query
from .pagination import apply_created_filter, paginate
from .serializers import event_to_dict

router = APIRouter(dependencies=[Depends(require_api_key)])


@router.get("/v1/events")
def list_events(request: Request, db: Session = Depends(get_db)):
    params = parse_query(request)
    items = db.query(Event).order_by(Event.seq.desc()).all()
    if params.get("type"):
        pattern = params["type"]
        if "*" in pattern:
            items = [e for e in items if fnmatch.fnmatchcase(e.type, pattern)]
        else:
            items = [e for e in items if e.type == pattern]
    types = params.get("types")
    if types:
        if isinstance(types, str):
            types = [types]
        items = [e for e in items if e.type in set(types)]
    items = apply_created_filter(items, params)
    return paginate(items, params, "/v1/events", event_to_dict, kind="event")


@router.get("/v1/events/{event_id}")
def get_event(event_id: str, db: Session = Depends(get_db)):
    event = db.get(Event, event_id)
    if event is None:
        raise resource_missing("event", event_id)
    return event_to_dict(event)
