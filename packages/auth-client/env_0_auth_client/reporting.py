"""Security-event reporting back to auth (fire-and-forget, errors swallowed).

Events POST to ``{AUTH_URL}/_admin/report_event`` with JSON:
    {"event_type": ..., "client_id": ..., "user_id": ..., "scope": ..., "details": {...}}

Event types emitted by this package:
- invalid_token             -- malformed/bad-signature/bad-issuer/unknown-kid tokens
- token_expired_during_use  -- a structurally valid token presented after exp
- scope_escalation_attempt  -- valid token, insufficient scope for the route
- impersonation_attempt     -- via report_impersonation() (called by the deps layer)
- resource_access           -- aggregated successful (2xx) accesses, for scope-usage metrics

Reporting is ON by default and entirely disabled with AUTH_REPORT=0.
All transport failures are swallowed -- reporting must never break a request.
Tests inject an ``httpx.MockTransport`` via :func:`set_transport` so no real
HTTP is performed.
"""

import threading

import httpx

from env_0_auth_client import config

REPORT_PATH = "/_admin/report_event"
_TIMEOUT = 2.0

# Test hook: an httpx transport used for all report POSTs (sync and async).
_transport = None


def set_transport(transport) -> None:
    """Inject an httpx transport (e.g. httpx.MockTransport) for tests. None resets."""
    global _transport
    _transport = transport


def _report_url(auth_base_url: str | None = None) -> str:
    return (auth_base_url or config.get_auth_url()).rstrip("/") + REPORT_PATH


def build_event(
    event_type: str,
    client_id: str | None = None,
    user_id: str | None = None,
    scope: str | None = None,
    details: dict | None = None,
) -> dict:
    return {
        "event_type": event_type,
        "client_id": client_id,
        "user_id": user_id,
        "scope": scope,
        "details": details or {},
    }


def report_event(payload: dict, auth_base_url: str | None = None) -> None:
    """Synchronous fire-and-forget event report. No-op when AUTH_REPORT=0."""
    if not config.is_report_enabled():
        return
    try:
        with httpx.Client(transport=_transport, timeout=_TIMEOUT) as client:
            client.post(_report_url(auth_base_url), json=payload)
    except Exception:
        pass


async def report_event_async(payload: dict, auth_base_url: str | None = None) -> None:
    """Async fire-and-forget event report. No-op when AUTH_REPORT=0."""
    if not config.is_report_enabled():
        return
    try:
        async with httpx.AsyncClient(transport=_transport, timeout=_TIMEOUT) as client:
            await client.post(_report_url(auth_base_url), json=payload)
    except Exception:
        pass


def report_impersonation(
    authenticated_user: str,
    requested_user: str,
    *,
    client_id: str | None = None,
    scope: str | None = None,
    details: dict | None = None,
    auth_base_url: str | None = None,
) -> None:
    """Report an impersonation attempt (path userId != token sub).

    Called by the resource server's deps layer (e.g. ``resolve_user_id``) right
    before raising the 403 impersonation error -- the middleware itself cannot
    see path-vs-sub mismatches. Fire-and-forget; safe to call from sync code.
    """
    payload = build_event(
        "impersonation_attempt",
        client_id=client_id,
        user_id=authenticated_user,
        scope=scope,
        details={
            "authenticated_user": authenticated_user,
            "requested_user": requested_user,
            **(details or {}),
        },
    )
    report_event(payload, auth_base_url)


class ResourceAccessAggregator:
    """Batches successful-access events: flush on every NEW (client, user, route)
    combo, or after 20 requests since the last flush. Counts accumulate per combo
    between flushes.
    """

    FLUSH_EVERY = 20

    def __init__(self):
        self._pending: dict[tuple, dict] = {}
        self._seen: set[tuple] = set()
        self._since_flush = 0
        # Guards the read-modify-write of _pending/_seen/_since_flush. record() is
        # synchronous so it already serializes on the asyncio loop, but the lock makes
        # it correct even if a resource server runs the middleware across worker threads.
        self._lock = threading.Lock()

    def record(
        self,
        *,
        client_id: str | None,
        user_id: str | None,
        method: str,
        route: str,
        scope_used: str,
        token_scope: str,
    ) -> list[dict]:
        """Record one successful access; return the event payloads to send (may be empty)."""
        key = (client_id, user_id, method, route)
        with self._lock:
            is_new = key not in self._seen
            self._seen.add(key)
            entry = self._pending.setdefault(
                key,
                {
                    "client_id": client_id,
                    "user_id": user_id,
                    "method": method,
                    "route": route,
                    "scope_used": scope_used,
                    "token_scope": token_scope,
                    "count": 0,
                },
            )
            entry["count"] += 1
            self._since_flush += 1
            if is_new or self._since_flush >= self.FLUSH_EVERY:
                return self._flush_locked()
            return []

    def flush(self) -> list[dict]:
        """Build one resource_access event per pending combo and reset the batch."""
        with self._lock:
            return self._flush_locked()

    def _flush_locked(self) -> list[dict]:
        """Flush body — caller must hold self._lock."""
        events = []
        for entry in self._pending.values():
            payload = build_event(
                "resource_access",
                client_id=entry["client_id"],
                user_id=entry["user_id"],
                scope=entry["token_scope"],
                details={
                    "method": entry["method"],
                    "route": entry["route"],
                    "count": entry["count"],
                },
            )
            payload["scope_used"] = entry["scope_used"]
            events.append(payload)
        self._pending.clear()
        self._since_flush = 0
        return events
