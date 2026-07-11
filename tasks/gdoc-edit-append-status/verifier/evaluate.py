#!/usr/bin/env python3
"""Evaluate gdoc-edit-append-status task.

Scoring (0.0 to 1.0):
  Per active project doc (x4):
    - Status block present with date + "Active" label  -> +0.10
    - Status block includes correct project name        -> +0.05
    - Status block includes correct current phase       -> +0.10
    Total per doc: 0.25  (x4 = 1.0)
  Penalties:
    - Each decoy (archived/completed/paused) doc modified -> -0.20 (x5 = -1.0)
  Tracked as metrics but not scored:
    - non_project_modified: number of non-project docs the agent touched
    - used_search: whether the agent used the search API
"""

import argparse
import importlib.util
import json
import os
from pathlib import Path


def _load_needles():
    """Load needles.py using TASKS_DIR (set in Dockerfile) for container paths."""
    tasks_dir = os.environ.get("TASKS_DIR")
    if tasks_dir:
        data_dir = Path(tasks_dir) / "gdoc-edit-append-status" / "data"
    else:
        # Local dev: evaluate.py lives in verifier/ alongside data/
        data_dir = Path(__file__).resolve().parent.parent / "data"
    spec = importlib.util.spec_from_file_location("needles", data_dir / "needles.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_needles = _load_needles()
PROJECT_DOC_IDS = _needles.PROJECT_DOC_IDS
DECOY_DOC_IDS = _needles.DECOY_DOC_IDS
EXPECTED_PHASES = _needles.EXPECTED_PHASES

# Markers that must appear in the status block
STATUS_DATE = _needles.STATUS_DATE
STATUS_LABEL = _needles.STATUS_LABEL

# Project names (extracted from needle titles)
PROJECT_NAMES = {n["id"]: n["name"].replace(" Overview", "").replace(" Design Doc", "")
                                     .replace(" Proposal", "").replace(" Sprint Plan", "")
                 for n in _needles.NEEDLES}


def _extract_text(body: dict) -> str:
    text_parts = []
    for element in body.get("content", []):
        paragraph = element.get("paragraph")
        if not paragraph:
            continue
        for para_element in paragraph.get("elements", []):
            text_run = para_element.get("textRun")
            if text_run:
                text_parts.append(text_run.get("content", ""))
    return "".join(text_parts)


def evaluate(final_state: dict, diff: dict, action_log: list) -> dict:
    metrics = {}
    reward = 0.0
    agent_acted = any(entry.get("method") in {"POST", "PATCH", "PUT", "DELETE"} for entry in action_log)

    all_docs = {}
    for user_data in final_state.get("users", {}).values():
        for doc in user_data.get("documents", []):
            all_docs[doc["id"]] = doc

    appended_count = 0
    phase_correct_count = 0
    name_correct_count = 0
    for doc_id in PROJECT_DOC_IDS:
        doc = all_docs.get(doc_id)
        if not doc:
            metrics[f"status_{doc_id}"] = "missing"
            continue

        text = _extract_text(doc.get("body", {}))
        text_lower = text.lower()

        # Check basic status block markers (date + label)
        has_date = STATUS_DATE.lower() in text_lower
        has_label = STATUS_LABEL.lower() in text_lower
        has_status_header = any(kw in text_lower for kw in [
            "status review", "status update", "status snapshot",
            "status check", "status note", "status:",
            "check-in", "checkin",
        ])
        has_basic = has_date and has_label and has_status_header

        if has_basic:
            reward += 0.10
            appended_count += 1

        # Check project name in the appended block
        expected_name = PROJECT_NAMES.get(doc_id, "")
        has_name = expected_name.lower() in text_lower if expected_name else False
        if has_basic and has_name:
            reward += 0.05
            name_correct_count += 1

        # Check current phase/focus extracted from content
        expected_phrases = EXPECTED_PHASES.get(doc_id, [])
        # Look for the phase in the APPENDED status block, not the original content.
        # Find text after the last status-related header.
        status_block = ""
        for marker in ["status review", "status update", "status snapshot",
                        "status check", "status note", "status:",
                        "check-in", "checkin"]:
            idx = text_lower.rfind(marker)
            if idx >= 0:
                candidate = text_lower[idx:]
                if len(candidate) > len(status_block):
                    status_block = candidate
                break

        has_phase = any(phrase.lower() in status_block for phrase in expected_phrases)
        if has_basic and has_phase:
            reward += 0.10
            phase_correct_count += 1

        metrics[f"status_{doc_id}"] = {
            "basic": has_basic, "name": has_name, "phase": has_phase
        }

    metrics["docs_appended"] = appended_count
    metrics["docs_with_name"] = name_correct_count
    metrics["docs_with_phase"] = phase_correct_count
    metrics["docs_total"] = len(PROJECT_DOC_IDS)

    # Track collateral damage — penalize modifying decoy project docs
    decoys_modified = 0
    non_project_modified = 0
    for user_data in diff.get("updated", {}).values():
        for doc in user_data.get("documents", {}).get("updated", []):
            doc_id = doc.get("id")
            if doc_id in DECOY_DOC_IDS:
                decoys_modified += 1
            elif doc_id not in PROJECT_DOC_IDS:
                non_project_modified += 1

    # Penalize 0.20 per decoy doc modified (max -1.0 for all 5)
    reward -= decoys_modified * 0.20
    metrics["decoys_modified"] = decoys_modified
    metrics["non_project_modified"] = non_project_modified

    used_search = any(
        "q=" in entry.get("path", "").lower()
        for entry in action_log
        if entry.get("method") == "GET"
    )
    metrics["used_search"] = used_search

    return {"reward": round(max(min(reward, 1.0), 0.0), 2), "done": True, "metrics": metrics}


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
    parser.add_argument("--state", required=True)
    parser.add_argument("--diff", required=True)
    parser.add_argument("--action-log", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    final_state = json.loads(open(args.state).read())
    diff = json.loads(open(args.diff).read())
    action_log_data = json.loads(open(args.action_log).read())
    log_entries = action_log_data.get("entries", action_log_data)

    result = evaluate(final_state, diff, log_entries)
    _write_reward(result, args.output)


if __name__ == "__main__":
    main()
