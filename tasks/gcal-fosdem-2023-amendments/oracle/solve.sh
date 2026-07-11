#!/usr/bin/env bash
set -euo pipefail

python3 <<'PY'
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path


TASK_NAME = "gcal-fosdem-2023-amendments"


def _load_scenarios():
    tasks_dir = Path(os.environ.get("TASKS_DIR", Path.cwd() / "tasks"))
    path = tasks_dir / TASK_NAME / "data" / "scenarios.py"
    spec = importlib.util.spec_from_file_location("scenarios", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.SCENARIOS


def _parse_iso(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def _normalize(text: str) -> str:
    return " ".join(text.lower().split())


def _extract_json(raw: str):
    raw = raw.strip()
    if raw.startswith("{") or raw.startswith("["):
        return json.loads(raw)
    for marker in ("{", "["):
        idx = raw.find(marker)
        if idx >= 0:
            return json.loads(raw[idx:])
    raise RuntimeError(f"Could not find JSON payload in output: {raw[:200]}")


def _gws(resource: str, method: str, *, params: dict | None = None, body: dict | None = None):
    cmd = ["gws", "calendar", resource, method]
    if params is not None:
        cmd.extend(["--params", json.dumps(params, separators=(",", ":"))])
    if body is not None:
        cmd.extend(["--json", json.dumps(body, separators=(",", ":"))])
    result = subprocess.run(cmd, check=True, capture_output=True, text=True)
    stdout = result.stdout.strip()
    if stdout:
        return _extract_json(stdout)
    return {}


def _event_start_iso(event: dict) -> str:
    start = event.get("start", {})
    value = ""
    if isinstance(start, dict):
        value = start.get("dateTime", start.get("date", ""))
    elif isinstance(start, str):
        value = start
    if not value:
        return ""
    return _parse_iso(value).strftime("%Y-%m-%dT%H:%M:%SZ")


def _list_events(time_min: str, time_max: str) -> list[dict]:
    data = _gws(
        "events",
        "list",
        params={
            "calendarId": "primary",
            "timeMin": time_min,
            "timeMax": time_max,
            "singleEvents": True,
            "showDeleted": False,
            "maxResults": 250,
        },
    )
    return list(data.get("items", []))


def _match_event(events: list[dict], spec: dict) -> dict | None:
    target_summary = _normalize(spec["summary"])
    target_start = spec["start_iso"]
    for event in events:
        if _normalize(event.get("summary", "")) != target_summary:
            continue
        if _event_start_iso(event) != target_start:
            continue
        return event
    return None


def _event_body(spec: dict) -> dict:
    body = {
        "summary": spec["summary"],
        "description": spec.get("description", ""),
        "start": {"dateTime": spec["start_iso"].replace("Z", "+00:00"), "timeZone": "UTC"},
        "end": {"dateTime": spec["end_iso"].replace("Z", "+00:00"), "timeZone": "UTC"},
    }
    if spec.get("location"):
        body["location"] = spec["location"]
    return body


scenarios = _load_scenarios()
all_specs = []
for scenario in scenarios:
    if scenario.get("seed_event") is not None:
        all_specs.append(scenario["seed_event"])
    if scenario.get("target_event") is not None:
        all_specs.append(scenario["target_event"])

window_start = min(_parse_iso(spec["start_iso"]) for spec in all_specs) - timedelta(days=1)
window_end = max(_parse_iso(spec["end_iso"]) for spec in all_specs) + timedelta(days=1)
time_min = window_start.strftime("%Y-%m-%dT%H:%M:%SZ")
time_max = window_end.strftime("%Y-%m-%dT%H:%M:%SZ")

for scenario in scenarios:
    action = scenario["action"]
    events = _list_events(time_min, time_max)

    if action == "delete":
        current = _match_event(events, scenario["seed_event"])
        if current is None:
            continue
        _gws(
            "events",
            "delete",
            params={"calendarId": "primary", "eventId": current["id"]},
        )
        print(f"Deleted {scenario['seed_event']['summary']}")
        continue

    if action == "create":
        current = _match_event(events, scenario["target_event"])
        if current is None:
            _gws(
                "events",
                "insert",
                params={"calendarId": "primary"},
                body=_event_body(scenario["target_event"]),
            )
            print(f"Created {scenario['target_event']['summary']}")
        continue

    if action == "update":
        seed_event = scenario["seed_event"]
        target_event = scenario["target_event"]
        current = _match_event(events, seed_event) or _match_event(events, target_event)
        if current is None:
            raise RuntimeError(f"Could not find event to update: {seed_event['summary']}")
        _gws(
            "events",
            "patch",
            params={"calendarId": "primary", "eventId": current["id"]},
            body=_event_body(target_event),
        )
        print(f"Updated {target_event['summary']}")
        continue

    if action == "trap":
        print(f"Left unchanged {scenario['seed_event']['summary']}")
        continue

    raise RuntimeError(f"Unsupported action: {action}")
PY
