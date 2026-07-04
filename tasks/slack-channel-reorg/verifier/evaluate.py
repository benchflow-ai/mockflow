#!/usr/bin/env python3
"""Evaluate slack-channel-reorg task.

Scoring (0.0 – 1.0):

  +0.25  Correct placements — partial credit per person (11 expected)
           platform(3 Senior only) + aiml(3) + commerce(2 slots) + infra(1) + product(2)
           Score = 0.25 * (correct / 11)

  +0.10  No false positives — 6 unmatched members not added to any hiring channel
           Partial: 0.10 * (clean / 6)

  +0.20  Deduplication: all 3 public Metaverse source channels queried for members
           Full marks only if conversations.members was called on all 3 channel IDs.
           Partial: 0.20 * (queried / 3)

  +0.20  DMs sent to matched members (partial per person, 11 expected)
           Score = 0.20 * (dm_sent / 11)

  +0.10  DMs sent to unmatched members (partial per person, 6 expected)
           Score = 0.10 * (dm_sent / 6)

  +0.15  Private channel access — accessed #metaverse-stealth via conversations.members
           Binary: 0.15 if the stealth channel was queried, 0.0 otherwise.
           (diana.fox and noah.patel, the two hidden Stealth Project engineers,
            are only visible after the bot DMs chris.taylor to unlock access)
"""

from __future__ import annotations

import argparse
import json

EXPECTED_MATCHES: dict[str, set[str]] = {
    "platform-team-hiring":  {"james.wright", "alex.johnson", "diana.fox"},
    "aiml-team-hiring":      {"kevin.liu", "ryan.kim", "noah.patel"},
    "commerce-team-hiring":  {"emma.davis", "sophie.martin"},
    "infra-team-hiring":     {"priya.sharma"},
    "product-team-hiring":   {"sarah.chen", "lisa.park"},
}

HIRING_CHANNELS = set(EXPECTED_MATCHES.keys())
TOTAL_CORRECT = sum(len(v) for v in EXPECTED_MATCHES.values())  # 11

# 6 unmatched: 4 no-skill-match + natalie.brown (junior, platform Senior-only)
#              + tom.wilson (junior, commerce 2-slot limit)
UNMATCHED_USERNAMES = {
    "chris.taylor", "mike.torres", "mia.garcia", "david.lee",
    "natalie.brown", "tom.wilson",
}

# Public source channels only — stealth access is scored separately
SOURCE_CHANNELS = {"metaverse-general", "metaverse-engineering", "metaverse-product"}

STEALTH_CHANNEL_NAME = "metaverse-stealth"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_index(ws_state: dict):
    channels = {c["name"]: c for c in ws_state.get("channels", [])}
    users = {u["name"]: u for u in ws_state.get("users", [])}
    return channels, users


def _channel_member_names(ws_state: dict, channel_id: str, uid_to_name: dict) -> set[str]:
    return {
        uid_to_name.get(m["user_id"], "")
        for m in ws_state.get("channel_members", [])
        if m["channel_id"] == channel_id
    }


def _members_api_called(action_log: list[dict], channel_id: str) -> bool:
    return any(
        "/api/conversations.members" in e["path"] and channel_id in e["path"]
        for e in action_log
    )


def _user_dm_channel(ws_state: dict, user_id: str) -> str | None:
    """Return the DM channel ID that contains this user."""
    dm_ids = {c["id"] for c in ws_state.get("channels", []) if c.get("is_im")}
    for m in ws_state.get("channel_members", []):
        if m["channel_id"] in dm_ids and m["user_id"] == user_id:
            return m["channel_id"]
    return None


