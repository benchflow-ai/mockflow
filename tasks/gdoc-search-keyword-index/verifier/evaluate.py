#!/usr/bin/env python3
"""Evaluate gdoc-search-keyword-index task.

Scoring (0.0 to 1.0):
  - Index document created with correct title ("Budget Documents Index") -> +0.15
  - Each of 5 budget docs found and listed in index -> +0.12 each (x5 = 0.60)
  - No false positives (non-budget docs listed) -> +0.10
  - Each false positive listed -> -0.15 (up to -0.45 cap)
  - Used search API -> +0.05
  - Multiple search queries used -> +0.10
"""

import argparse
import json


BUDGET_DOC_TITLES = [
    "Q1 Department Budget Proposal",
    "Project Phoenix Status Report",
    "Annual Planning Meeting Notes",
    "Vendor Evaluation Summary",
    "Facilities Operations Review",
]

DECOY_TITLES = [
    "Team Standup Notes",
    "API v2.0 Design Document",
    "Incident Postmortem",
    "Code Review Guidelines",
    "Onboarding Checklist",
    # Near-miss decoys (financial context, but no "budget" in content)
    "Q4 Revenue Forecast",
    "Compensation Review Process",
    "Office Lease Renewal Terms",
    "Q2 Cost Allocation Proposal",
]


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

    new_docs = []
    for user_data in diff.get("updated", {}).values():
        new_docs.extend(user_data.get("documents", {}).get("added", []))

    index_doc = None
    for doc in new_docs:
        title = doc.get("title", "").lower()
        if "budget" in title and "index" in title:
            index_doc = doc
            break

    metrics["index_doc_exists"] = index_doc is not None
    if index_doc:
        reward += 0.15

        body = index_doc.get("body", {})
        text = _extract_text(body)
        text_lower = text.lower()

        found_count = 0
        for title in BUDGET_DOC_TITLES:
            found = title.lower() in text_lower
            metrics[f"found_{title[:20].replace(' ', '_').lower()}"] = found
            if found:
                found_count += 1
                reward += 0.12

        metrics["budget_docs_found"] = found_count
        metrics["budget_docs_total"] = len(BUDGET_DOC_TITLES)

        false_positives = 0
        for title in DECOY_TITLES:
            if title.lower() in text_lower:
                false_positives += 1
        metrics["false_positives"] = false_positives
        metrics["no_false_positives"] = false_positives == 0

        # Graduated FP penalty: each false positive costs -0.15, up to -0.45
        fp_penalty = min(false_positives * 0.15, 0.45)
        reward -= fp_penalty
        metrics["fp_penalty"] = round(fp_penalty, 2)

        if false_positives == 0 and found_count >= 1:
            reward += 0.10
    else:
        metrics["budget_docs_found"] = 0
        metrics["budget_docs_total"] = len(BUDGET_DOC_TITLES)
        metrics["false_positives"] = 0

    metrics["api_calls"] = len(action_log)

    # Check if agent used search API
    search_queries = [
        entry for entry in action_log
        if entry.get("method") == "GET" and "q=" in entry.get("path", "").lower()
    ]
    used_search = len(search_queries) > 0
    metrics["used_search"] = used_search
    if used_search:
        reward += 0.05

    # Bonus for multiple search queries — finding all 5 docs requires
    # more than a single "budget" search since some docs bury the keyword
    used_multiple_searches = len(search_queries) >= 2
    metrics["used_multiple_searches"] = used_multiple_searches
    if used_multiple_searches:
        reward += 0.10

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
