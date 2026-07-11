"""Single-source task data for a real IETF Gmail + GCal sync workflow.

All user-visible content in this task comes from official IETF sources:

- Mailing-list reminder:
  https://mailarchive.ietf.org/arch/msg/core/w6PNrW9y6KvgIXJ3bavssCADNjI/
- Mailing-list cancellation notice:
  https://mailarchive.ietf.org/arch/msg/core/b9ED0y5TFrWROI3fLfLD_lNix7Y/
- Datatracker session page:
  https://datatracker.ietf.org/meeting/interim-2026-core-04/session/core

We intentionally avoid fabricated attendees, locations, or filler content.
The only harness adaptation is that the seeded Gmail account owns copies of
the public mailing-list emails.

Dates are parameterized relative to UTC "today" so the task stays in the
near future regardless of when the harness runs.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from textwrap import dedent


# ---------------------------------------------------------------------------
# Date anchoring — meeting falls on the next Wednesday from UTC today
# ---------------------------------------------------------------------------

def _utc_today() -> date:
    return datetime.now(timezone.utc).date()


def _next_weekday(target: int) -> int:
    """Days until the next *target* weekday (0=Mon). Always >= 1."""
    today = _utc_today().weekday()
    delta = (target - today) % 7
    return delta if delta > 0 else 7


# T = meeting day (next Wednesday)
_MEETING_OFFSET = _next_weekday(2)  # 2 = Wednesday
MEETING_DATE = _utc_today() + timedelta(days=_MEETING_OFFSET)
MEETING_DATE_STR = MEETING_DATE.isoformat()  # e.g. "2026-03-04"
MEETING_DATE_PRETTY = MEETING_DATE.strftime("%B %-d")  # e.g. "March 4"

ANNOUNCEMENT_DATE = MEETING_DATE - timedelta(days=6)
CANCELLATION_DATE = MEETING_DATE - timedelta(days=1)

ANNOUNCEMENT_TS = f"{ANNOUNCEMENT_DATE.isoformat()}T12:21:55+00:00"
CANCELLATION_TS = f"{CANCELLATION_DATE.isoformat()}T20:52:50+00:00"

# Decoy 1: a stale cancellation from 30 days ago for a different WG
DECOY_DATE = _utc_today() - timedelta(days=30)
DECOY_DATE_STR = DECOY_DATE.isoformat()
DECOY_DATE_PRETTY = DECOY_DATE.strftime("%B %-d")
DECOY_TS = f"{DECOY_DATE.isoformat()}T14:07:22+00:00"

# Decoy 2: a CONFIRMED CoRE interim meeting 2 weeks later — looks very
# similar to the cancelled one but must NOT be deleted.
CONFIRMED_OFFSET = _MEETING_OFFSET + 14  # 2 weeks after the cancelled meeting
CONFIRMED_DATE = _utc_today() + timedelta(days=CONFIRMED_OFFSET)
CONFIRMED_DATE_STR = CONFIRMED_DATE.isoformat()
CONFIRMED_DATE_PRETTY = CONFIRMED_DATE.strftime("%B %-d")
CONFIRMED_ANNOUNCEMENT_TS = f"{(CONFIRMED_DATE - timedelta(days=5)).isoformat()}T09:15:00+00:00"

# Decoy 3: an HTTPBIS WG cancellation with a matching calendar event —
# agent must not cancel/delete the HTTPBIS event (wrong WG).
HTTPBIS_MEETING_OFFSET = _MEETING_OFFSET + 1  # Thursday after the CoRE Wednesday
HTTPBIS_DATE = _utc_today() + timedelta(days=HTTPBIS_MEETING_OFFSET)
HTTPBIS_DATE_STR = HTTPBIS_DATE.isoformat()
HTTPBIS_DATE_PRETTY = HTTPBIS_DATE.strftime("%B %-d")
HTTPBIS_CANCEL_TS = f"{(HTTPBIS_DATE - timedelta(days=2)).isoformat()}T11:30:00+00:00"


# ---------------------------------------------------------------------------
# Sources
# ---------------------------------------------------------------------------

SOURCES = {
    "announcement_email": (
        "https://mailarchive.ietf.org/arch/msg/core/"
        "w6PNrW9y6KvgIXJ3bavssCADNjI/"
    ),
    "cancellation_email": (
        "https://mailarchive.ietf.org/arch/msg/core/"
        "b9ED0y5TFrWROI3fLfLD_lNix7Y/"
    ),
    "session_page": "https://datatracker.ietf.org/meeting/interim-2026-core-04/session/core",
    "wg_meetings_page": "https://datatracker.ietf.org/wg/core/meetings/",
}


# ---------------------------------------------------------------------------
# Email content (parameterized)
# ---------------------------------------------------------------------------

ANNOUNCEMENT_SUBJECT = f"[core] CoRE WG Virtual Interim {MEETING_DATE_STR}"
ANNOUNCEMENT_BODY = dedent(
    f"""\
    Dear all,
    Just a reminder that we have a virtual interim meeting scheduled on Wednesday, {MEETING_DATE_PRETTY} at 15:00-16:30 UTC.
    The information for the meeting is as follows.
    - Material: [1]
    - Meetecho: [2]
    - Notes: [3]
    Please go to the notes [3] and add topics you would like to discuss to the agenda.
    *** If there are no agenda items by 18:00 UTC on Tuesday, the meeting will be cancelled. ***
    Best,
    /Marco

    [1]
    https://datatracker.ietf.org/meeting/interim-2026-core-04/session/core
    [2]
    https://meetings.conf.meetecho.com/interim/?group=7e3fae63-ae83-4607-8d84-35f31a3eb39d
    [3]
    https://notes.ietf.org/notes-ietf-interim-2026-core-04-core
    """
).strip()

CANCELLATION_SUBJECT = (
    "[core] Constrained RESTful Environments (core) WG Interim Meeting "
    f"Cancelled (was {MEETING_DATE_STR})"
)
CANCELLATION_BODY = dedent(
    f"""\
    The Constrained RESTful Environments (core) virtual
    interim meeting for {MEETING_DATE_STR} from 16:00 to 17:30 Europe/Stockholm
    has been cancelled.
    """
).strip()


# ---------------------------------------------------------------------------
# Decoy email 1 — stale cancellation for a different WG (6TiSCH)
# ---------------------------------------------------------------------------

DECOY_SUBJECT = (
    "[6tisch] IPv6 over the TSCH mode of IEEE 802.15.4e (6tisch) WG Interim "
    f"Meeting Cancelled (was {DECOY_DATE_STR})"
)
DECOY_BODY = dedent(
    f"""\
    The IPv6 over the TSCH mode of IEEE 802.15.4e (6tisch) virtual
    interim meeting for {DECOY_DATE_STR} from 14:00 to 15:00 America/New_York
    has been cancelled.
    """
).strip()

# ---------------------------------------------------------------------------
# Decoy email 2 — confirmed CoRE meeting announcement (do NOT cancel)
# ---------------------------------------------------------------------------

CONFIRMED_SUBJECT = f"[core] Confirmed CoRE WG Interim — {CONFIRMED_DATE_STR}"
CONFIRMED_BODY = dedent(
    f"""\
    Dear all,
    Just a reminder that we have a virtual interim meeting scheduled on Wednesday, {CONFIRMED_DATE_PRETTY} at 15:00-16:30 UTC.
    The information for the meeting is as follows.
    - Material: [1]
    - Meetecho: [2]
    - Notes: [3]
    Please go to the notes [3] and add topics you would like to discuss to the agenda.
    Best,
    /Marco

    [1]
    https://datatracker.ietf.org/meeting/interim-2026-core-05/session/core
    [2]
    https://meetings.conf.meetecho.com/interim/?group=7e3fae63-ae83-4607-8d84-35f31a3eb39d
    [3]
    https://notes.ietf.org/notes-ietf-interim-2026-core-05-core
    """
).strip()

# ---------------------------------------------------------------------------
# Decoy email 3 — HTTPBIS WG cancellation (wrong WG — do NOT cancel CoRE)
# ---------------------------------------------------------------------------

HTTPBIS_CANCEL_SUBJECT = (
    "[httpbis] HTTP (httpbis) WG Interim Meeting "
    f"Cancelled (was {HTTPBIS_DATE_STR})"
)
HTTPBIS_CANCEL_BODY = dedent(
    f"""\
    The HTTP (httpbis) virtual
    interim meeting for {HTTPBIS_DATE_STR} from 14:00 to 15:30 America/New_York
    has been cancelled.
    """
).strip()


# ---------------------------------------------------------------------------
# Scenarios
# ---------------------------------------------------------------------------

SCENARIOS = [
    {
        "id": "ietf_core_interim_cancel",
        "action": "delete",
        # Use the exact reminder subject as the calendar title to avoid
        # inventing a paraphrase for the seeded event.
        "event": {
            "summary": ANNOUNCEMENT_SUBJECT,
            "start_date": MEETING_DATE_STR,
            "start_hour": 15,
            "duration_hours": 1.5,
            "calendar": "primary",
            "location": "",
            "description": ANNOUNCEMENT_BODY,
        },
        # Decoy events: a confirmed CoRE meeting and an HTTPBIS meeting.
        # These must NOT be touched by the agent.
        "decoy_events": [
            {
                "summary": CONFIRMED_SUBJECT,
                "start_date": CONFIRMED_DATE_STR,
                "start_hour": 15,
                "duration_hours": 1.5,
                "calendar": "primary",
                "location": "",
                "description": CONFIRMED_BODY,
            },
            {
                "summary": HTTPBIS_CANCEL_SUBJECT,
                "start_date": HTTPBIS_DATE_STR,
                "start_hour": 14,
                "duration_hours": 1.5,
                "calendar": "primary",
                "location": "",
                "description": HTTPBIS_CANCEL_BODY,
            },
        ],
        "emails": [
            {
                "subject": ANNOUNCEMENT_SUBJECT,
                "sender_name": "Marco Tiloca",
                "sender_email": "marco.tiloca@ri.se",
                "received_at": ANNOUNCEMENT_TS,
                "body_plain": ANNOUNCEMENT_BODY,
                "labels": ["INBOX"],
                "source_url": SOURCES["announcement_email"],
            },
            {
                "subject": CANCELLATION_SUBJECT,
                "sender_name": "IESG Secretary",
                "sender_email": "iesg-secretary@ietf.org",
                "received_at": CANCELLATION_TS,
                "body_plain": CANCELLATION_BODY,
                "labels": ["INBOX"],
                "source_url": SOURCES["cancellation_email"],
            },
            {
                "subject": DECOY_SUBJECT,
                "sender_name": "IESG Secretary",
                "sender_email": "iesg-secretary@ietf.org",
                "received_at": DECOY_TS,
                "body_plain": DECOY_BODY,
                "labels": ["INBOX"],
            },
            {
                "subject": CONFIRMED_SUBJECT,
                "sender_name": "Marco Tiloca",
                "sender_email": "marco.tiloca@ri.se",
                "received_at": CONFIRMED_ANNOUNCEMENT_TS,
                "body_plain": CONFIRMED_BODY,
                "labels": ["INBOX"],
            },
            {
                "subject": HTTPBIS_CANCEL_SUBJECT,
                "sender_name": "IESG Secretary",
                "sender_email": "iesg-secretary@ietf.org",
                "received_at": HTTPBIS_CANCEL_TS,
                "body_plain": HTTPBIS_CANCEL_BODY,
                "labels": ["INBOX"],
            },
        ],
        "eval": {
            "target_summary": ANNOUNCEMENT_SUBJECT,
            "match_keywords": [
                # Stable date-independent keyword — survives container-build vs
                # eval-time date drift (the seeded summary always contains this
                # substring regardless of which Wednesday was current at build).
                # NOTE: avoid URL fragments like "interim-2026-core-04" which
                # appear in description fields of unrelated seed-pack events.
                "core wg virtual interim",
                f"core wg virtual interim {MEETING_DATE_STR}",
            ],
            # Decoy event summaries — must remain untouched in final state
            "decoy_summaries": [
                CONFIRMED_SUBJECT,
                HTTPBIS_CANCEL_SUBJECT,
            ],
        },
    }
]
