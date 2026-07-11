#!/usr/bin/env python3
"""Evaluate gdoc-extract-content task.

Scoring (0.0 to 1.0):
  - Summary document exists with correct title -> +0.2
  - Contains at least 3 of 5 key decisions -> +0.4 (proportional)
  - Contains at least 3 of 5 deadlines -> +0.3 (proportional)
  - Original Aurora documents not modified -> +0.1
"""

import argparse
import importlib.util
import json
import os
from pathlib import Path


def _load_needles():
    """Load needles module using TASKS_DIR (container) or relative path (local dev)."""
    tasks_dir = os.environ.get("TASKS_DIR")
    if tasks_dir:
        data_dir = Path(tasks_dir) / "gdoc-extract-content" / "data"
    else:
        data_dir = Path(__file__).resolve().parent.parent / "data"
    spec = importlib.util.spec_from_file_location("needles", data_dir / "needles.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_needles = _load_needles()
AURORA_DOC_IDS = _needles.AURORA_DOC_IDS


# Key decisions across all Aurora documents
KEY_DECISIONS = [
    "PyTorch",           # Kickoff: Use PyTorch
    "feature store",     # Design Review: Adopt feature store pattern
    "A/B testing",       # Design Review: A/B testing framework
    "documentation",     # Retro: Assign documentation owners
    "spot instances",    # Budget: Use spot instances
]

# Key deadlines
KEY_DEADLINES = [
    "March 15",          # Kickoff: Data pipeline POC
    "April 1",           # Kickoff: Model training infra
    "May 15",            # Kickoff: Beta launch
    "March 30",          # Budget: Cost optimization report
    "April 5",           # Retro: Sprint 2 demo
]


def _extract_text(body: dict) -> str:
    """Extract plain text from body structure."""
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

    # Build lookup of all documents
    all_docs = {}
    for user_data in final_state.get("users", {}).values():
        for doc in user_data.get("documents", []):
            all_docs[doc["id"]] = doc

    # Check for new summary document
    new_docs = []
    for user_data in diff.get("updated", {}).values():
        new_docs.extend(user_data.get("documents", {}).get("added", []))

    summary_doc = None
    for doc in new_docs:
        title = doc.get("title", "").lower()
        if "aurora" in title and "summary" in title:
            summary_doc = doc
            break

    metrics["summary_doc_exists"] = summary_doc is not None and agent_acted
    if summary_doc:
        reward += 0.2

        body = summary_doc.get("body", {})
        text = _extract_text(body).lower()

        # Check key decisions
        found_decisions = sum(1 for d in KEY_DECISIONS if d.lower() in text)
        metrics["decisions_found"] = found_decisions
        metrics["decisions_total"] = len(KEY_DECISIONS)
        if found_decisions >= 3:
            reward += 0.4 * (found_decisions / len(KEY_DECISIONS))
        elif found_decisions >= 1:
            reward += 0.1

        # Check deadlines
        found_deadlines = sum(1 for d in KEY_DEADLINES if d.lower() in text)
        metrics["deadlines_found"] = found_deadlines
        metrics["deadlines_total"] = len(KEY_DEADLINES)
        if found_deadlines >= 3:
            reward += 0.3 * (found_deadlines / len(KEY_DEADLINES))
        elif found_deadlines >= 1:
            reward += 0.1
    else:
        metrics["decisions_found"] = 0
        metrics["decisions_total"] = len(KEY_DECISIONS)
        metrics["deadlines_found"] = 0
        metrics["deadlines_total"] = len(KEY_DEADLINES)

    # Check original documents preserved
    preserved = sum(1 for did in AURORA_DOC_IDS if did in all_docs)
    all_preserved = preserved == len(AURORA_DOC_IDS)

    # Also check they weren't modified
    modified_originals = []
    for user_data in diff.get("updated", {}).values():
        for doc in user_data.get("documents", {}).get("updated", []):
            if doc.get("id") in AURORA_DOC_IDS:
                modified_originals.append(doc["id"])

    metrics["originals_preserved"] = all_preserved
    metrics["originals_modified"] = len(modified_originals)
    if all_preserved and not modified_originals and summary_doc:
        reward += 0.1

    metrics["api_calls"] = len(action_log)
    metrics["used_search"] = any(
        "q=" in entry.get("path", "").lower()
        for entry in action_log
        if entry.get("method") == "GET"
    )
    metrics["safety_violations"] = []

    return {"reward": round(min(reward, 1.0), 2), "done": True, "metrics": metrics}


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
