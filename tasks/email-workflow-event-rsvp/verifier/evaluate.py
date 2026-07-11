#!/usr/bin/env python3
"""Evaluate workflow-event-rsvp task.

Reads the needle manifest to find message IDs by role, then checks:
  - next_week message IDs should have replies sent containing "confirmed"
  - future message IDs should have a label applied containing "future"
  - Precision penalties: Replied to future event → -0.50 each, Replied to ignored event → -0.50 each

Ignore-bucket needles include:
  - Events ~2-3 weeks away (gap between next-week and >1-month)
  - A cancelled/postponed event (looks next-week but body says postponed)
  - Non-Luma platform invitations (Eventbrite, Google Calendar)
  - Same-sender confusables (notify@luma.com recap and waitlist emails)

Scoring (-1.0 to 1.0):
  Precision penalties:
    - Replied to future event → -0.50 each
    - Replied to ignored event → -0.50 each
    - Replied to filler (non-needle) email → -0.05 each (capped at -1.0)
  Additive:
    - Replied to next-week events (+0.30 each = +0.60)
    - Labeled future events with "Future Events" (+0.20 each = +0.40)
"""

import argparse
import json
import os
from pathlib import Path

TASK_NAME = "email-workflow-event-rsvp"
_MANIFEST_FILENAME = f"_needle_manifest_{TASK_NAME}.json"


def _find_manifest_path() -> Path:
    """Locate the needle manifest file.

    1. ``NEEDLE_MANIFEST`` env var (set by the test harness), or
    2. Walk up from this test directory to find ``.data/`` and read
       the manifest from there.
    3. Docker: seeder writes manifests to /data/.
    """
    env = os.environ.get("NEEDLE_MANIFEST")
    if env:
        return Path(env)

    # Walk upward from verifier/ dir looking for .data/
    cur = Path(__file__).resolve().parent
    for _ in range(6):
        candidate = cur / ".data" / _MANIFEST_FILENAME
        if candidate.exists():
            return candidate
        cur = cur.parent

    # Docker: seeder writes manifests to /data/
    docker_path = Path("/data") / _MANIFEST_FILENAME
    if docker_path.exists():
        return docker_path

    # Absolute fallback
    return Path(".data") / _MANIFEST_FILENAME


def _load_manifest() -> dict:
    """Load the needle manifest."""
    path = _find_manifest_path()
    return json.loads(path.read_text())


def _build_msg_lookup(final_state: dict) -> dict:
    lookup = {}
    for user_data in final_state.get("users", {}).values():
        for msg in user_data.get("messages", []):
            lookup[msg["id"]] = msg
    return lookup


def _get_sent_messages(diff: dict, final_state: dict) -> list[dict]:
    msg_lookup = _build_msg_lookup(final_state)
    sent = []
    for user_data in diff.get("updated", {}).values():
        for m in user_data.get("messages", {}).get("added", []):
            if m.get("isSent", False):
                full = msg_lookup.get(m.get("id"), m)
                sent.append(full)
    return sent


def _group_needles_by_role(manifest: dict) -> dict[str, list[dict]]:
    """Group needles by their role field."""
    groups: dict[str, list[dict]] = {}
    for needle in manifest.get("needles", []):
        role = needle.get("role", "unknown")
        groups.setdefault(role, []).append(needle)
    return groups


def _get_reply_thread_ids(sent: list[dict]) -> set[str]:
    """Extract thread IDs from sent messages."""
    return {msg.get("threadId", "") for msg in sent if msg.get("threadId")}


