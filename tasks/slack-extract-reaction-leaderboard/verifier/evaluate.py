#!/usr/bin/env python3
"""Evaluate slack-extract-reaction-leaderboard task.

Scoring (0.0 to 1.0):
  - A message was posted to #random                        → +0.05
  - Post mentions rank-1 text snippet AND correct count    → +0.30
  - Post mentions rank-2 snippet+count, AFTER rank-1       → +0.25
  - Post mentions rank-3 snippet+count, AFTER rank-2       → +0.20
  - Agent reacted to the #1 message with :trophy: emoji    → +0.20
                                                      total  1.00
Penalties (applied after, can push score to 0.0):
  - Cross-channel distractor included in post              → -0.10
"""

import argparse
import json
import os
import re

import importlib.util
import pathlib


def _load_needles():
    tasks_dir = (
        pathlib.Path(os.environ["TASKS_DIR"])
        if "TASKS_DIR" in os.environ
        else pathlib.Path(__file__).resolve().parents[2]
    )
    needles_path = tasks_dir / "slack-extract-reaction-leaderboard" / "data" / "needles.py"
    spec = importlib.util.spec_from_file_location("_leaderboard_needles", needles_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_needles = _load_needles()
WINNER_TEXT = _needles.WINNER_TEXT
WINNER_COUNT = _needles.WINNER_REACTION_COUNT
RANK2_TEXT = _needles.RANK2_TEXT
RANK2_COUNT = _needles.RANK2_REACTION_COUNT
RANK3_TEXT = _needles.RANK3_TEXT
RANK3_COUNT = _needles.RANK3_REACTION_COUNT

# Use first 25 chars of each message as the snippet to check
WINNER_SNIPPET = WINNER_TEXT[:25].lower()
RANK2_SNIPPET = RANK2_TEXT[:25].lower()
RANK3_SNIPPET = RANK3_TEXT[:25].lower()

# Cross-channel distractor snippet (from #random meme post)
DISTRACTOR_SNIPPET = "found this absolute gem of".lower()


def _channel_id(state: dict, name: str) -> str | None:
    for ws in state.get("workspaces", {}).values():
        for ch in ws.get("channels", []):
            if ch.get("name") == name:
                return ch["id"]
    return None


def _posted_texts(diff: dict, channel_id: str) -> list[str]:
    texts = []
    for ws_diff in diff.get("updated", {}).values():
        for msg in ws_diff.get("messages", {}).get("added", []):
            if msg.get("channel_id") == channel_id:
                texts.append(msg.get("text", ""))
    return texts


def _trophy_reaction_added(action_log: list, general_id: str) -> bool:
    """Return True if the agent called reactions.add with :trophy: in #general."""
    for e in action_log:
        if e.get("method") == "POST" and "reactions.add" in e.get("path", ""):
            body = e.get("request_body") or {}
            if body.get("channel") == general_id and body.get("name") == "trophy":
                return True
    return False


def evaluate(final_state: dict, diff: dict, action_log: list) -> dict:
    metrics: dict = {}
    reward = 0.0

    random_id = _channel_id(final_state, "random")
    general_id = _channel_id(final_state, "general")
    posts = _posted_texts(diff, random_id) if random_id else []

    # 1. Posted something to #random
    posted_to_random = len(posts) > 0
    if posted_to_random:
        reward += 0.05
    metrics["posted_to_random"] = posted_to_random

    all_text = " ".join(posts).lower()

    # 2. Rank-1 message snippet + count in post
    rank1_found = WINNER_SNIPPET in all_text and bool(re.search(r'\b' + str(WINNER_COUNT) + r'\b', all_text))
    if rank1_found:
        reward += 0.30
    metrics["rank1_found"] = rank1_found

    # 3. Rank-2 message snippet + count, must appear AFTER rank-1 (ordering built-in)
    rank2_snippet_present = RANK2_SNIPPET in all_text and bool(re.search(r'\b' + str(RANK2_COUNT) + r'\b', all_text))
    rank2_found = False
    if rank2_snippet_present and rank1_found:
        pos1 = all_text.index(WINNER_SNIPPET)
        pos2 = all_text.index(RANK2_SNIPPET)
        rank2_found = pos2 > pos1
    metrics["rank2_found"] = rank2_found
    if rank2_found:
        reward += 0.25

    # 4. Rank-3 message snippet + count, must appear AFTER rank-2 (ordering built-in)
    rank3_snippet_present = RANK3_SNIPPET in all_text and bool(re.search(r'\b' + str(RANK3_COUNT) + r'\b', all_text))
    rank3_found = False
    if rank3_snippet_present and rank2_found:
        pos2 = all_text.index(RANK2_SNIPPET)
        pos3 = all_text.index(RANK3_SNIPPET)
        rank3_found = pos3 > pos2
    metrics["rank3_found"] = rank3_found
    if rank3_found:
        reward += 0.20

    # 5. Reacted to the #1 message with :trophy:
    trophy_added = _trophy_reaction_added(action_log, general_id) if general_id else False
    if trophy_added:
        reward += 0.20
    metrics["trophy_added"] = trophy_added

    # 6. Penalty: cross-channel distractor included in the leaderboard post
    distractor_present = posted_to_random and DISTRACTOR_SNIPPET in all_text
    if distractor_present:
        reward -= 0.10
    metrics["distractor_present"] = distractor_present

    reward = max(0.0, min(round(reward, 2), 1.0))
    metrics["api_calls"] = len(action_log)
    return {"reward": reward, "done": True, "metrics": metrics}


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
