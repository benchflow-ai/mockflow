"""Evaluator for rebalance-on-call-rotation.

Scoring breakdown (total 1.0):
  - Week 1 correctly assigned (Elena Petrov — swap honored)        +0.25
  - Week 2 unchanged (Bob Martinez)                                +0.05
  - Week 3 correctly reassigned (Alice Chen — fewest, alphabetical)+0.25
  - Week 4 unchanged (Derek Okafor)                                +0.10
  - No PTO engineer assigned to their PTO week                     +0.10
  - Ambiguous swap not honored (Derek NOT on week 3)               +0.05
  - Doc modified (any change from initial)                         +0.05
  - All 4 weeks filled in the doc                                  +0.05
  - Schedule summary posted to #on-call-swap                       +0.10
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os


def _load_scenarios():
    tasks_dir = os.environ.get("TASKS_DIR")
    if tasks_dir:
        data_dir = os.path.join(tasks_dir, "multi-rebalance-on-call-rotation", "data")
    else:
        data_dir = os.path.join(os.path.dirname(__file__), "..", "data")
    path = os.path.join(data_dir, "scenarios.py")
    spec = importlib.util.spec_from_file_location("scenarios", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_sc = _load_scenarios()
ENGINEERS = _sc.ENGINEERS
WEEKS = _sc.WEEKS
EXPECTED_SCHEDULE = _sc.EXPECTED_SCHEDULE
DOC_SCHEDULE_ID = _sc.DOC_SCHEDULE_ID
PTO_EVENTS = _sc.PTO_EVENTS
INITIAL_SCHEDULE = _sc.INITIAL_SCHEDULE


def _parse_schedule_from_doc(doc_text: str) -> dict[str, str]:
    """Extract week -> assignee mapping from document text.

    Handles table format (| Week | Engineer |) and list format (- Week: Engineer).
    """
    schedule: dict[str, str] = {}
    engineer_names = [e["name"] for e in ENGINEERS]
    for line in doc_text.split("\n"):
        for week_label in WEEKS:
            if week_label in line:
                for name in engineer_names:
                    if name in line:
                        schedule[week_label] = name
    return schedule


def _extract_body_text(body: dict) -> str:
    """Extract plain text from a Google Docs body dict."""
    parts = []
    for element in body.get("content", []):
        paragraph = element.get("paragraph")
        if not paragraph:
            continue
        for pe in paragraph.get("elements", []):
            text_run = pe.get("textRun")
            if text_run:
                parts.append(text_run.get("content", ""))
    return "".join(parts)


def _extract_doc_text(docs_state: dict) -> str:
    """Extract plain text from the gdoc state for the schedule document.

    State format: {"users": {uid: {"documents": [doc, ...]}}}
    """
    # Try the actual gdoc state format: users -> documents list
    for uid, user_data in docs_state.get("users", {}).items():
        for doc in user_data.get("documents", []):
            body = doc.get("body", {})
            text = _extract_body_text(body)
            if "On-Call" in text or any(w in text for w in WEEKS):
                return text

    # Fallback: flat documents dict (for unit tests)
    for doc_id, doc in docs_state.get("documents", {}).items():
        body = doc.get("body", {})
        text = _extract_body_text(body)
        if "On-Call" in text or any(w in text for w in WEEKS):
            return text

    return ""


def _check_slack_post(slack_state: dict) -> bool:
    """Check if a schedule summary was posted to #on-call-swap.

    Validates that the agent posted a message containing at least 3 of the 4
    week labels AND at least 3 engineer names from the roster.  This confirms
    a schedule summary was shared without double-penalizing week correctness
    (which is already scored by the per-week checks).

    State format: {"workspaces": {ws_id: {"channels": [...], "messages": [...]}}}
    Also supports flat test format: {"channels": {id: {"name": ..., "messages": [...]}}}
    """
    engineer_names = [e["name"] for e in ENGINEERS]

    def _is_schedule_summary(text: str) -> bool:
        week_hits = sum(1 for w in WEEKS if w in text)
        name_hits = sum(1 for n in engineer_names if n in text)
        return week_hits >= 3 and name_hits >= 3

    # Try slack state format: workspaces -> channels + messages
    for ws_id, ws_data in slack_state.get("workspaces", {}).items():
        ch_name_to_id = {}
        for ch in ws_data.get("channels", []):
            ch_name_to_id[ch.get("name", "")] = ch.get("id", "")

        swap_ch_id = ch_name_to_id.get("on-call-swap")
        if not swap_ch_id:
            continue

        for msg in ws_data.get("messages", []):
            if msg.get("channel_id") != swap_ch_id:
                continue
            if _is_schedule_summary(msg.get("text", "")):
                return True

    # Fallback: flat test format
    for ch_id, ch_data in slack_state.get("channels", {}).items():
        if ch_data.get("name") != "on-call-swap":
            continue
        for msg in ch_data.get("messages", []):
            if _is_schedule_summary(msg.get("text", "")):
                return True

    return False


def evaluate(
    docs_state: dict,
    docs_diff: dict,
    slack_state: dict,
    slack_diff: dict,
    action_log: list,
) -> dict:
    reward = 0.0

    # Gate: if no action taken, return 0.0
    has_action = bool(action_log)
    if not has_action:
        doc_changes = docs_diff.get("changes", docs_diff.get("documents", {}))
        has_action = bool(doc_changes)
    if not has_action:
        slack_changes = slack_diff.get("changes", slack_diff.get("channels", {}))
        has_action = bool(slack_changes)

    if not has_action:
        return {"reward": 0.0, "done": 1}

    # Parse the updated schedule from the doc
    doc_text = _extract_doc_text(docs_state)
    parsed = _parse_schedule_from_doc(doc_text)

    # Score each week assignment
    week_correct = {}
    for entry in EXPECTED_SCHEDULE:
        week = entry["week"]
        expected = entry["assignee"]
        actual = parsed.get(week)
        week_correct[week] = int(actual == expected)

    # Week 1 (swap honored): +0.25
    w1 = week_correct[WEEKS[0]]
    if w1:
        reward += 0.25

    # Week 2 (unchanged): +0.05
    w2 = week_correct[WEEKS[1]]
    if w2:
        reward += 0.05

    # Week 3 (reassigned correctly): +0.25
    w3 = week_correct[WEEKS[2]]
    if w3:
        reward += 0.25

    # Week 4 (unchanged): +0.10
    w4 = week_correct[WEEKS[3]]
    if w4:
        reward += 0.10

    # Build PTO week lookup: map engineer name -> set of week labels with PTO
    _pto_week_map: dict[str, set[str]] = {}
    for pto in PTO_EVENTS:
        # Match PTO email to engineer name
        pto_name = None
        for e in ENGINEERS:
            if e["email"] == pto["email"]:
                pto_name = e["name"]
                break
        if not pto_name:
            continue
        # Match PTO date range to week labels
        for i, initial in enumerate(INITIAL_SCHEDULE):
            if initial["assignee"] == pto_name:
                _pto_week_map.setdefault(pto_name, set()).add(WEEKS[i])

    # No PTO engineer assigned to their PTO week: +0.10
    pto_conflict = False
    for week, assignee in parsed.items():
        if assignee and week in _pto_week_map.get(assignee, set()):
            pto_conflict = True
            break
    no_pto_assigned = int(not pto_conflict and bool(parsed))
    if no_pto_assigned:
        reward += 0.10

    # Ambiguous swap not honored (Derek NOT assigned to week 3): +0.05
    # Derek offered to take Carol's week but Carol never confirmed.
    week3_assignee = parsed.get(WEEKS[2], "")
    ambig_rejected = int(week3_assignee != "Derek Okafor" and bool(parsed))
    if ambig_rejected:
        reward += 0.05

    # Track max_weeks for metrics
    counts: dict[str, int] = {}
    for week, assignee in parsed.items():
        if assignee:
            counts[assignee] = counts.get(assignee, 0) + 1
    max_weeks = max(counts.values()) if counts else 0

    # Doc modified (any change from initial): +0.05
    doc_modified = int(bool(doc_text) and any(
        parsed.get(w) != _sc.INITIAL_SCHEDULE[i]["assignee"]
        for i, w in enumerate(WEEKS)
        if parsed.get(w)
    ))
    if doc_modified:
        reward += 0.05

    # All 4 weeks filled in the doc: +0.05
    schedule_complete = int(all(parsed.get(w) for w in WEEKS))
    if schedule_complete:
        reward += 0.05

    # Schedule posted to Slack: +0.10
    posted = int(_check_slack_post(slack_state))
    if posted:
        reward += 0.10

    return {
        "reward": max(-1.0, min(1.0, round(reward, 2))),
        "done": 1,
        "week1_swap_honored": w1,
        "week2_unchanged": w2,
        "week3_reassigned": w3,
        "week4_unchanged": w4,
        "max_weeks_per_engineer": max_weeks,
        "no_pto_assigned": no_pto_assigned,
        "ambig_swap_rejected": ambig_rejected,
        "doc_updated": doc_modified,
        "schedule_complete": schedule_complete,
        "slack_posted": posted,
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
    parser = argparse.ArgumentParser()
    parser.add_argument("--docs-state", required=True)
    parser.add_argument("--docs-diff", required=True)
    parser.add_argument("--slack-state", required=True)
    parser.add_argument("--slack-diff", required=True)
    parser.add_argument("--action-log", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    docs_state = json.loads(open(args.docs_state).read())
    docs_diff = json.loads(open(args.docs_diff).read())
    slack_state = json.loads(open(args.slack_state).read())
    slack_diff = json.loads(open(args.slack_diff).read())
    action_log_data = json.loads(open(args.action_log).read())
    log_entries = action_log_data.get("entries", action_log_data)

    result = evaluate(docs_state, docs_diff, slack_state, slack_diff, log_entries)
    _write_reward(result, args.output)


if __name__ == "__main__":
    main()