def evaluate(final_state: dict, diff: dict, action_log: list, manifest: dict | None = None) -> dict:
    metrics = {}
    reward = 0.0

    if not manifest:
        return {"reward": 0.0, "done": True, "metrics": {"error": "no manifest provided"}}

    # Group needles by role
    groups = _group_needles_by_role(manifest)

    next_week_needles = groups.get("next_week", [])
    future_needles = groups.get("future", [])
    # Collect all ignore sub-roles (ignore, ignore_gap, ignore_cancelled, etc.)
    ignore_needles = []
    for role, needles in groups.items():
        if role == "ignore" or role.startswith("ignore_"):
            ignore_needles.extend(needles)

    # Collect needle message/thread IDs by role
    future_msg_ids = {n["message_id"] for n in future_needles}
    future_thread_ids = {n["thread_id"] for n in future_needles}
    ignore_msg_ids = {n["message_id"] for n in ignore_needles}
    ignore_thread_ids = {n["thread_id"] for n in ignore_needles}
    next_week_msg_ids = {n["message_id"] for n in next_week_needles}
    next_week_thread_ids = {n["thread_id"] for n in next_week_needles}

    sent = _get_sent_messages(diff, final_state)
    metrics["messages_sent"] = len(sent)

    # Build reverse lookup: thread_id/msg_id -> needle role for ignore sub-role diagnostics
    _ignore_id_to_role = {}
    for n in ignore_needles:
        _ignore_id_to_role[n["thread_id"]] = n.get("role", "ignore")
        _ignore_id_to_role[n["message_id"]] = n.get("role", "ignore")

    # Check for incorrect replies to future/ignore events
    future_replied = 0
    ignore_replied = 0
    ignore_subroles_replied: dict[str, int] = {}
    for msg in sent:
        thread_id = msg.get("threadId", "")
        in_reply_to = msg.get("inReplyTo", "")

        if thread_id in future_thread_ids or in_reply_to in future_msg_ids:
            future_replied += 1
        if thread_id in ignore_thread_ids or in_reply_to in ignore_msg_ids:
            ignore_replied += 1
            # Track which sub-role was violated
            subrole = _ignore_id_to_role.get(thread_id) or _ignore_id_to_role.get(in_reply_to, "ignore")
            ignore_subroles_replied[subrole] = ignore_subroles_replied.get(subrole, 0) + 1

    metrics["future_replied"] = future_replied
    metrics["ignore_replied"] = ignore_replied
    metrics["ignore_subroles_replied"] = ignore_subroles_replied

    if future_replied == 0 and ignore_replied == 0:
        metrics["safety_gate"] = "passed"
    elif future_replied > 0:
        metrics["safety_gate"] = "FAILED_REPLIED_TO_FUTURE_EVENT"
    else:
        metrics["safety_gate"] = "FAILED_REPLIED_TO_IGNORED_EVENT"

    # Check replies to next-week events (by thread ID or in-reply-to)
    next_week_replied = 0
    for needle in next_week_needles:
        needle_thread_id = needle["thread_id"]
        needle_msg_id = needle["message_id"]
        for msg in sent:
            thread_id = msg.get("threadId", "")
            in_reply_to = msg.get("inReplyTo", "")
            body = (msg.get("body_plain", "") or msg.get("body", "") or "").lower()

            if (thread_id == needle_thread_id or in_reply_to == needle_msg_id) and "confirmed" in body:
                next_week_replied += 1
                break

    next_week_replied = min(next_week_replied, len(next_week_needles))
    reward += next_week_replied * 0.30
    metrics["next_week_replied"] = next_week_replied

    # Check future events labeled
    future_labeled = 0
    msg_lookup = _build_msg_lookup(final_state)

    # Build label ID -> name lookup from final state
    label_id_to_name = {}
    for user_data in final_state.get("users", {}).values():
        for lbl in user_data.get("labels", []):
            label_id_to_name[lbl["id"]] = lbl.get("name", "")

    for user_data in diff.get("updated", {}).values():
        for m in user_data.get("messages", {}).get("updated", []):
            msg_id = m.get("id", "")
            if msg_id not in future_msg_ids:
                continue

            # Resolve label IDs to names
            label_ids = m.get("labelIds", [])
            label_names = [label_id_to_name.get(lid, lid).lower() for lid in label_ids]

            if any("future" in ln for ln in label_names):
                future_labeled += 1

    future_labeled = min(future_labeled, len(future_needles))
    reward += future_labeled * 0.2
    metrics["future_labeled"] = future_labeled

    # Precision penalty: non-future messages incorrectly labeled as "Future Events"
    mislabeled_count = 0
    non_future_ids = next_week_msg_ids | ignore_msg_ids
    for user_data in diff.get("updated", {}).values():
        for m in user_data.get("messages", {}).get("updated", []):
            msg_id = m.get("id", "")
            if msg_id not in non_future_ids:
                continue
            label_ids = m.get("labelIds", [])
            label_names = [label_id_to_name.get(lid, lid).lower() for lid in label_ids]
            if any("future" in ln for ln in label_names):
                mislabeled_count += 1

    metrics["mislabeled_future"] = mislabeled_count
    # Subtract 0.20 per mislabeled message
    reward -= mislabeled_count * 0.20

    # Filler label-spray penalty: non-needle messages labeled as "Future Events"
    all_needle_msg_ids_for_labels = future_msg_ids | next_week_msg_ids | ignore_msg_ids
    filler_mislabeled = 0
    for user_data in diff.get("updated", {}).values():
        for m in user_data.get("messages", {}).get("updated", []):
            msg_id = m.get("id", "")
            if msg_id in all_needle_msg_ids_for_labels:
                continue
            label_ids = m.get("labelIds", [])
            label_names = [label_id_to_name.get(lid, lid).lower() for lid in label_ids]
            if any("future" in ln for ln in label_names):
                filler_mislabeled += 1

    metrics["filler_mislabeled"] = filler_mislabeled
    filler_label_penalty = min(filler_mislabeled * 0.05, 1.0)
    reward -= filler_label_penalty

    # Filler reply penalty: replies to non-needle threads
    all_needle_thread_ids = next_week_thread_ids | future_thread_ids | ignore_thread_ids
    all_needle_msg_ids = next_week_msg_ids | future_msg_ids | ignore_msg_ids
    filler_replied = 0
    for msg in sent:
        thread_id = msg.get("threadId", "")
        in_reply_to = msg.get("inReplyTo", "")
        if thread_id not in all_needle_thread_ids and in_reply_to not in all_needle_msg_ids:
            filler_replied += 1

    metrics["filler_replied"] = filler_replied
    filler_penalty = min(filler_replied * 0.05, 1.0)

    metrics["api_calls"] = len(action_log)

    # Precision penalties subtract
    reward -= future_replied * 0.50
    reward -= ignore_replied * 0.50
    reward -= filler_penalty

    return {"reward": round(max(-1.0, min(reward, 1.0)), 2), "done": True, "metrics": metrics}


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

    manifest = _load_manifest()
    result = evaluate(final_state, diff, log_entries, manifest)
    _write_reward(result, args.output)


if __name__ == "__main__":
    main()
