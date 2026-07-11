"""Multi-env seed data for rebalance-on-call-rotation.

gdrive reads:  NEEDLES, NORMAL_FILES, FILL_CONFIG
gdoc mirrors:  from gdrive (--from-gdrive)
gcal reads:    NEEDLE_EVENTS, GCAL_FILL_CONFIG
slack reads:   SEED_USERS, SEED_CHANNELS, SEED_MESSAGES, FILL_CONFIG (as SLACK_FILL_CONFIG)
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

from mock_gdrive.seed.content import DOC


def _load_sibling(name: str):
    here = Path(__file__).parent
    spec = importlib.util.spec_from_file_location(name, here / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_sc = _load_sibling("scenarios")

ENGINEERS = _sc.ENGINEERS
INITIAL_SCHEDULE = _sc.INITIAL_SCHEDULE
EXPECTED_SCHEDULE = _sc.EXPECTED_SCHEDULE
PTO_EVENTS = _sc.PTO_EVENTS
DECOY_EVENTS = _sc.DECOY_EVENTS
SLACK_SWAP_MESSAGES = _sc.SLACK_SWAP_MESSAGES
AMBIGUOUS_SWAP_MESSAGES = _sc.AMBIGUOUS_SWAP_MESSAGES
NOISE_SWAP_MESSAGES = _sc.NOISE_SWAP_MESSAGES
DOC_SCHEDULE_ID = _sc.DOC_SCHEDULE_ID

# ── GDrive / GDoc ────────────────────────────────────────────────────────────
# The on-call schedule document is the needle. Agent must find and update it.

NEEDLES = [
    {
        "id": DOC_SCHEDULE_ID,
        "name": "On-Call Schedule \u2014 April",
        "mimeType": DOC,
        "content_text": _sc.build_schedule_doc(INITIAL_SCHEDULE),
        "days_ago": 7,
    },
]

NORMAL_FILES = [
    {
        "name": "Engineering Team Roster",
        "mimeType": DOC,
        "content_text": (
            "Engineering Team Roster\n\n"
            "Active engineers:\n"
            + "\n".join(f"- {e['name']} ({e['email']})" for e in ENGINEERS)
            + "\n\nLast updated: March 2026."
        ),
        "days_ago": 30,
    },
    {
        "name": "Q1 2026 Incident Postmortems",
        "mimeType": DOC,
        "content_text": "Q1 2026 Incident Postmortems\n\nNo major incidents in Q1.",
        "days_ago": 14,
    },
]

# FILL_CONFIG is read by both gdrive (target_count) and slack (base_scenario).
# Each seeder only reads the fields it cares about.
FILL_CONFIG = {"target_count": 20, "base_scenario": "default"}

# ── GCal ─────────────────────────────────────────────────────────────────────
# PTO events (needles) + decoy conference event

NEEDLE_EVENTS = [
    {
        "summary": pto["summary"],
        "start": {"date": pto["start"]},
        "end": {"date": pto["end"]},
        "attendees": [{"email": pto["email"]}],
    }
    for pto in PTO_EVENTS
] + [
    {
        "summary": decoy["summary"],
        "start": {"date": decoy["start"]},
        "end": {"date": decoy["end"]},
        "attendees": [{"email": decoy["email"]}],
    }
    for decoy in DECOY_EVENTS
]

GCAL_FILL_CONFIG = {"target_count": 15}

# ── Slack ────────────────────────────────────────────────────────────────────
# Seed engineers as Slack users and #on-call-swap channel with swap messages.

SEED_USERS: list[dict] = [
    {
        "key": e["slack_key"],
        "name": e["slack_username"],
        "real_name": e["name"],
        "email": e["email"],
        "title": "Software Engineer \u00b7 NexusAI",
    }
    for e in ENGINEERS
]

SEED_CHANNELS: list[dict] = [
    {
        "name": "on-call-swap",
        "is_private": False,
        "topic": "Coordinate on-call swaps here",
        "purpose": "On-call rotation swap coordination",
        "members": [e["slack_key"] for e in ENGINEERS],
    },
]

_ALL_SWAP_MSGS = (
    NOISE_SWAP_MESSAGES
    + SLACK_SWAP_MESSAGES
    + AMBIGUOUS_SWAP_MESSAGES
)
# Sort by days_ago descending (oldest first) for natural chronological order.
_ALL_SWAP_MSGS.sort(key=lambda m: -m["days_ago"])

SEED_MESSAGES: dict = {
    "on-call-swap": [
        {
            "sender": msg["sender_key"],
            "text": msg["text"],
            "days_ago": msg["days_ago"],
        }
        for msg in _ALL_SWAP_MSGS
    ],
}


# Note: Slack seeder reads FILL_CONFIG (defined above alongside gdrive fields).
