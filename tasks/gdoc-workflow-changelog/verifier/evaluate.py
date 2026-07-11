#!/usr/bin/env python3
"""Evaluate gdoc-workflow-changelog task.

Scoring (0.0 to 1.0):
  - Changelog document created with correct title: +0.2
  - Changelog entries included (13 key changes, each ~0.038): +0.5
  - Entries in newest-first order: +0.1
  - Original API docs preserved: +0.1
  - Used search API: +0.1
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
        data_dir = Path(tasks_dir) / "gdoc-workflow-changelog" / "data"
    else:
        # Local dev: evaluate.py lives in verifier/ alongside data/
        data_dir = Path(__file__).resolve().parent.parent / "data"
    spec = importlib.util.spec_from_file_location("needles", data_dir / "needles.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_needles = _load_needles()
API_DOC_IDS = _needles.CHANGELOG_DOC_IDS

# Ordered newest-first (the instruction requires "newest changes first")
KEY_CHANGES = [
    {"name": "search_fuzzy", "terms": [["fuzzy matching"], ["typo tolerance"]], "date": "2026-03-18"},
    {"name": "users_pagination", "terms": [["pagination"]], "date": "2026-03-15"},
    {"name": "auth_oauth2", "terms": [["oauth2"], ["social login"]], "date": "2026-03-12"},
    {"name": "payments_recurring", "terms": [["recurring payments"]], "date": "2026-03-10"},
    {"name": "search_highlighting", "terms": [["highlighting"]], "date": "2026-03-05"},
    {"name": "payments_webhook", "terms": [["webhook"]], "date": "2026-03-01"},
    {"name": "auth_mfa", "terms": [["multi-factor"], ["mfa"], ["totp"]], "date": "2026-02-28"},
    {"name": "users_email_verification", "terms": [["email verification"]], "date": "2026-02-20"},
    {"name": "payments_refund", "terms": [["refund"]], "date": "2026-02-15"},
    {"name": "search_faceted", "terms": [["faceted search"]], "date": "2026-02-10"},
    {"name": "auth_refresh_token", "terms": [["refresh token"]], "date": "2026-02-01"},
    {"name": "search_initial_release", "terms": [["initial release", "search"]], "date": "2026-01-20"},
    {"name": "users_initial_release", "terms": [["initial release", "users"]], "date": "2026-01-10"},
]

CHANGE_SCORE = 0.5 / len(KEY_CHANGES)


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


def _check_change(text: str, change: dict) -> bool:
    """Check whether a key change appears in the text.

    The check is header-agnostic: it matches keyword groups anywhere in the
    text, so both "Changelog:" and "Changes:" section headers are handled
    correctly without special-casing.
    """
    for term_group in change["terms"]:
        if all(term in text for term in term_group):
            return True
    return False


def evaluate(final_state: dict, diff: dict, action_log: list) -> dict:
    metrics = {}
    reward = 0.0
    agent_acted = any(entry.get("method") in {"POST", "PATCH", "PUT", "DELETE"} for entry in action_log)

    all_docs = {}
    for user_data in final_state.get("users", {}).values():
        for doc in user_data.get("documents", []):
            all_docs[doc["id"]] = doc

    new_docs = []
    for user_data in diff.get("updated", {}).values():
        new_docs.extend(user_data.get("documents", {}).get("added", []))

    changelog_doc = None
    for doc in new_docs:
        title = doc.get("title", "").lower()
        if "changelog" in title and "api" in title:
            changelog_doc = doc
            break

    metrics["changelog_created"] = changelog_doc is not None
    if changelog_doc:
        reward += 0.2

        text = _extract_text(changelog_doc.get("body", {})).lower()

        changes_found = 0
        for change in KEY_CHANGES:
            found = _check_change(text, change)
            metrics[f"change_{change['name']}"] = found
            if found:
                changes_found += 1
                reward += CHANGE_SCORE

        metrics["changes_found"] = changes_found
        metrics["changes_total"] = len(KEY_CHANGES)

        # --- Ordering check: entries should appear newest-first ---
        # Find the text position of each found change; verify positions are ascending
        # (since KEY_CHANGES is already sorted newest-first, ascending positions = correct order)
        positions = []
        for change in KEY_CHANGES:
            if not metrics.get(f"change_{change['name']}"):
                continue
            for term_group in change["terms"]:
                if all(term in text for term in term_group):
                    pos = text.index(term_group[0])
                    positions.append(pos)
                    break
        correctly_ordered = all(positions[i] <= positions[i + 1] for i in range(len(positions) - 1))
        metrics["correctly_ordered"] = correctly_ordered
        if correctly_ordered and changes_found >= 2:
            reward += 0.1
    else:
        metrics["changes_found"] = 0
        metrics["changes_total"] = len(KEY_CHANGES)
        metrics["correctly_ordered"] = False

    originals_preserved = all(doc_id in all_docs for doc_id in API_DOC_IDS)
    metrics["originals_preserved"] = originals_preserved
    if originals_preserved and agent_acted:
        reward += 0.1

    used_search = any(
        "q=" in entry.get("path", "").lower()
        for entry in action_log
        if entry.get("method") == "GET"
    )
    metrics["used_search"] = used_search
    if used_search and agent_acted:
        reward += 0.1

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