def _has_new_dm(ws_diff: dict, dm_channel_id: str) -> bool:
    added = ws_diff.get("messages", {}).get("added", [])
    return any(m.get("channel_id") == dm_channel_id for m in added)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def evaluate(final_state: dict, diff: dict, action_log: list[dict]) -> dict:
    metrics: dict = {}
    reward = 0.0

    ws_state = final_state.get("workspaces", {}).get("workspace_001", {})
    ws_diff = diff.get("updated", {}).get("workspace_001", {})

    channels, users = _build_index(ws_state)
    uid_to_name = {u["id"]: u["name"] for u in ws_state.get("users", [])}

    # ------------------------------------------------------------------
    # 1. Correct placements (+0.25, partial per person)
    # ------------------------------------------------------------------
    correct_placements = 0
    placement_details: dict[str, list] = {}

    for ch_name, expected_users in EXPECTED_MATCHES.items():
        ch = channels.get(ch_name)
        if not ch:
            placement_details[ch_name] = []
            continue
        member_names = _channel_member_names(ws_state, ch["id"], uid_to_name)
        placed = expected_users & member_names
        correct_placements += len(placed)
        placement_details[ch_name] = sorted(placed)

    placement_score = round(0.25 * correct_placements / TOTAL_CORRECT, 4)
    reward += placement_score
    metrics["correct_placements"] = correct_placements
    metrics["placement_score"] = placement_score
    metrics["placement_details"] = placement_details

    # ------------------------------------------------------------------
    # 2. No false positives (+0.10, partial per unmatched person)
    # ------------------------------------------------------------------
    unmatched_clean = 0
    fp_details: dict[str, bool] = {}

    for username in UNMATCHED_USERNAMES:
        user = users.get(username)
        if not user:
            unmatched_clean += 1
            fp_details[username] = True
            continue
        uid = user["id"]
        member_names_in_hiring = set()
        for ch_name in HIRING_CHANNELS:
            ch = channels.get(ch_name)
            if ch:
                member_names_in_hiring |= _channel_member_names(ws_state, ch["id"], uid_to_name)
        in_any_hiring = uid_to_name.get(uid, "") in member_names_in_hiring
        clean = not in_any_hiring
        if clean:
            unmatched_clean += 1
        fp_details[username] = clean

    fp_score = round(0.10 * unmatched_clean / len(UNMATCHED_USERNAMES), 4)
    if correct_placements > 0:
        reward += fp_score
    metrics["unmatched_clean"] = unmatched_clean
    metrics["false_positive_score"] = fp_score
    metrics["false_positive_details"] = fp_details

    # ------------------------------------------------------------------
    # 3. Deduplication: all 3 public source channels queried (+0.20, partial)
    # ------------------------------------------------------------------
    source_queried: dict[str, bool] = {}
    for ch_name in SOURCE_CHANNELS:
        ch = channels.get(ch_name)
        source_queried[ch_name] = ch is not None and _members_api_called(action_log, ch["id"])

    queried_count = sum(source_queried.values())
    dedup_score = round(0.20 * queried_count / len(SOURCE_CHANNELS), 4)
    if correct_placements > 0:
        reward += dedup_score
    metrics["source_channels_queried"] = source_queried
    metrics["deduplication_score"] = dedup_score

    # ------------------------------------------------------------------
    # 4. Private channel access: #metaverse-stealth queried (+0.15, binary)
    # ------------------------------------------------------------------
    stealth_ch = channels.get(STEALTH_CHANNEL_NAME)
    stealth_accessed = (
        stealth_ch is not None and _members_api_called(action_log, stealth_ch["id"])
    )
    stealth_members = {"diana.fox", "noah.patel"}
    stealth_placed = sum(
        1 for u in stealth_members
        if any(u in placement_details.get(ch, []) for ch in EXPECTED_MATCHES)
    )
    stealth_score = 0.15 if stealth_accessed and stealth_placed > 0 else 0.0
    reward += stealth_score
    metrics["stealth_channel_accessed"] = stealth_accessed
    metrics["stealth_access_score"] = stealth_score

    # ------------------------------------------------------------------
    # 5. DMs sent to matched members (+0.20, partial per person)
    # ------------------------------------------------------------------
    dm_matched = 0
    dm_matched_details: dict[str, bool] = {}

    matched_usernames = set().union(*EXPECTED_MATCHES.values())
    for username in matched_usernames:
        user = users.get(username)
        if not user:
            dm_matched_details[username] = False
            continue
        dm_ch = _user_dm_channel(ws_state, user["id"])
        sent = dm_ch is not None and _has_new_dm(ws_diff, dm_ch)
        if sent:
            dm_matched += 1
        dm_matched_details[username] = sent

    dm_matched_score = round(0.20 * dm_matched / TOTAL_CORRECT, 4)
    reward += dm_matched_score
    metrics["dm_matched_sent"] = dm_matched
    metrics["dm_matched_score"] = dm_matched_score
    metrics["dm_matched_details"] = dm_matched_details

    # ------------------------------------------------------------------
    # 6. DMs sent to unmatched members (+0.10, partial per person)
    # ------------------------------------------------------------------
    dm_unmatched = 0
    dm_unmatched_details: dict[str, bool] = {}

    for username in UNMATCHED_USERNAMES:
        user = users.get(username)
        if not user:
            dm_unmatched_details[username] = False
            continue
        dm_ch = _user_dm_channel(ws_state, user["id"])
        sent = dm_ch is not None and _has_new_dm(ws_diff, dm_ch)
        if sent:
            dm_unmatched += 1
        dm_unmatched_details[username] = sent

    dm_unmatched_score = round(0.10 * dm_unmatched / len(UNMATCHED_USERNAMES), 4)
    reward += dm_unmatched_score
    metrics["dm_unmatched_sent"] = dm_unmatched
    metrics["dm_unmatched_score"] = dm_unmatched_score
    metrics["dm_unmatched_details"] = dm_unmatched_details

    # ------------------------------------------------------------------
    metrics["total_api_calls"] = len(action_log)
    metrics["reward"] = round(reward, 2)

    return {"reward": round(reward, 2), "done": True, "metrics": metrics}


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
