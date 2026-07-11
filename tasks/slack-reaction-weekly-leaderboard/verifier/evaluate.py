#!/usr/bin/env python3
"""Evaluate slack-reaction-weekly-leaderboard task.

Seed state (7-day window, after self-reaction exclusion):
  Rank 1: sarah (U04SARAHKIM)   — 22 reactions (#general 12 + #engineering 10)
  Rank 2: priya (U02PRIYAPATEL) — 15 reactions (#general 8  + #product 7)
  Rank 3: james (U07JAMESBROWN) — 13 reactions (#frontend 17 total − 4 self = 13)
  Rank 4: dan   (U05DANLOPEZ)   —  9 reactions (#backend 9)

  Self-reaction trap: james has 17 raw reactions but 4 are self-reactions.
  Without exclusion, james ranks #2 (17 > priya's 15). With correct exclusion,
  james ranks #3 (13 < priya's 15).

  Time-window distractor: tom has 30 reactions in #general but posted 10 days ago.

Scoring (0.0 to 1.0):
  - A message was posted to #general                              → +0.2
  - Post mentions winner (sarah) and winner count (22)            → +0.3
  - Post mentions rank-2 (priya) and rank-2 count (15)            → +0.2
  - Post mentions rank-3 (james) and rank-3 count (13)            → +0.1
  - Leaderboard also shared to #random (sarah > 20 reactions)     → +0.2
"""

import argparse
import json
import os
import importlib.util
import pathlib


def _load_needles():
    tasks_dir = (
        pathlib.Path(os.environ["TASKS_DIR"])
        if "TASKS_DIR" in os.environ
        else pathlib.Path(__file__).resolve().parents[2]
    )
    needles_path = tasks_dir / "slack-reaction-weekly-leaderboard" / "data" / "needles.py"
    spec = importlib.util.spec_from_file_location("_leaderboard_needles", needles_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_needles = _load_needles()
WINNER_USER = _needles.WINNER_USER      # "sarah"
WINNER_COUNT = _needles.WINNER_COUNT    # 22
RANK2_USER = _needles.RANK2_USER        # "priya"
RANK2_COUNT = _needles.RANK2_COUNT      # 15
RANK3_USER = _needles.RANK3_USER        # "james"
RANK3_COUNT = _needles.RANK3_COUNT      # 13
DM_THRESHOLD = _needles.DM_THRESHOLD   # 20


def _channel_id(state: dict, name: str) -> str | None:
    for ws in state.get("workspaces", {}).values():
        for ch in ws.get("channels", []):
            if ch.get("name") == name:
                return ch["id"]
    return None


def _posted_texts(state: dict, diff: dict, channel_id: str) -> list[str]:
    texts = []
    for ws_diff in diff.get("updated", {}).values():
        for msg in ws_diff.get("messages", {}).get("added", []):
            if msg.get("channel_id") == channel_id:
                texts.append(msg.get("text", ""))
    return texts


def evaluate(final_state: dict, diff: dict, action_log: list) -> dict:
    metrics: dict = {}
    reward = 0.0

    general_id = _channel_id(final_state, "general")
    random_id = _channel_id(final_state, "random")

    general_posts = _posted_texts(final_state, diff, general_id) if general_id else []
    random_posts = _posted_texts(final_state, diff, random_id) if random_id else []

    # 1. Posted something to #general
    posted_to_general = len(general_posts) > 0
    if posted_to_general:
        reward += 0.2
    metrics["posted_to_general"] = posted_to_general

    all_general_text = " ".join(general_posts).lower()

    # 2. Winner (sarah + 22) in #general post
    winner_in_post = (
        WINNER_USER.lower() in all_general_text
        and str(WINNER_COUNT) in all_general_text
    )
    if winner_in_post:
        reward += 0.3
    metrics["winner_in_post"] = winner_in_post

    # 3. Rank-2 (priya + 15) in #general post
    rank2_in_post = (
        RANK2_USER.lower() in all_general_text
        and str(RANK2_COUNT) in all_general_text
    )
    if rank2_in_post:
        reward += 0.2
    metrics["rank2_in_post"] = rank2_in_post

    # 4. Rank-3 (james + 13) in #general post
    rank3_in_post = (
        RANK3_USER.lower() in all_general_text
        and str(RANK3_COUNT) in all_general_text
    )
    if rank3_in_post:
        reward += 0.1
    metrics["rank3_in_post"] = rank3_in_post

    # 5. Also shared to #random (because winner > DM_THRESHOLD)
    #    Validate the #random post actually mentions the winner name and count.
    all_random_text = " ".join(random_posts).lower()
    shared_to_random = (
        len(random_posts) > 0
        and WINNER_USER.lower() in all_random_text
        and str(WINNER_COUNT) in all_random_text
    )
    if shared_to_random:
        reward += 0.2
    metrics["shared_to_random"] = shared_to_random

    metrics["api_calls"] = len(action_log)
    return {"reward": min(round(reward, 2), 1.0), "done": True, "metrics": metrics}


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
