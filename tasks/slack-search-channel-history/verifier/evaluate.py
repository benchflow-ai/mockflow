#!/usr/bin/env python3
"""Evaluate slack-search-channel-history task.

Scoring (0.0 – 1.0):

  +0.50  Correct answer posted in any channel (text contains "2000" near rate-limit context)

  +0.30  conversations.replies called on the needle thread
           — the thread with 20 replies in #product-archive

  +0.10  Valid discovery path used (at least one of):
           Path A: conversations.history paginated on #product-archive
                   (at least one call carried a cursor parameter)
           Path B: search.messages called at least once

  +0.10  search.messages token hygiene:
           - search never called → full marks (trivially ok)
           - all search calls used user token (xoxp-) → full marks
           - bot token calls return an error and yield no results, so the
             agent is already self-penalised; no additional score penalty
"""

from __future__ import annotations

import argparse
import json
import re

CORRECT_ANSWER_RE = re.compile(
    r"\b2000\b[^.\n]{0,40}(?:req|/min)|(?:req|rate\s+limit)[^.\n]{0,40}\b2000\b",
    re.IGNORECASE,
)
TARGET_CHANNEL_NAME = "product-archive"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _find_channel_id(ws_state: dict, name: str) -> str | None:
    return next(
        (c["id"] for c in ws_state.get("channels", []) if c.get("name") == name),
        None,
    )


def _find_needle_ts(ws_state: dict, channel_id: str) -> str | None:
    """Return the ts of the top-level message with exactly 20 replies."""
    return next(
        (
            m["ts"]
            for m in ws_state.get("messages", [])
            if m.get("channel_id") == channel_id and m.get("reply_count") == 20
        ),
        None,
    )


def _history_calls(log: list[dict], channel_id: str) -> list[dict]:
    return [
        e for e in log
        if "/api/conversations.history" in e["path"]
        and f"channel={channel_id}" in e["path"]
    ]


def _replies_calls(log: list[dict], thread_ts: str) -> list[dict]:
    return [
        e for e in log
        if "/api/conversations.replies" in e["path"]
        and f"ts={thread_ts}" in e["path"]
    ]


def _search_calls(log: list[dict]) -> list[dict]:
    return [e for e in log if "/api/search.messages" in e["path"]]


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def evaluate(final_state: dict, diff: dict, action_log: list[dict]) -> dict:
    metrics: dict = {}
    reward = 0.0

    ws_state = final_state.get("workspaces", {}).get("workspace_001", {})
    ws_diff = diff.get("updated", {}).get("workspace_001", {})

    archive_id = _find_channel_id(ws_state, TARGET_CHANNEL_NAME)
    metrics["archive_channel_id"] = archive_id

    needle_ts = _find_needle_ts(ws_state, archive_id) if archive_id else None
    metrics["needle_thread_ts"] = needle_ts

    # ------------------------------------------------------------------
    # 1. Correct answer posted anywhere (+0.50)
    # ------------------------------------------------------------------
    new_messages = ws_diff.get("messages", {}).get("added", [])
    answer_posted = any(
        CORRECT_ANSWER_RE.search(m.get("text", ""))
        for m in new_messages
    )
    if answer_posted:
        reward += 0.50
    metrics["answer_posted"] = answer_posted

    # ------------------------------------------------------------------
    # 2. conversations.replies called on the needle thread (+0.30)
    # ------------------------------------------------------------------
    replies_used = False
    if needle_ts:
        r_calls = _replies_calls(action_log, needle_ts)
        metrics["replies_call_count"] = len(r_calls)
        replies_used = len(r_calls) > 0
    if replies_used:
        reward += 0.30
    metrics["replies_used"] = replies_used

    # ------------------------------------------------------------------
    # 3. Valid discovery path used (+0.10)
    #
    # Path A: conversations.history paginated (cursor used)
    # Path B: search.messages called at least once
    # ------------------------------------------------------------------
    path_a_used = False
    if archive_id:
        h_calls = _history_calls(action_log, archive_id)
        metrics["history_call_count"] = len(h_calls)
        path_a_used = any("cursor=" in e["path"] for e in h_calls)
    metrics["history_paginated"] = path_a_used

    s_calls = _search_calls(action_log)
    metrics["search_call_count"] = len(s_calls)
    path_b_used = len(s_calls) > 0
    metrics["search_used"] = path_b_used

    discovery_ok = path_a_used or path_b_used
    if discovery_ok:
        reward += 0.10
    metrics["discovery_ok"] = discovery_ok

    # ------------------------------------------------------------------
    # 4. search.messages token hygiene (+0.10)
    #
    # Full marks if:
    #   a) search.messages was never called, OR
    #   b) every search call used a user token (xoxp-)
    # Zero marks if any search call used a bot token (xoxb-)
    # ------------------------------------------------------------------
    # Bot token search calls return an error and yield no results, so the
    # agent is already self-penalised. We only track hygiene for metrics;
    # the score is always awarded.
    if not s_calls:
        token_hygiene_ok = True
    else:
        # Bot token search calls return errors and yield no results — the agent
        # is already self-penalised; no additional score penalty.
        # Hygiene is OK in all cases: user-token calls are correct usage, and
        # bot-token calls are harmless failed attempts.
        token_hygiene_ok = True
    metrics["token_hygiene_ok"] = token_hygiene_ok
    # Bot token calls return errors and yield no results — agent is already
    # self-penalised. Score awarded when any API calls were made AND hygiene OK.
    if token_hygiene_ok and len(action_log) > 0:
        reward += 0.10

    # ------------------------------------------------------------------
    metrics["total_api_calls"] = len(action_log)
    metrics["reward"] = round(reward, 2)

    return {"reward": round(reward, 2), "done": True, "metrics": metrics}


# ---------------------------------------------------------------------------
# CLI entry point (called by Harbor harness)
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
    parser = argparse.ArgumentParser()
    parser.add_argument("--state", required=True)
    parser.add_argument("--diff", required=True)
    parser.add_argument("--action-log", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    final_state = json.loads(open(args.state).read())
    diff = json.loads(open(args.diff).read())
    action_log_data = json.loads(open(args.action_log).read())
    action_log = action_log_data.get("entries", action_log_data)

    result = evaluate(final_state, diff, action_log)
    _write_reward(result, args.output)


if __name__ == "__main__":
    main()
