"""Stripe cursor pagination: limit (1-100, default 10), starting_after, ending_before.

Lists are reverse-chronological (newest first). The total order is the
insertion sequence (`seq` column) since `created` is unix-seconds and too
coarse to break ties.
"""

from __future__ import annotations

from .errors import StripeError
from .serializers import list_envelope


def parse_limit(params: dict) -> int:
    raw = params.get("limit")
    if raw in (None, ""):
        return 10
    try:
        limit = int(raw)
    except (TypeError, ValueError):
        raise StripeError(400, f"Invalid integer: {raw}", param="limit")
    if limit < 1 or limit > 100:
        raise StripeError(
            400,
            f"limit must be between 1 and 100, but was {limit}",
            param="limit",
        )
    return limit


def paginate(items: list, params: dict, url: str, serialize, *, kind: str) -> dict:
    """Paginate a pre-sorted (newest-first) list of ORM rows into a list envelope.

    `items` MUST already be ordered seq desc. `serialize` maps row -> dict.
    """
    limit = parse_limit(params)
    starting_after = params.get("starting_after") or None
    ending_before = params.get("ending_before") or None
    if starting_after and ending_before:
        raise StripeError(
            400,
            "You cannot use both starting_after and ending_before in the same request.",
            param="starting_after",
        )

    def _index_of(obj_id: str, param: str) -> int:
        for i, item in enumerate(items):
            if item.id == obj_id:
                return i
        raise StripeError(400, f"No such {kind}: '{obj_id}'", code="resource_missing", param=param)

    if starting_after:
        idx = _index_of(starting_after, "starting_after")
        page = items[idx + 1 : idx + 1 + limit]
        has_more = len(items) > idx + 1 + limit
    elif ending_before:
        idx = _index_of(ending_before, "ending_before")
        start = max(0, idx - limit)
        page = items[start:idx]
        has_more = start > 0
    else:
        page = items[:limit]
        has_more = len(items) > limit

    return list_envelope(url, [serialize(i) for i in page], has_more)


def apply_created_filter(items: list, params: dict) -> list:
    """Filter rows by `created` / `created[gt|gte|lt|lte]` query params."""
    created = params.get("created")
    if created is None:
        return items
    if isinstance(created, str):
        try:
            ts = int(created)
        except ValueError:
            raise StripeError(400, f"Invalid integer: {created}", param="created")
        return [i for i in items if i.created == ts]
    if isinstance(created, dict):
        ops = {}
        for op in ("gt", "gte", "lt", "lte"):
            if op in created:
                try:
                    ops[op] = int(created[op])
                except (TypeError, ValueError):
                    raise StripeError(400, f"Invalid integer: {created[op]}", param=f"created[{op}]")
        out = items
        if "gt" in ops:
            out = [i for i in out if i.created > ops["gt"]]
        if "gte" in ops:
            out = [i for i in out if i.created >= ops["gte"]]
        if "lt" in ops:
            out = [i for i in out if i.created < ops["lt"]]
        if "lte" in ops:
            out = [i for i in out if i.created <= ops["lte"]]
        return out
    return items
