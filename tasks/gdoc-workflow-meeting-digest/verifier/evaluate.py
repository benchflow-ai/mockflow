#!/usr/bin/env python3
"""Evaluate gdoc-workflow-meeting-digest task.

Scoring (0.0 to 1.0):
  - Digest document created with correct title: +0.2
  - Highlights from each week mentioned (proportional): +0.35
      Week 1 "auth service" or "authentication": +0.0875
      Week 2 "migration" + "staging": +0.0875
      Week 3 "rate limiter" or "rate limiting": +0.0875
      Week 4 "zero downtime" or "database migration complete": +0.0875
  - Blockers from each week mentioned (proportional): +0.25
      Week 1 "datetime" or "conversion": +0.0625
      Week 2 "memory leak": +0.0625
      Week 3 "maintenance window" or "ops team": +0.0625
      Week 4 "no blockers": +0.0625
  - Organized by week (chronological order): +0.1
  - Original standup docs preserved: +0.1
"""

import argparse
import importlib.util
import json
import os
from pathlib import Path


def _load_needles():
    # In container: BenchFlow uploads verifier/ to /verifier/, so __file__ is
    # /verifier/evaluate.py — parent.parent / "data" would be /data/ (wrong).
    # Use TASKS_DIR env var (set in Dockerfile) to find the task data dir.
    tasks_dir = os.environ.get("TASKS_DIR")
    if tasks_dir:
        data_dir = Path(tasks_dir) / "gdoc-workflow-meeting-digest" / "data"
    else:
        data_dir = Path(__file__).resolve().parent.parent / "data"
    spec = importlib.util.spec_from_file_location("needles", data_dir / "needles.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_needles = _load_needles()
STANDUP_DOC_IDS = _needles.STANDUP_DOC_IDS
DIGEST_TITLE = _needles.DIGEST_TITLE


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

    new_docs = []
    for user_data in diff.get("updated", {}).values():
        new_docs.extend(user_data.get("documents", {}).get("added", []))

    digest_doc = None
    for doc in new_docs:
        title = doc.get("title", "").lower()
        # Accept any title containing "standup" and "digest", or matching
        # the parameterized DIGEST_TITLE from needles.py
        if ("standup" in title and "digest" in title) or title == DIGEST_TITLE.lower():
            digest_doc = doc
            break

    metrics["digest_created"] = digest_doc is not None
    if digest_doc:
        reward += 0.2

        text = _extract_text(digest_doc.get("body", {})).lower()

        w1_highlight = "auth service" in text or "authentication" in text
        w2_highlight = "migration" in text and "staging" in text
        w3_highlight = "rate limiter" in text or "rate limiting" in text
        w4_highlight = "zero downtime" in text or "database migration complete" in text

        metrics["highlight_week1"] = w1_highlight
        metrics["highlight_week2"] = w2_highlight
        metrics["highlight_week3"] = w3_highlight
        metrics["highlight_week4"] = w4_highlight

        highlights_found = sum([w1_highlight, w2_highlight, w3_highlight, w4_highlight])
        metrics["highlights_found"] = highlights_found
        reward += highlights_found * 0.0875

        w1_blocker = "datetime" in text or "conversion" in text
        w2_blocker = "memory leak" in text
        w3_blocker = "maintenance window" in text or "ops team" in text
        w4_blocker = "no blockers" in text

        metrics["blocker_week1"] = w1_blocker
        metrics["blocker_week2"] = w2_blocker
        metrics["blocker_week3"] = w3_blocker
        metrics["blocker_week4"] = w4_blocker

        blockers_found = sum([w1_blocker, w2_blocker, w3_blocker, w4_blocker])
        metrics["blockers_found"] = blockers_found
        reward += blockers_found * 0.0625

        # --- Ordering check: content should be organized by week (chronological) ---
        # Find the text position of a unique keyword per week; verify ascending order
        week_markers = [
            ("week1", "auth service" if "auth service" in text else "authentication"),
            ("week2", "memory leak"),
            ("week3", "rate limiter" if "rate limiter" in text else "rate limiting"),
            ("week4", "zero downtime" if "zero downtime" in text else "database migration complete"),
        ]
        positions = []
        for label, marker in week_markers:
            if marker in text:
                positions.append((label, text.index(marker)))
        correctly_ordered = len(positions) >= 2 and all(
            positions[i][1] < positions[i + 1][1] for i in range(len(positions) - 1)
        )
        metrics["correctly_ordered"] = correctly_ordered
        if correctly_ordered:
            reward += 0.1
    else:
        # --- Partial credit (max 0.15): evidence the agent read standup docs ---
        # Two signals: (1) wrong-title doc with correct content, (2) agent fetched
        # the standup documents (GET requests containing standup doc IDs).
        partial = 0.0

        # Signal 1: content in a wrong-title doc or action-log request bodies
        fallback_texts = []
        for doc in new_docs:
            fallback_texts.append(_extract_text(doc.get("body", {})).lower())
        for entry in action_log:
            for field in ("body", "request_body"):
                raw = entry.get(field)
                if isinstance(raw, str):
                    fallback_texts.append(raw.lower())
                elif isinstance(raw, dict):
                    fallback_texts.append(json.dumps(raw).lower())
        fallback_text = " ".join(fallback_texts)

        if fallback_text.strip():
            fb_highlights = sum([
                "auth service" in fallback_text or "authentication" in fallback_text,
                "migration" in fallback_text and "staging" in fallback_text,
                "rate limiter" in fallback_text or "rate limiting" in fallback_text,
                "zero downtime" in fallback_text or "database migration complete" in fallback_text,
            ])
            fb_blockers = sum([
                "datetime" in fallback_text or "conversion" in fallback_text,
                "memory leak" in fallback_text,
                "maintenance window" in fallback_text or "ops team" in fallback_text,
                "no blockers" in fallback_text,
            ])
            partial += (fb_highlights + fb_blockers) * 0.0125

        # Signal 2: agent fetched standup docs (read the source material)
        action_log_text = json.dumps(action_log).lower()
        docs_read = sum(1 for did in STANDUP_DOC_IDS if did.lower() in action_log_text)
        metrics["standup_docs_read"] = docs_read
        partial += docs_read * 0.025  # 0.025 per doc, up to 0.10 for all 4

        partial = min(partial, 0.15)
        if partial > 0:
            reward += partial
            metrics["partial_content_credit"] = round(partial, 4)
        metrics["highlights_found"] = 0
        metrics["blockers_found"] = 0
        metrics["correctly_ordered"] = False

    originals_preserved = all(doc_id in all_docs for doc_id in STANDUP_DOC_IDS)
    metrics["originals_preserved"] = originals_preserved
    if originals_preserved and agent_acted:
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
