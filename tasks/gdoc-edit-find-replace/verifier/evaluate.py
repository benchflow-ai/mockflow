#!/usr/bin/env python3
"""Evaluate gdoc-edit-find-replace task.

Scoring (0.0 to 1.0):
  - Each needle doc correctly replaced (no "Nexus AI", has "Meridian Labs"): +0.15 x5 = 0.75
  - No unrelated documents modified: +0.15
  - Used search API to find documents: +0.10
"""

import argparse
import importlib.util
import json
import os
from pathlib import Path


def _load_needles():
    """Load needles module using TASKS_DIR env var.

    BenchFlow uploads verifier/ to /verifier/ inside the container, so __file__
    is /verifier/evaluate.py and relative paths to ../data break.
    Use TASKS_DIR (set in Dockerfile) to locate the task data directory.
    """
    tasks_dir = os.environ.get("TASKS_DIR")
    if tasks_dir:
        data_dir = Path(tasks_dir) / "gdoc-edit-find-replace" / "data"
    else:
        data_dir = Path(__file__).resolve().parent.parent / "data"

    spec = importlib.util.spec_from_file_location("needles", data_dir / "needles.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_needles = _load_needles()
NEEDLE_DOC_IDS = _needles.NEEDLE_DOC_IDS


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

    replaced_count = 0
    for doc_id in NEEDLE_DOC_IDS:
        doc = all_docs.get(doc_id)
        key = f"replaced_{doc_id}"
        if not doc:
            metrics[key] = False
            continue
        text = _extract_text(doc.get("body", {}))
        old_gone = "Nexus AI" not in text
        new_present = "Meridian Labs" in text
        success = old_gone and new_present
        metrics[key] = success
        if success:
            replaced_count += 1
            reward += 0.15

    metrics["needle_docs_replaced"] = replaced_count
    metrics["needle_docs_total"] = len(NEEDLE_DOC_IDS)

    non_needle_modified = []
    for user_data in diff.get("updated", {}).values():
        for doc in user_data.get("documents", {}).get("updated", []):
            if doc.get("id") not in NEEDLE_DOC_IDS:
                non_needle_modified.append(doc.get("id"))

    metrics["non_needle_modified_count"] = len(non_needle_modified)
    no_collateral = len(non_needle_modified) == 0
    metrics["no_collateral_damage"] = no_collateral
    if no_collateral and agent_acted:
        reward += 0.15

    used_search = any(
        "q=" in entry.get("path", "").lower()
        for entry in action_log
        if entry.get("method") == "GET"
    )
    metrics["used_search"] = used_search
    if used_search and agent_acted:
        reward += 0.10

    metrics["api_calls"] = len(action_log)

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
