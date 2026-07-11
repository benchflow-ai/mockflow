#!/usr/bin/env python3
"""Evaluate multi-mail-slack-invite task.

Scoring (0.0 – 1.0):

  +0.20  Easy channel memberships correct (partial)
           Score = 0.20 * (correct_easy / total_easy)

  +0.20  Medium channel memberships correct (partial)
           Score = 0.20 * (correct_medium / total_medium)

  +0.20  Hard channel memberships correct (partial)
           Score = 0.20 * (correct_hard / total_hard)

  +0.10  Gmail list/search: agent called the list endpoint at least once
  +0.20  Gmail reads: proportional to individual SkillsBench messages read
           Score = 0.20 * (skillsbench_emails_read / total_skillsbench_emails)

  +0.10  No false positives among contributors (partial)
           Score = 0.10 * (contributors not placed in any wrong channel / total)
           Non-contributor users (e.g. slackbot) are ignored.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
from pathlib import Path


# ---------------------------------------------------------------------------
# Load expected data from scenarios.py
# ---------------------------------------------------------------------------

def _load_scenarios_mod():
    tasks_dir = os.environ.get("TASKS_DIR")
    if tasks_dir:
        data_dir = Path(tasks_dir) / "multi-mail-slack-invite" / "data"
    else:
        data_dir = Path(__file__).resolve().parent.parent / "data"
    spec = importlib.util.spec_from_file_location(
        "scenarios", data_dir / "scenarios.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _build_expected() -> tuple[dict[str, set[str]], dict[str, set[str]]]:
    """Return (channel→{username}, contributor→{channels})."""
    sc = _load_scenarios_mod()
    channel_to_users: dict[str, set[str]] = {
        sc.CHANNEL_EASY:   set(),
        sc.CHANNEL_MEDIUM: set(),
        sc.CHANNEL_HARD:   set(),
    }
    contributor_to_chs: dict[str, set[str]] = {}

    for c in sc.CONTRIBUTORS:
        uname = c["slack_username"]
        contributor_to_chs[uname] = set(c["channels"])
        for ch in c["channels"]:
            channel_to_users[ch].add(uname)

    return channel_to_users, contributor_to_chs


TASK_CHANNELS = {
    "skillsbench_task_easy",
    "skillsbench_task_medium",
    "skillsbench_task_hard",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _channel_member_names(
    ws_state: dict, ch_id: str, uid_to_name: dict[str, str]
) -> set[str]:
    return {
        uid_to_name.get(m["user_id"], "")
        for m in ws_state.get("channel_members", [])
        if m["channel_id"] == ch_id
    }


_MSG_PATH_RE = re.compile(
    r"^/gmail/v1/users/[^/]+/messages/([^/?]+)$"
)
_MSG_LIST_RE = re.compile(
    r"^/gmail/v1/users/[^/]+/messages$"
)


def _gmail_read_ids(action_log: list[dict]) -> set[str]:
    """Return set of message IDs fetched via GET .../messages/{id}."""
    ids: set[str] = set()
    for entry in action_log:
        if entry.get("method", "").upper() != "GET":
            continue
        path = entry.get("path", "")
        m = _MSG_PATH_RE.match(path)
        if m:
            ids.add(m.group(1))
    return ids


def _gmail_list_called(action_log: list[dict]) -> bool:
    """Return True if agent made any GET call to the messages list endpoint."""
    for entry in action_log:
        if entry.get("method", "").upper() != "GET":
            continue
        path = entry.get("path", "").split("?")[0]
        if _MSG_LIST_RE.match(path):
            return True
    return False


def _skillsbench_message_ids(gmail_state: dict) -> set[str]:
    """Return IDs of all seeded SkillsBench emails across all users."""
    ids: set[str] = set()
    for _user_id, inbox in gmail_state.get("users", {}).items():
        for msg in inbox.get("messages", []):
            subject = msg.get("subject", "")
            if "[SkillsBench]" in subject:
                ids.add(msg["id"])
    return ids


# ---------------------------------------------------------------------------
# Main evaluate function
# ---------------------------------------------------------------------------

def evaluate(
    final_state: dict,
    diff: dict,
    action_log: list[dict],
    gmail_state: dict,
    gmail_action_log: list[dict],
) -> dict:
    channel_to_users, _contributor_to_chs = _build_expected()
    sc = _load_scenarios_mod()

    expected_easy   = channel_to_users[sc.CHANNEL_EASY]
    expected_medium = channel_to_users[sc.CHANNEL_MEDIUM]
    expected_hard   = channel_to_users[sc.CHANNEL_HARD]

    metrics: dict = {}
    reward = 0.0

    ws_state    = final_state.get("workspaces", {}).get("workspace_001", {})
    channels    = {c["name"]: c for c in ws_state.get("channels", [])}
    uid_to_name = {u["id"]: u["name"] for u in ws_state.get("users", [])}

    def members_of(ch_name: str) -> set[str]:
        ch = channels.get(ch_name)
        if not ch:
            return set()
        return _channel_member_names(ws_state, ch["id"], uid_to_name)

    # ------------------------------------------------------------------
    # 1. Easy channel (+0.20, partial)
    # ------------------------------------------------------------------
    actual_easy    = members_of(sc.CHANNEL_EASY)
    correct_easy   = expected_easy & actual_easy
    easy_score     = round(0.20 * len(correct_easy) / len(expected_easy), 4) if expected_easy else 0.0
    reward        += easy_score

    metrics["easy"] = {
        "score":   easy_score,
        "correct": sorted(correct_easy),
        "missed":  sorted(expected_easy - actual_easy),
        "false_positives": sorted(actual_easy - expected_easy),
    }

    # ------------------------------------------------------------------
    # 2. Medium channel (+0.20, partial)
    # ------------------------------------------------------------------
    actual_medium  = members_of(sc.CHANNEL_MEDIUM)
    correct_medium = expected_medium & actual_medium
    medium_score   = round(0.20 * len(correct_medium) / len(expected_medium), 4) if expected_medium else 0.0
    reward        += medium_score

    metrics["medium"] = {
        "score":   medium_score,
        "correct": sorted(correct_medium),
        "missed":  sorted(expected_medium - actual_medium),
        "false_positives": sorted(actual_medium - expected_medium),
    }

    # ------------------------------------------------------------------
    # 3. Hard channel (+0.20, partial)
    # ------------------------------------------------------------------
    actual_hard    = members_of(sc.CHANNEL_HARD)
    correct_hard   = expected_hard & actual_hard
    hard_score     = round(0.20 * len(correct_hard) / len(expected_hard), 4) if expected_hard else 0.0
    reward        += hard_score

    metrics["hard"] = {
        "score":   hard_score,
        "correct": sorted(correct_hard),
        "missed":  sorted(expected_hard - actual_hard),
        "false_positives": sorted(actual_hard - expected_hard),
    }

    # ------------------------------------------------------------------
    # 4. Gmail operations (+0.30, partial)
    #    0.10 for calling the list/search endpoint at least once.
    #    0.20 proportional to how many seeded SkillsBench messages were
    #    individually read (GET .../messages/{id}).
    # ------------------------------------------------------------------
    seeded_ids   = _skillsbench_message_ids(gmail_state)
    total_seeded = len(seeded_ids)
    list_called  = _gmail_list_called(gmail_action_log)
    read_ids     = _gmail_read_ids(gmail_action_log)
    emails_read  = len(seeded_ids & read_ids)

    list_score = 0.10 if list_called else 0.0
    read_score = round(0.20 * emails_read / total_seeded, 4) if total_seeded else 0.0
    gmail_score = round(list_score + read_score, 4)
    reward += gmail_score

    metrics["gmail"] = {
        "score":        gmail_score,
        "emails_read":  emails_read,
        "total_seeded": total_seeded,
        "list_called":  list_called,
    }

    # ------------------------------------------------------------------
    # 5. No false positives among contributors (+0.10, partial)
    #    Only checks contributor usernames — ignores bots like slackbot.
    #    Score = 0.10 * (contributors not in any wrong channel / total)
    # ------------------------------------------------------------------
    _contributor_to_chs = {c["slack_username"]: set(c["channels"]) for c in sc.CONTRIBUTORS}
    total_contributors = len(_contributor_to_chs)
    clean = 0
    fp_details: dict[str, bool] = {}

    for uname, expected_chs in _contributor_to_chs.items():
        actual_chs = {
            ch for ch in TASK_CHANNELS
            if uname in members_of(ch)
        }
        is_clean = actual_chs.issubset(expected_chs)
        if is_clean:
            clean += 1
        fp_details[uname] = is_clean

    fp_score = round(0.10 * clean / total_contributors, 4) if total_contributors else 0.0
    if any(ch in channels for ch in TASK_CHANNELS):
        reward  += fp_score

    metrics["no_false_positives"] = {
        "score":   fp_score,
        "clean":   clean,
        "total":   total_contributors,
        "details": fp_details,
    }

    metrics["total_slack_api_calls"] = len(action_log)
    metrics["total_gmail_api_calls"] = len(gmail_action_log)
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
    parser = argparse.ArgumentParser(
        description="Evaluate multi-mail-slack-invite"
    )
    parser.add_argument("--state",            required=True)
    parser.add_argument("--diff",             required=True)
    parser.add_argument("--action-log",       required=True)
    parser.add_argument("--gmail-state",      required=True)
    parser.add_argument("--gmail-action-log", required=True)
    parser.add_argument("--output",           required=True)
    args = parser.parse_args()

    final_state      = json.loads(Path(args.state).read_text())
    diff             = json.loads(Path(args.diff).read_text())
    raw_log          = json.loads(Path(args.action_log).read_text())
    action_log       = raw_log.get("entries", raw_log) if isinstance(raw_log, dict) else raw_log
    gmail_state      = json.loads(Path(args.gmail_state).read_text())
    raw_gmail_log    = json.loads(Path(args.gmail_action_log).read_text())
    gmail_action_log = raw_gmail_log.get("entries", raw_gmail_log) if isinstance(raw_gmail_log, dict) else raw_gmail_log

    result = evaluate(final_state, diff, action_log, gmail_state, gmail_action_log)
    _write_reward(result, args.output)


if __name__ == "__main__":
    main()
