"""Stripe-style form body parsing.

Stripe request bodies are `application/x-www-form-urlencoded` with bracket
notation for nesting:

    metadata[order_id]=6735            -> {"metadata": {"order_id": "6735"}}
    automatic_payment_methods[enabled]=true
    expand[]=latest_charge&expand[]=customer -> {"expand": ["latest_charge", "customer"]}
    line_items[0][price]=price_x       -> {"line_items": [{"price": "price_x"}]}
    a[b][c][d]=1                       -> arbitrary depth

Rules implemented (matching real Stripe):
- Trailing `[]` appends to a list.
- All-numeric sibling keys at a level are folded into a list ordered by index.
- A repeated scalar key keeps the LAST value.
- Values are always strings; type coercion happens at the endpoint layer.
"""

from __future__ import annotations

import json
from urllib.parse import parse_qsl


def split_key(raw_key: str) -> list[str]:
    """Split `a[b][c][]` into ["a", "b", "c", ""].

    Malformed bracket syntax (unbalanced) degrades to the literal key.
    """
    if "[" not in raw_key:
        return [raw_key]
    head, _, rest = raw_key.partition("[")
    if not head or not rest.endswith("]"):
        return [raw_key]
    parts = [head]
    buf = ""
    depth = 1
    for ch in rest:
        if ch == "[":
            if depth != 0:
                # nested '[' inside a segment — malformed
                return [raw_key]
            depth = 1
        elif ch == "]":
            if depth != 1:
                return [raw_key]
            parts.append(buf)
            buf = ""
            depth = 0
        else:
            if depth != 1:
                return [raw_key]
            buf += ch
    if depth != 0:
        return [raw_key]
    return parts


def _assign(root: dict, path: list[str], value: str) -> None:
    node = root
    for i, seg in enumerate(path):
        last = i == len(path) - 1
        if seg == "":
            # Empty bracket: list append. Only supported as trailing segment(s);
            # an intermediate "" creates a fresh dict element per occurrence.
            key = "__list__"
            lst = node.setdefault(key, [])
            if last:
                lst.append(value)
            else:
                new: dict = {}
                lst.append(new)
                node = new
        elif last:
            node[seg] = value
        else:
            nxt = node.get(seg)
            if not isinstance(nxt, dict):
                nxt = {}
                node[seg] = nxt
            node = nxt


def _collapse(node):
    """Convert the intermediate representation into final dicts/lists."""
    if isinstance(node, dict):
        if set(node.keys()) == {"__list__"}:
            return [_collapse(v) for v in node["__list__"]]
        collapsed = {k: _collapse(v) for k, v in node.items() if k != "__list__"}
        # all-numeric keys -> list ordered by integer index
        if collapsed and all(k.isdigit() for k in collapsed):
            return [collapsed[k] for k in sorted(collapsed, key=int)]
        return collapsed
    if isinstance(node, list):
        return [_collapse(v) for v in node]
    return node


def unflatten(pairs: list[tuple[str, str]]) -> dict:
    """Unflatten a list of (bracketed_key, value) pairs into nested data."""
    root: dict = {}
    for raw_key, value in pairs:
        _assign(root, split_key(raw_key), value)
    result = _collapse(root)
    return result if isinstance(result, dict) else {}


def parse_form(body: str | bytes) -> dict:
    """Parse a urlencoded body (or query string) with bracket notation."""
    if isinstance(body, bytes):
        body = body.decode("utf-8", errors="replace")
    pairs = parse_qsl(body, keep_blank_values=True)
    return unflatten(pairs)


async def read_body(request) -> dict:
    """Read a request body as Stripe-style params.

    Primary format is x-www-form-urlencoded with bracket notation. JSON bodies
    are accepted leniently (divergence from real Stripe, documented in
    API_NOTES.md) because agent SDK clients sometimes send JSON.
    """
    raw = await request.body()
    if not raw:
        return {}
    content_type = (request.headers.get("content-type") or "").lower()
    if "application/json" in content_type:
        try:
            data = json.loads(raw)
            return data if isinstance(data, dict) else {}
        except (json.JSONDecodeError, UnicodeDecodeError):
            return {}
    return parse_form(raw)


def parse_query(request) -> dict:
    """Parse a query string with bracket notation (expand[], created[gte], ...)."""
    return parse_form(str(request.url.query))
