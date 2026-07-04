"""Per-route OAuth scope requirements for auth (used when AUTH_ENABLED=1).

``SCOPE_MAP`` keys are ``(HTTP_METHOD, route_path_template)`` tuples EXACTLY as
the routes are registered on the FastAPI app (see ``mock_gcal/api/app.py``).
Values are OR-logic scope lists: ANY one listed scope grants access. Routes
absent from the map (and exempt prefixes like /_admin, /health, /dev, /mcp)
require a valid token but no particular scope.

Scope names are the bare auth names (``calendar.readonly``, not full
Google URLs). The contract pins exactly four Calendar scopes:

- ``calendar.readonly``        read calendars, events, freebusy
- ``calendar.events``          CRUD on events
- ``calendar.events.readonly`` read events only
- ``calendar.full``            all Calendar operations

Mapping (per the pinned contract, mirroring real Google Calendar semantics):

- reads                  -> calendar.readonly | calendar.events | calendar.full
  (+ calendar.events.readonly for event GETs, which never expose anything
  beyond events)
- event mutations        -> calendar.events | calendar.full
- calendar / calendarList mutations -> calendar.full only
- ACL (sharing) endpoints -> calendar.full ONLY, including reads: real Google
  gates every Acl method behind the full calendar scope
- freebusy               -> calendar.readonly | calendar.full (contract pin)
- channels.stop          -> any calendar scope (real Google allows stopping a
  channel with whichever scope created it)

This module deliberately has NO env_0_auth_client import so that gcal
works unchanged when auth-client is not installed.

Coverage of every registered /calendar/v3 route is enforced by
``tests/test_auth_integration.py::TestScopeMapCoverage``.
"""

from __future__ import annotations

# Mirrors env_0_auth_client.ScopeMap (kept local: auth-client is optional).
ScopeMap = dict[tuple[str, str], list[str]]

GCAL_PREFIX = "/calendar/v3"
_U = f"{GCAL_PREFIX}/users/{{userId}}"
_C = f"{GCAL_PREFIX}/calendars/{{calendarId}}"

FULL = "calendar.full"  # equivalent of https://www.googleapis.com/auth/calendar
READONLY = "calendar.readonly"
EVENTS = "calendar.events"
EVENTS_READONLY = "calendar.events.readonly"

# General (non-event) reads: calendarList, calendars.get, settings, colors,
# profile. calendar.events is accepted per the pinned contract read list;
# calendar.events.readonly is NOT (it is events-only).
READ = [READONLY, EVENTS, FULL]
# Event GETs (list/get/instances) and events.watch: also calendar.events.readonly.
EVENT_READ = [READONLY, EVENTS_READONLY, EVENTS, FULL]
# Event mutations (insert/import/update/patch/move/quickAdd/delete).
EVENT_WRITE = [EVENTS, FULL]
# Calendar + calendarList mutations: full access only.
MANAGE = [FULL]
# ACL/sharing endpoints (ALL of them, reads included): full access only,
# like real Google Calendar. The delegated-access track relies on this.
ACL = [FULL]
# freebusy query (contract pin: readonly|full).
FREEBUSY = [READONLY, FULL]
# channels.stop: any calendar scope may stop a watch channel.
CHANNEL_STOP = [READONLY, EVENTS_READONLY, EVENTS, FULL]

SCOPE_MAP: ScopeMap = {
    # --- calendarList ---
    ("GET", f"{_U}/calendarList"): READ,
    ("GET", f"{_U}/calendarList/{{calendarId}}"): READ,
    ("POST", f"{_U}/calendarList"): MANAGE,
    ("PATCH", f"{_U}/calendarList/{{calendarId}}"): MANAGE,
    ("PUT", f"{_U}/calendarList/{{calendarId}}"): MANAGE,
    ("DELETE", f"{_U}/calendarList/{{calendarId}}"): MANAGE,
    ("POST", f"{_U}/calendarList/watch"): READ,
    # --- calendars ---
    ("GET", _C): READ,
    ("POST", f"{GCAL_PREFIX}/calendars"): MANAGE,
    ("PATCH", _C): MANAGE,
    ("PUT", _C): MANAGE,
    ("POST", f"{_C}/clear"): MANAGE,
    ("DELETE", _C): MANAGE,
    # --- events ---
    ("GET", f"{_C}/events"): EVENT_READ,
    ("GET", f"{_C}/events/{{eventId}}"): EVENT_READ,
    ("GET", f"{_C}/events/{{eventId}}/instances"): EVENT_READ,
    ("POST", f"{_C}/events"): EVENT_WRITE,
    ("POST", f"{_C}/events/import"): EVENT_WRITE,
    ("PUT", f"{_C}/events/{{eventId}}"): EVENT_WRITE,
    ("PATCH", f"{_C}/events/{{eventId}}"): EVENT_WRITE,
    ("POST", f"{_C}/events/{{eventId}}/move"): EVENT_WRITE,
    ("POST", f"{_C}/events/quickAdd"): EVENT_WRITE,
    ("POST", f"{_C}/events/watch"): EVENT_READ,
    ("DELETE", f"{_C}/events/{{eventId}}"): EVENT_WRITE,
    # --- acl (sharing): calendar.full ONLY, including reads ---
    ("GET", f"{_C}/acl"): ACL,
    ("GET", f"{_C}/acl/{{ruleId}}"): ACL,
    ("POST", f"{_C}/acl"): ACL,
    ("PATCH", f"{_C}/acl/{{ruleId}}"): ACL,
    ("PUT", f"{_C}/acl/{{ruleId}}"): ACL,
    ("DELETE", f"{_C}/acl/{{ruleId}}"): ACL,
    ("POST", f"{_C}/acl/watch"): ACL,
    # --- colors / freebusy / channels ---
    ("GET", f"{GCAL_PREFIX}/colors"): READ,
    ("POST", f"{GCAL_PREFIX}/freeBusy"): FREEBUSY,
    ("POST", f"{GCAL_PREFIX}/channels/stop"): CHANNEL_STOP,
    # --- settings (read-only in this mock: list/get/watch) ---
    ("GET", f"{_U}/settings"): READ,
    ("GET", f"{_U}/settings/{{setting}}"): READ,
    ("POST", f"{_U}/settings/watch"): READ,
    # --- profile (mock-specific helper endpoint) ---
    ("GET", f"{_U}/profile"): READ,
}
