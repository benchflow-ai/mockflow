"""Multi-env seed data built from the source-backed IETF scenario."""

from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_sibling(name: str):
    here = Path(__file__).parent
    spec = importlib.util.spec_from_file_location(name, here / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_scenarios_mod = _load_sibling("scenarios")
SCENARIO = _scenarios_mod.SCENARIOS[0]


def _to_gmail_needles() -> list[dict]:
    needles: list[dict] = []
    for email in SCENARIO["emails"]:
        needles.append(
            {
                "subject": email["subject"],
                "sender_name": email["sender_name"],
                "sender_email": email["sender_email"],
                "received_at": email["received_at"],
                "body_plain": email["body_plain"],
                "labels": list(email.get("labels", ["INBOX"])),
            }
        )
    return needles


def _to_gcal_needle_events() -> list[dict]:
    ev = SCENARIO["event"]
    events = [
        {
            "summary": ev["summary"],
            "start_date": ev["start_date"],
            "start_hour": ev["start_hour"],
            "duration_hours": ev["duration_hours"],
            "calendar": ev["calendar"],
            "location": ev.get("location", ""),
            "description": ev["description"],
        }
    ]
    # Add decoy calendar events that must NOT be touched
    for decoy in SCENARIO.get("decoy_events", []):
        events.append(
            {
                "summary": decoy["summary"],
                "start_date": decoy["start_date"],
                "start_hour": decoy["start_hour"],
                "duration_hours": decoy["duration_hours"],
                "calendar": decoy["calendar"],
                "location": decoy.get("location", ""),
                "description": decoy.get("description", ""),
            }
        )
    return events


NEEDLES = _to_gmail_needles()
NEEDLE_THREADS = []
NEEDLE_EVENTS = _to_gcal_needle_events()

GMAIL_FILL_CONFIG = {
    "target_count": len(NEEDLES),
    "include_ambiguous": False,
    "include_draft": False,
}

GCAL_FILL_CONFIG = {
    "seed_packs": [],
    "target_count": "fixed_only",
    "include_needles": True,
}
