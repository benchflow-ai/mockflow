#!/usr/bin/env python3
"""Evaluate multi-doc-slack-spec-drift task.

Scoring (0.0 to 1.0):
  +0.25 x3  Each drift decision correctly flagged via a comment  = 0.75
  +0.15     Precision: no false-positive comments (gated on >= 1 drift matched)
  +0.10     Restraint: doc body NOT edited (gated on >= 1 drift matched)

  False-positive penalty: -0.05 per comment that matches no known drift.
  Clamped to [-1.0, 1.0].
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
from pathlib import Path


# ---------------------------------------------------------------------------
# Load expected data from needles.py
# ---------------------------------------------------------------------------

def _load_needles():
    tasks_dir = os.environ.get("TASKS_DIR")
    if tasks_dir:
        data_dir = Path(tasks_dir) / "multi-doc-slack-spec-drift" / "data"
    else:
        data_dir = Path(__file__).resolve().parent.parent / "data"
    spec = importlib.util.spec_from_file_location(
        "needles_multi_doc_slack_spec_drift", data_dir / "needles.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _get_needles():
    """Lazy-load needles (deferred to avoid import errors when env_0_gdrive is absent)."""
    if not hasattr(_get_needles, "_cache"):
        _get_needles._cache = _load_needles()
    return _get_needles._cache


def _get_doc_spec():
    return _get_needles().DOC_SPEC


def _get_drift_decisions():
    return _get_needles().DRIFT_DECISIONS


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _comment_matches_drift(comment: dict, drift: dict) -> bool:
    """Check if a comment's content mentions keywords for a drift decision.

    Two modes:
      keywords_any — match if ANY keyword appears (default, backward-compat)
      keywords_all — match only if ALL keywords appear (stricter)
    """
    content = comment.get("content", "").lower()
    if "keywords_all" in drift:
        return all(kw.lower() in content for kw in drift["keywords_all"])
    keywords = drift.get("keywords_any", drift.get("keywords", []))
    return any(kw.lower() in content for kw in keywords)


def _extract_comments(diff: dict, doc_id: str) -> list[dict]:
    """Extract added comments for a specific document from the diff."""
    comments = []
    for _user_id, user_data in diff.get("updated", {}).items():
        for comment in user_data.get("comments", {}).get("added", []):
            if comment.get("documentId") == doc_id:
                comments.append(comment)
    return comments


def _doc_body_edited(diff: dict, doc_id: str) -> bool:
    """Check if the document body was edited (updated entries exist)."""
    for _user_id, user_data in diff.get("updated", {}).items():
        for doc in user_data.get("documents", {}).get("updated", []):
            if doc.get("id") == doc_id:
                # Check if body was changed (has content changes beyond metadata)
                if "body" in doc:
                    return True
    return False


# ---------------------------------------------------------------------------
# Main evaluate function
# ---------------------------------------------------------------------------

def evaluate(final_state: dict, diff: dict, action_log: list) -> dict:
    metrics: dict = {}
    reward = 0.0

    DOC_SPEC = _get_doc_spec()
    DRIFT_DECISIONS = _get_drift_decisions()

    # Extract comments added to the spec doc
    comments = _extract_comments(diff, DOC_SPEC)
    metrics["comments_added"] = len(comments)

    # Score each drift decision
    drifts_matched = 0
    matched_comment_ids: set[int] = set()  # track which comments matched a drift

    for drift in DRIFT_DECISIONS:
        found = False
        for i, comment in enumerate(comments):
            if _comment_matches_drift(comment, drift):
                found = True
                matched_comment_ids.add(i)
                break
        metrics[f"drift_{drift['id']}"] = found
        if found:
            drifts_matched += 1
            reward += 0.25

    metrics["drifts_matched"] = drifts_matched
    metrics["drifts_total"] = len(DRIFT_DECISIONS)

    # Precision and restraint only awarded if at least 1 drift was matched
    if drifts_matched > 0:
        # Precision: penalize false-positive comments
        false_positives = len(comments) - len(matched_comment_ids)
        precision_score = max(0.0, 0.15 - false_positives * 0.05)
        reward += precision_score
        metrics["false_positives"] = false_positives
        metrics["precision_score"] = round(precision_score, 4)

        # Restraint: doc body should NOT be edited
        body_edited = _doc_body_edited(diff, DOC_SPEC)
        restraint_score = 0.0 if body_edited else 0.10
        reward += restraint_score
        metrics["body_edited"] = body_edited
        metrics["restraint_score"] = round(restraint_score, 4)
    else:
        metrics["false_positives"] = 0
        metrics["precision_score"] = 0.0
        metrics["body_edited"] = False
        metrics["restraint_score"] = 0.0

    reward = max(-1.0, min(1.0, round(reward, 2)))
    metrics["reward"] = reward

    return {"reward": reward, "done": True, "metrics": metrics}


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

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
    parser = argparse.ArgumentParser(
        description="Evaluate multi-doc-slack-spec-drift"
    )
    parser.add_argument("--state", required=True)
    parser.add_argument("--diff", required=True)
    parser.add_argument("--action-log", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    final_state = json.loads(Path(args.state).read_text())
    diff = json.loads(Path(args.diff).read_text())
    raw_log = json.loads(Path(args.action_log).read_text())
    action_log = raw_log.get("entries", raw_log) if isinstance(raw_log, dict) else raw_log

    result = evaluate(final_state, diff, action_log)
    _write_reward(result, args.output)


if __name__ == "__main__":
    main()
