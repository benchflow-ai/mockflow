#!/usr/bin/env python3
"""Evaluator for the IETF CoRE interim-meeting cancellation task."""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
from pathlib import Path


def _load_scenarios():
    tasks_dir = os.environ.get("TASKS_DIR")
    if tasks_dir:
        data_dir = Path(tasks_dir) / "multi-mail-cal-ietf-core-interim-cancel" / "data"
    else:
        data_dir = Path(__file__).resolve().parent.parent / "data"
    spec = importlib.util.spec_from_file_location("scenarios", data_dir / "scenarios.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.SCENARIOS


SCENARIO = _load_scenarios()[0]
TARGET_SUMMARY = SCENARIO["eval"]["target_summary"].lower()
MATCH_KEYWORDS = [kw.lower() for kw in SCENARIO["eval"]["match_keywords"]]
DECOY_SUMMARIES = [s.lower() for s in SCENARIO["eval"].get("decoy_summaries", [])]


def _normalize(text: str) -> str:
    return text.lower().strip()


def _event_text(event: dict) -> str:
    summary = _normalize(event.get("summary", ""))
    description = _normalize(event.get("description", ""))
    return f"{summary}\n{description}"


def _matches_target(event: dict) -> bool:
    text = _event_text(event)
    if _normalize(event.get("summary", "")) == TARGET_SUMMARY:
        return True
    return any(keyword in text for keyword in MATCH_KEYWORDS)


def _get_events_by_user(state: dict) -> list[dict]:
    events = []
    users = state.get("users", state)
    for user_data in users.values():
        if isinstance(user_data, dict):
            events.extend(user_data.get("events", []))
    return events


def _get_diff_events(diff: dict) -> tuple[list[dict], list[dict], list[dict]]:
    added, updated, deleted = [], [], []
    users = diff.get("users", diff)
    for user_data in users.values():
        if not isinstance(user_data, dict):
            continue
        events = user_data.get("events", {})
        added.extend(events.get("added", []))
        updated.extend(events.get("updated", []))
        deleted.extend(events.get("deleted", []))
    return added, updated, deleted


def _is_active(event: dict) -> bool:
    return _normalize(event.get("status", "confirmed")) != "cancelled"


def _matches_decoy(event: dict) -> bool:
    """Return True if event matches any decoy summary."""
    text = _event_text(event)
    summary = _normalize(event.get("summary", ""))
    for decoy_summary in DECOY_SUMMARIES:
        if summary == decoy_summary or decoy_summary in text:
            return True
    return False


def evaluate(gcal_state: dict, gcal_diff: dict, gcal_action_log: list) -> dict:
    added, updated, deleted = _get_diff_events(gcal_diff)

    active_matches = [event for event in _get_events_by_user(gcal_state) if _matches_target(event) and _is_active(event)]
    cancelled_matches = [event for event in _get_events_by_user(gcal_state) if _matches_target(event) and not _is_active(event)]
    added_matches = [event for event in added if _matches_target(event)]
    updated_cancelled = [event for event in updated if _matches_target(event) and not _is_active(event)]
    deleted_matches = [event for event in deleted if _matches_target(event)]

    # Check decoy events — they must NOT be touched
    decoy_deleted = [event for event in deleted if _matches_decoy(event)]
    decoy_cancelled = [event for event in updated if _matches_decoy(event) and not _is_active(event)]
    decoy_touched = len(decoy_deleted) + len(decoy_cancelled)

    action_count = len(gcal_action_log) if isinstance(gcal_action_log, list) else 0

    reward = 0.0
    reason = "target event still active"

    if active_matches:
        reward = 0.0
    elif added_matches:
        reward = 0.0
        reason = "created a duplicate matching event"
    elif deleted_matches:
        reward = 1.0
        reason = "deleted the cancelled interim event"
    elif updated_cancelled and cancelled_matches:
        reward = 1.0
        reason = "marked the cancelled interim event as cancelled"
    elif cancelled_matches:
        reward = 0.5
        reason = "event is cancelled in final state but diff does not show a clear cancel action"

    # Penalize touching decoy events: -0.5 per decoy touched
    if decoy_touched:
        penalty = decoy_touched * 0.5
        reward = max(0.0, reward - penalty)
        reason += f"; PENALTY: touched {decoy_touched} decoy event(s)"

    return {
        "reward": round(reward, 4),
        "done": True,
        "action_count": action_count,
        "details": {
            "reason": reason,
            "active_matches": len(active_matches),
            "cancelled_matches": len(cancelled_matches),
            "added_matches": len(added_matches),
            "updated_cancelled": len(updated_cancelled),
            "deleted_matches": len(deleted_matches),
            "decoy_deleted": len(decoy_deleted),
            "decoy_cancelled": len(decoy_cancelled),
        },
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
    parser = argparse.ArgumentParser(description="Evaluate multi-mail-cal-ietf-core-interim-cancel")
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
