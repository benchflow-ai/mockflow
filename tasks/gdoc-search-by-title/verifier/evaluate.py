#!/usr/bin/env python3
"""Evaluate gdoc-search-by-title task.

Scoring (0.0 to 1.0):
  - New document exists with title containing "Sprint Action Items" -> +0.15
  - Contains action items from BOTH needle docs -> proportional up to +0.50
    (7 total items: 4 from planning notes, 3 from async follow-ups)
  - Only action items (no extra content from source) -> +0.10
  - No decoy action items contaminating the output -> proportional up to +0.10
    (loses 0.10 * (decoy_count / total_decoy_tracked) for contamination)
  - Original docs not deleted or modified -> +0.05
  - Used Drive search (not just listing) -> +0.10

All bonuses except new_doc_exists require agent_acted = True,
defined as having made at least one mutating API call (POST/PATCH/PUT/DELETE).
"""

import argparse
import importlib.util
import json
import os

def _get_data_dir():
    """Locate the task data directory reliably inside the container."""
    tasks_dir = os.environ.get("TASKS_DIR")
    if tasks_dir:
        candidate = os.path.join(tasks_dir, "gdoc-search-by-title", "data")
        if os.path.isdir(candidate):
            return candidate
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data")

def _load_needles():
    """Load needles.py by file path to avoid sys.path/sys.modules collisions."""
    needles_path = os.path.join(_get_data_dir(), "needles.py")
    spec = importlib.util.spec_from_file_location("needles_gdoc_search_by_title", needles_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

_needles = _load_needles()
NEEDLE_DOC_IDS = [_needles.DOC_SPRINT_PLANNING, _needles.DOC_SPRINT_FOLLOWUP]

# Action items from the primary planning doc
PRIMARY_ACTION_ITEMS = [
    "API v2 migration plan",
    "performance benchmarks",
    "auth middleware RFC",
    "roadmap in Notion",
]

# Action items from the async follow-up doc
FOLLOWUP_ACTION_ITEMS = [
    "staging environment for API v2",
    "integration tests for new auth flow",
    "p95 latency baselines",
]

ALL_ACTION_ITEMS = PRIMARY_ACTION_ITEMS + FOLLOWUP_ACTION_ITEMS

# Decoy action items that should NOT appear in the output.
# Expanded with items from harder decoys (retro, platform team, mid-cycle).
DECOY_ITEMS = [
    # From "Q1 Sprint Planning Draft" (outdated draft)
    "investigate API v2 feasibility",
    "benchmark candidate tools",
    "gather team velocity data",
    # From "Q1 Sprint Planning Notes - Archive" (old cycle)
    "login page redesign",
    "close out Q4 OKRs",
    "migrate CI to GitHub Actions",
    # From "Q1 Planning Recap & Action Items" (org-level, not sprint)
    "finalize headcount plan",
    "submit budget proposal",
    "schedule Q1 all-hands",
    # From "Sprint Action Items - Sprint 16" (wrong sprint)
    "flaky e2e tests in CI",
    "deployment runbook",
    "payment service latency",
    # From "Q1 Sprint Retro — Action Items" (retro, not planning)
    "retry logic to flaky integration tests",
    "PR review SLA document",
    "automated test failure alerts",
    "audit and close stale PRs",
    # From "Q1 Sprint Planning Notes — Platform Team" (different team)
    "Kubernetes upgrade runbook",
    "Terraform modules for staging",
    "Datadog dashboards",
    "load testing scripts for API gateway",
    # From "Sprint Planning Mid-Cycle Check-in" (updated/re-scoped versions)
    "rollback strategy",
    "extend performance benchmarks",
    "edge cases to auth middleware",
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

    # agent_acted = made at least one mutating API call
    agent_acted = any(
        entry.get("method") in {"POST", "PATCH", "PUT", "DELETE"}
        for entry in action_log
    )
    metrics["agent_acted"] = agent_acted

    # Build lookup of all documents
    all_docs = {}
    for user_data in final_state.get("users", {}).values():
        for doc in user_data.get("documents", []):
            all_docs[doc["id"]] = doc

    # Check for new document with correct title
    new_docs = []
    for user_data in diff.get("updated", {}).values():
        new_docs.extend(user_data.get("documents", {}).get("added", []))

    action_items_doc = None
    for doc in new_docs:
        title = doc.get("title", "").lower()
        if "sprint" in title and "action" in title:
            action_items_doc = doc
            break

    metrics["new_doc_exists"] = action_items_doc is not None
    if action_items_doc:
        reward += 0.15  # created doc with correct title

        body = action_items_doc.get("body", {})
        text = _extract_text(body).lower()

        # Check for action items from BOTH needle docs (proportional)
        found_primary = sum(1 for item in PRIMARY_ACTION_ITEMS if item.lower() in text)
        found_followup = sum(1 for item in FOLLOWUP_ACTION_ITEMS if item.lower() in text)
        found_total = found_primary + found_followup
        metrics["primary_items_found"] = found_primary
        metrics["followup_items_found"] = found_followup
        metrics["action_items_found"] = found_total
        metrics["action_items_total"] = len(ALL_ACTION_ITEMS)

        if found_total > 0:
            reward += 0.50 * (found_total / len(ALL_ACTION_ITEMS))

        # Precision bonus: "just the action items, nothing else"
        noise_phrases = ["key decisions", "attendees", "next meeting",
                         "proposed topics", "sprint cadence", "this template",
                         "what went well", "what to improve"]
        noise_found = sum(1 for p in noise_phrases if p in text)
        metrics["noise_phrases_found"] = noise_found
        if noise_found == 0:
            reward += 0.10

        # Decoy contamination: proportional penalty.
        # Each decoy item found costs a fraction of the 0.10 bonus.
        decoy_found = sum(1 for item in DECOY_ITEMS if item.lower() in text)
        metrics["decoy_items_found"] = decoy_found
        metrics["decoy_items_total"] = len(DECOY_ITEMS)
        if decoy_found == 0:
            reward += 0.10
        else:
            # Proportional loss: lose up to 0.10. Any 3+ decoy items = full loss.
            contamination_ratio = min(decoy_found / 3.0, 1.0)
            reward += 0.10 * (1.0 - contamination_ratio)
    else:
        metrics["primary_items_found"] = 0
        metrics["followup_items_found"] = 0
        metrics["action_items_found"] = 0
        metrics["action_items_total"] = len(ALL_ACTION_ITEMS)
        metrics["noise_phrases_found"] = 0
        metrics["decoy_items_found"] = 0
        metrics["decoy_items_total"] = len(DECOY_ITEMS)

    # Check original documents not deleted
    originals_preserved = all(doc_id in all_docs for doc_id in NEEDLE_DOC_IDS)
    metrics["original_preserved"] = originals_preserved
    if originals_preserved and action_items_doc is not None:
        reward += 0.05

    # Bonus for using Drive search (q= parameter) instead of brute-force listing
    used_search = any(
        "q=" in entry.get("path", "").lower()
        for entry in action_log
        if entry.get("method") == "GET"
    )
    metrics["used_search"] = used_search
    if used_search and agent_acted:
        reward += 0.10

    metrics["api_calls"] = len(action_log)

    return {"reward": round(min(max(reward, 0.0), 1.0), 2), "done": True, "metrics": metrics}


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
