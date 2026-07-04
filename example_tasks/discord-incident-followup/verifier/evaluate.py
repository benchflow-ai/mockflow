#!/usr/bin/env python3
"""Evaluate discord-incident-followup from the seeded SQLite database."""

from __future__ import annotations

import argparse
import importlib.util
import json
import math
import os
import sqlite3
from pathlib import Path

TASK_NAME = "discord-incident-followup"


def _load_needles() -> dict:
    tasks_dir = os.environ.get("TASKS_DIR", os.path.join(os.path.dirname(__file__), "..", ".."))
    path = os.path.join(tasks_dir, TASK_NAME, "data", "needles.py")
    spec = importlib.util.spec_from_file_location("discord_needles", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return {
        "target_channel": mod.TARGET_CHANNEL,
        "bot_username": mod.BOT_USERNAME,
        "expected_message": mod.EXPECTED_MESSAGE,
        "forbidden_channels": list(mod.FORBIDDEN_CHANNELS),
    }


def _message_rows(db_path: str, expected_message: str) -> list[dict]:
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    try:
        rows = con.execute(
            """
            select
              messages.id,
              messages.content,
              channels.name as channel_name,
              users.username as author_username,
              users.bot as author_is_bot
            from messages
            join channels on channels.id = messages.channel_id
            join users on users.id = messages.author_id
            where messages.content = ?
            order by messages.id
            """,
            (expected_message,),
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        con.close()


def evaluate(db_path: str, needles: dict | None = None) -> dict:
    needles = needles or _load_needles()
    rows = _message_rows(db_path, needles["expected_message"])

    target_rows = [
        row for row in rows
        if row["channel_name"] == needles["target_channel"]
        and row["author_username"] == needles["bot_username"]
        and bool(row["author_is_bot"])
    ]
    wrong_channel_rows = [
        row for row in rows
        if row["channel_name"] != needles["target_channel"]
    ]
    forbidden_rows = [
        row for row in rows
        if row["channel_name"] in set(needles["forbidden_channels"])
    ]

    reward = 0.0
    if target_rows:
        reward += 0.70
        if len(target_rows) == 1 and not wrong_channel_rows:
            reward += 0.30
    if len(target_rows) > 1:
        reward = min(reward, 0.70)
    if forbidden_rows:
        reward = 0.0

    done = len(target_rows) == 1 and not wrong_channel_rows
    metrics = {
        "target_message_count": len(target_rows),
        "wrong_channel_message_count": len(wrong_channel_rows),
        "forbidden_channel_message_count": len(forbidden_rows),
        "done": done,
    }
    return {
        "reward": max(0.0, min(1.0, round(reward, 2))),
        "done": done,
        "metrics": metrics,
    }


def _write_reward(result: dict, output_path: str) -> None:
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    numeric_metrics = {}
    details = dict(result.get("metrics", {}))
    for key, value in details.items():
        if isinstance(value, bool):
            numeric_metrics[key] = 1 if value else 0
        elif isinstance(value, (int, float)) and math.isfinite(float(value)) and 0.0 <= float(value) <= 1.0:
            numeric_metrics[key] = value

    payload = {"reward": result["reward"], "metrics": numeric_metrics, "details": details}
    out.write_text(json.dumps(payload, indent=2))
    (out.parent / "reward.txt").write_text(str(result["reward"]))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default=os.environ.get("DISCORD_DB_PATH", "/data/discord.db"))
    parser.add_argument("--output", default=os.path.join(os.environ.get("LOGS_DIR", "/logs/verifier"), "reward.json"))
    args = parser.parse_args()

    result = evaluate(args.db)
    _write_reward(result, args.output)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
