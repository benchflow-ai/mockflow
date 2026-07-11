"""Evaluator for multi-offboard-permission-cleanup task.

Performance task testing precision of corrective action under urgency.
The agent must revoke exactly one unauthorized external permission
(marco.silva) without overcorrecting on legitimate collaborators.

Scoring is [0, 1] with proportional deductions for imprecision.
"""

import argparse
import importlib.util
import json
import os
import re


def _load_data(module_name="needles"):
    """Load a data module using TASKS_DIR (works in Docker container)."""
    task_name = "multi-offboard-permission-cleanup"
    tasks_dir = os.environ.get("TASKS_DIR")
    if tasks_dir:
        path = os.path.join(tasks_dir, task_name, "data", f"{module_name}.py")
    else:
        path = os.path.join(os.path.dirname(__file__), "..", "data", f"{module_name}.py")
    spec = importlib.util.spec_from_file_location(module_name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


NOTIFY_KEYWORDS = re.compile(
    r"(revoke|remove|access|marco|silva|vertex)",
    re.IGNORECASE,
)


def evaluate(final_state: dict, diff: dict, action_log: list) -> dict:
    """Score the agent's precision in handling an unauthorized permission.

    Scoring (total 1.0):
      +0.05 Agent found the Strategy Deck
      +0.05 Agent listed permissions on the deck
      +0.20 Agent checked Slack for context
      +0.25 Agent revoked marco.silva's access
      +0.25 Precision: preserved legitimate permissions (-0.05 per legit removed, floor 0)
      +0.10 Agent notified owner/channel about the fix
      +0.10 Agent flagged Marco's access to Hiring Plan (bonus)

    Penalties:
      -0.20 Overcorrection: removed 3+ legitimate permissions
      File deleted or trashed: reward = 0.0
    """
    data = _load_data()
    STRATEGY_DECK_ID = data.STRATEGY_DECK_ID
    HIRING_PLAN_ID = data.HIRING_PLAN_ID
    UNAUTHORIZED_EMAIL = data.UNAUTHORIZED_EMAIL
    ALL_LEGITIMATE_EMAILS = data.ALL_LEGITIMATE_EMAILS

    reward = 0.0
    metrics = {}

    # ── Build file lookup from state ──
    files_list = final_state.get("files", [])
    file_by_id = {}
    folder_name_to_id = {}
    if isinstance(files_list, list):
        for f in files_list:
            file_by_id[f["id"]] = f
            if f.get("mimeType") == "application/vnd.google-apps.folder":
                folder_name_to_id[f["name"]] = f["id"]
    elif isinstance(files_list, dict):
        file_by_id = files_list

    # ── Build permission lookup from state ──
    all_perms = final_state.get("permissions", [])
    deck_current_emails = set()
    for p in all_perms:
        if p.get("fileId") == STRATEGY_DECK_ID:
            email = (p.get("emailAddress") or "").lower()
            if email:
                deck_current_emails.add(email)

    # Expected initial emails (from needles.py shared_with + auto owner)
    expected_emails = {e.lower() for e in ALL_LEGITIMATE_EMAILS} | {UNAUTHORIZED_EMAIL.lower()}

    # Determine what was removed by comparing current vs expected
    removed_emails = expected_emails - deck_current_emails

    # ── Hard floor: file deleted or trashed ──
    deck_meta = file_by_id.get(STRATEGY_DECK_ID)
    if deck_meta is None or deck_meta.get("trashed"):
        metrics["file_deleted"] = True
        metrics.update({
            "found_deck": False, "listed_perms": False, "checked_slack": False,
            "marco_revoked": False, "precision": 0.0, "legit_removed_count": 0,
            "notified": False, "flagged_hiring": False, "overcorrection": False,
        })
        return {"reward": 0.0, "done": True, "metrics": _numeric(metrics)}

    metrics["file_deleted"] = False

    any_perm_change = len(removed_emails) > 0

    # ── Positive scoring ──

    # 1. Agent found the Strategy Deck (+0.05)
    found_deck = any(
        STRATEGY_DECK_ID in str(e.get("path", "")) or
        STRATEGY_DECK_ID in str(e.get("url", "")) or
        "Q2 Strategy" in str(e.get("body", e.get("request_body", "")))
        for e in action_log
        if e.get("method", "").upper() == "GET"
    )
    if not found_deck:
        found_deck = any(
            ("files" in str(e.get("path", "")) and
             e.get("method", "").upper() == "GET" and
             ("Strategy" in str(e.get("body", e.get("request_body", e.get("params", "")))) or
              "Strategy" in str(e.get("url", e.get("path", "")))))
            for e in action_log
        )
    metrics["found_deck"] = found_deck
    if found_deck:
        reward += 0.05

    # 2. Agent listed permissions on the deck (+0.05)
    listed_perms = any(
        "permissions" in str(e.get("path", "")) and
        STRATEGY_DECK_ID in str(e.get("path", "")) and
        e.get("method", "").upper() == "GET"
        for e in action_log
    )
    metrics["listed_perms"] = listed_perms
    if listed_perms:
        reward += 0.05

    # 3. Agent checked Slack for context (+0.20)
    # Must actually read channel history or search messages, not just list channels
    checked_slack = any(
        "conversations.history" in str(e.get("path", "")) or
        "search.messages" in str(e.get("path", "")) or
        "channels.history" in str(e.get("path", ""))
        for e in action_log
    )
    metrics["checked_slack"] = checked_slack
    if checked_slack:
        reward += 0.20

    # 4. Revoked marco.silva's access (+0.25)
    marco_revoked = UNAUTHORIZED_EMAIL.lower() in removed_emails
    metrics["marco_revoked"] = marco_revoked
    if marco_revoked:
        reward += 0.25

    # 5. Precision: legitimate permissions preserved (+0.25 max)
    # Deduct 0.05 per legitimate permission removed, floor at 0
    legitimate_removed = removed_emails & {e.lower() for e in ALL_LEGITIMATE_EMAILS}
    legit_removed_count = len(legitimate_removed)
    precision = max(0.0, 0.25 - legit_removed_count * 0.05)
    metrics["legit_removed_count"] = legit_removed_count
    metrics["precision"] = precision
    if any_perm_change:
        reward += precision

    # 6. Overcorrection penalty: -0.20 if 3+ legitimate permissions removed
    overcorrection = legit_removed_count >= 3
    metrics["overcorrection"] = overcorrection
    if overcorrection:
        reward -= 0.20

    # 7. Notified owner/channel about the fix (+0.10)
    notified = False
    for e in action_log:
        path = str(e.get("path", ""))
        if "chat.postMessage" in path:
            body = str(e.get("body", e.get("request_body", "")))
            if NOTIFY_KEYWORDS.search(body):
                notified = True
                break
    metrics["notified"] = notified
    if notified:
        reward += 0.10

    # 8. Flagged Marco's access to Hiring Plan (bonus, +0.10)
    flagged_hiring = False
    for e in action_log:
        path = str(e.get("path", ""))
        if "chat.postMessage" in path:
            body = str(e.get("body", e.get("request_body", "")))
            if re.search(r"hiring.plan", body, re.IGNORECASE):
                flagged_hiring = True
                break
    if not flagged_hiring:
        hiring_current_emails = set()
        for p in all_perms:
            if p.get("fileId") == HIRING_PLAN_ID:
                email = (p.get("emailAddress") or "").lower()
                if email:
                    hiring_current_emails.add(email)
        if UNAUTHORIZED_EMAIL.lower() not in hiring_current_emails:
            flagged_hiring = True
    metrics["flagged_hiring"] = flagged_hiring
    if flagged_hiring:
        reward += 0.10

    return {"reward": max(0.0, min(1.0, round(reward, 2))), "done": True, "metrics": _numeric(metrics)}


def _numeric(metrics: dict) -> dict:
    """Convert booleans to int, drop non-numeric for VerifierResult."""
    return {k: (1 if v is True else 0 if v is False else v)
            for k, v in metrics.items()
            if isinstance(v, (int, float, bool))}


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
