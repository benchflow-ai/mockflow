#!/usr/bin/env python3
"""Evaluator for gcal-federal-register-meeting-amendments."""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
from datetime import datetime, timezone
from pathlib import Path


TASK_NAME = "gcal-federal-register-meeting-amendments"


def _load_scenarios():
    tasks_dir = os.environ.get("TASKS_DIR")
    if tasks_dir:
        data_dir = Path(tasks_dir) / TASK_NAME / "data"
    else:
        data_dir = Path(__file__).resolve().parent.parent / "data"
    spec = importlib.util.spec_from_file_location("scenarios", data_dir / "scenarios.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.SCENARIOS


SCENARIOS = _load_scenarios()
ACTION_SCENARIOS = [scenario for scenario in SCENARIOS if scenario["action"] != "trap"]
SCOREABLE = len(ACTION_SCENARIOS)


def _normalize(text: str) -> str:
    return " ".join(text.lower().split())


def _parse_iso(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


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


def _event_end_iso(event: dict) -> str:
    end = event.get("end", {})
    value = ""
    if isinstance(end, dict):
        value = end.get("dateTime", end.get("date", ""))
    elif isinstance(end, str):
        value = end
    if not value:
        return ""
    return _parse_iso(value).strftime("%Y-%m-%dT%H:%M:%SZ")


def _status(event: dict) -> str:
    return _normalize(event.get("status", "confirmed"))


def _matches_spec(event: dict, spec: dict) -> bool:
    if _normalize(event.get("summary", "")) != _normalize(spec["summary"]):
        return False
    if _event_start_iso(event) != spec["start_iso"]:
        return False
    return True


def _matches_exact(event: dict, spec: dict) -> bool:
    if not _matches_spec(event, spec):
        return False
    if _event_end_iso(event) != spec["end_iso"]:
        return False
    if _normalize(event.get("location", "")) != _normalize(spec.get("location", "")):
        return False
    return True


def _all_events(state: dict) -> list[dict]:
    events: list[dict] = []
    users = state.get("users", state)
    for user_data in users.values():
        if isinstance(user_data, dict):
            events.extend(user_data.get("events", []))
    return events


def _diff_events(diff: dict) -> tuple[list[dict], list[dict], list[dict]]:
    added: list[dict] = []
    updated: list[dict] = []
    deleted: list[dict] = []
    users = diff.get("users", diff)
    for user_data in users.values():
        if not isinstance(user_data, dict):
            continue
        events = user_data.get("events", {})
        added.extend(events.get("added", []))
        updated.extend(events.get("updated", []))
        deleted.extend(events.get("deleted", []))
    return added, updated, deleted


def evaluate(gcal_state: dict, gcal_diff: dict, gcal_action_log: list) -> dict:
    final_events = _all_events(gcal_state)
    added, updated, deleted = _diff_events(gcal_diff)

    action_score = 0.0
    trap_penalty = 0.0
    details: dict[str, dict] = {}

    for scenario in SCENARIOS:
        scenario_id = scenario["id"]
        action = scenario["action"]

        if action == "delete":
            spec = scenario["seed_event"]
            final_matches = [e for e in final_events if _matches_spec(e, spec)]
            active_matches = [e for e in final_matches if _status(e) != "cancelled"]
            deleted_matches = [e for e in deleted if _matches_spec(e, spec)]
            updated_cancelled = [
                e for e in updated if _matches_spec(e, spec) and _status(e) == "cancelled"
            ]
            if not active_matches and (deleted_matches or updated_cancelled or final_matches):
                action_score += 1.0
                details[scenario_id] = {"score": 1.0, "reason": "removed or cancelled"}
            else:
                details[scenario_id] = {"score": 0.0, "reason": "still active"}
            continue

        if action == "create":
            spec = scenario["target_event"]
            final_matches = [e for e in final_events if _matches_exact(e, spec) and _status(e) != "cancelled"]
            added_matches = [e for e in added if _matches_exact(e, spec)]
            if len(final_matches) == 1 and added_matches:
                action_score += 1.0
                details[scenario_id] = {"score": 1.0, "reason": "created"}
            else:
                details[scenario_id] = {
                    "score": 0.0,
                    "reason": f"expected created event, found final={len(final_matches)} added={len(added_matches)}",
                }
            continue

        if action == "update":
            seed_spec = scenario["seed_event"]
            target_spec = scenario["target_event"]
            seed_active = [
                e for e in final_events if _matches_spec(e, seed_spec) and _status(e) != "cancelled"
            ]
            target_active = [
                e for e in final_events if _matches_exact(e, target_spec) and _status(e) != "cancelled"
            ]
            if not seed_active and len(target_active) == 1:
                action_score += 1.0
                details[scenario_id] = {"score": 1.0, "reason": "updated"}
            else:
                details[scenario_id] = {
                    "score": 0.0,
                    "reason": f"seed_active={len(seed_active)} target_active={len(target_active)}",
                }
            continue

        if action == "trap":
            spec = scenario["seed_event"]
            final_matches = [e for e in final_events if _matches_exact(e, spec) and _status(e) != "cancelled"]
            touched = [e for e in updated if _matches_spec(e, spec)] + [e for e in deleted if _matches_spec(e, spec)]
            if len(final_matches) == 1 and not touched:
                details[scenario_id] = {"score": 1.0, "reason": "left unchanged"}
            else:
                trap_penalty += 1.0
                details[scenario_id] = {
                    "score": 0.0,
                    "reason": f"final={len(final_matches)} touched={len(touched)}",
                }
            continue

        details[scenario_id] = {"score": 0.0, "reason": f"unsupported action {action}"}

    reward = round(max(0.0, min(1.0, (action_score - trap_penalty) / SCOREABLE)), 4) if SCOREABLE else 0.0
    action_count = len(gcal_action_log) if isinstance(gcal_action_log, list) else 0
    return {
        "reward": reward,
        "done": True,
        "action_count": action_count,
        "details": details,
    }


def _write_reward(result, output_path):
    """Write benchflow-canonical reward outputs (strict-valid reward.json).

    reward.json carries only the scalar ``reward`` plus a ``metrics`` map of
    numeric values already in [0, 1] (booleans -> 0/1); every other diagnostic
    (counts, string verdicts like ``safety_gate``, ``safety_violations``,
    ``done``, etc.) is preserved losslessly under the ``details`` structured
    key, which benchflow accepts unvalidated. The scalar reward is unchanged,
    so scoring is identical to the prior rich/flat reward.json.
    """
    import json as _json
    import math as _math
    import os as _os

    output_path = str(output_path)
    out_dir = _os.path.dirname(output_path) or "."
    _os.makedirs(out_dir, exist_ok=True)

    reward = result["reward"]
    raw_metrics = result.get("metrics", {}) or {}

    numeric_metrics = {}
    for key, value in raw_metrics.items():
        if isinstance(value, bool):
            numeric_metrics[str(key)] = 1 if value else 0
        elif (
            isinstance(value, (int, float))
            and _math.isfinite(float(value))
            and 0.0 <= float(value) <= 1.0
        ):
            numeric_metrics[str(key)] = value

    details = dict(raw_metrics)
    if "done" in result:
        details["done"] = result["done"]

    payload = {"reward": reward}
    if numeric_metrics:
        payload["metrics"] = numeric_metrics
    if details:
        payload["details"] = details

    # Canonical reward.json (the file benchflow's verifier validates).
    with open(output_path, "w") as fh:
        _json.dump(payload, fh, indent=2)

    # Scalar reward.txt alongside it (must match reward.json["reward"]).
    with open(_os.path.join(out_dir, "reward.txt"), "w") as fh:
        fh.write(str(reward))


def main():
    parser = argparse.ArgumentParser(description="Evaluate gcal-federal-register-meeting-amendments")
    parser.add_argument("--gcal-state", required=True)
    parser.add_argument("--gcal-diff", required=True)
    parser.add_argument("--gcal-action-log", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    gcal_state = json.loads(Path(args.gcal_state).read_text())
    gcal_diff = json.loads(Path(args.gcal_diff).read_text())
    gcal_action_log_raw = json.loads(Path(args.gcal_action_log).read_text())

    if isinstance(gcal_action_log_raw, dict):
        gcal_action_log = gcal_action_log_raw.get("entries", gcal_action_log_raw.get("actions", []))
    else:
        gcal_action_log = gcal_action_log_raw

    result = evaluate(gcal_state, gcal_diff, gcal_action_log)
    _write_reward(result, args.output)


if __name__ == "__main__":
    main()
