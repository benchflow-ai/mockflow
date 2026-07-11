"""Single-source task data for multi-mail-slack-invite.

Scenario: Nexus AI launched an open-source benchmark project called SkillsBench.
  Contributors have emailed us to announce their task submissions.
  The user needs to:
    1. Read the contributor emails in Gmail.
    2. Categorize each contributor by the estimated completion time of their task(s):
         < 100 min   → skillsbench_task_easy
         100–500 min → skillsbench_task_medium
         > 500 min   → skillsbench_task_hard
       A contributor with tasks in multiple buckets is invited to multiple channels.
    3. Create the three Slack channels.
    4. Invite each contributor to every channel that matches their tasks.

Data sources (same directory):
  skillsbench_tasks.csv  — raw task data (name, email, times)
  answer_easy.csv        — names of contributors with at least one easy task
  answer_medium.csv      — names of contributors with at least one medium task
  answer_hard.csv        — names of contributors with at least one hard task
"""

from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path

_DATA = Path(__file__).parent

CSV_TASKS  = _DATA / "skillsbench_tasks.csv"
CSV_EASY   = _DATA / "answer_easy.csv"
CSV_MEDIUM = _DATA / "answer_medium.csv"
CSV_HARD   = _DATA / "answer_hard.csv"

CHANNEL_EASY   = "skillsbench_task_easy"
CHANNEL_MEDIUM = "skillsbench_task_medium"
CHANNEL_HARD   = "skillsbench_task_hard"

DIFFICULTY_CHANNEL = {
    "easy":   CHANNEL_EASY,
    "medium": CHANNEL_MEDIUM,
    "hard":   CHANNEL_HARD,
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_names(path: Path) -> set[str]:
    """Read a one-name-per-line CSV answer file."""
    with open(path, encoding="utf-8") as fh:
        return {line.strip() for line in fh if line.strip()}


def _slack_username(name: str) -> str:
    """'Jiahao Liu' → 'jiahao.liu',  'Jack' → 'jack'."""
    return ".".join(name.lower().split())


def _slack_key(name: str) -> str:
    return _slack_username(name).replace(".", "_")


# ---------------------------------------------------------------------------
# Load data
# ---------------------------------------------------------------------------

def load_contributors() -> list[dict]:
    """Return one dict per unique contributor name.

    Each entry:
        name, canonical_email, github,
        tasks (list of task dicts with task_name/pr_number/estimated_minutes),
        channels (list of channel names the contributor should be in),
        slack_username, slack_key
    """
    # ── 1. Load answer sets ──────────────────────────────────────────────────
    easy_names   = _load_names(CSV_EASY)
    medium_names = _load_names(CSV_MEDIUM)
    hard_names   = _load_names(CSV_HARD)
    all_names    = easy_names | medium_names | hard_names

    # ── 2. Group tasks by contributor name from the main CSV ─────────────────
    # For contributors appearing with multiple email addresses we collect all
    # tasks and later pick the canonical email (the address with most tasks).
    by_name: dict[str, dict] = defaultdict(lambda: {"tasks_by_email": defaultdict(list)})

    with open(CSV_TASKS, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            name = row["author_name"].strip()
            if name not in all_names:
                continue  # contributor not in any answer channel

            time_str = row.get(
                "estimated time for a human to complete the task (in minutes)", ""
            ).strip()
            try:
                minutes = int(time_str)
            except ValueError:
                continue

            email  = row["author_email"].strip()
            github = row.get("author_github_handle", "").strip()
            pr_raw = row.get("pr_number", "").strip()
            pr     = int(pr_raw) if pr_raw.isdigit() else None

            entry = by_name[name]
            # Keep track of github handle (prefer non-empty)
            if github and "github" not in entry:
                entry["github"] = github

            entry["tasks_by_email"][email].append({
                "task_name":         row["task_name"].strip(),
                "pr_number":         pr,
                "estimated_minutes": minutes,
            })

    # ── 3. Build final contributor list ─────────────────────────────────────
    contributors: list[dict] = []

    for name in sorted(all_names):  # stable alphabetical order
        entry = by_name.get(name)
        if not entry:
            continue  # name in answer CSV but not in tasks CSV (shouldn't happen)

        tasks_by_email = entry["tasks_by_email"]

        # Canonical email = address with the most tasks; ties broken by first seen
        canonical_email = max(tasks_by_email, key=lambda e: len(tasks_by_email[e]))

        # Merge all tasks (from all email addresses)
        all_tasks = [t for tasks in tasks_by_email.values() for t in tasks]
        # Sort by PR number for stability
        all_tasks.sort(key=lambda t: (t["pr_number"] is None, t["pr_number"] or 0))

        channels: list[str] = []
        if name in easy_names:
            channels.append(CHANNEL_EASY)
        if name in medium_names:
            channels.append(CHANNEL_MEDIUM)
        if name in hard_names:
            channels.append(CHANNEL_HARD)

        contributors.append({
            "name":             name,
            "canonical_email":  canonical_email,
            "github":           entry.get("github", ""),
            "tasks":            all_tasks,
            "channels":         channels,
            "slack_username":   _slack_username(name),
            "slack_key":        _slack_key(name),
        })

    return contributors


# ---------------------------------------------------------------------------
# Email generation
# ---------------------------------------------------------------------------

_EMAIL_TEMPLATES = [
    # Template 0: structured (original style)
    lambda name, task, github: "\n".join([
        "Hi,",
        "",
        "I'm excited to share my contribution to the SkillsBench open-source"
        " benchmark project by Nexus AI!",
        "",
        "Submitted task:",
        (f"  * {task['task_name']} (PR #{task['pr_number']}) — "
         f"estimated {task['estimated_minutes']} min"
         if task["pr_number"]
         else f"  * {task['task_name']} — estimated {task['estimated_minutes']} min"),
        "",
        "I'd love to stay connected with other contributors. Please let me know"
        " if anything else is needed.",
        "",
        f"Best regards,\n{name}" + (f"\nGitHub: @{github}" if github else ""),
    ]),
    # Template 1: conversational — time embedded in prose
    lambda name, task, github: "\n".join([
        f"Hey there,",
        "",
        f"Just wanted to let you know I submitted {task['task_name']}"
        + (f" (PR #{task['pr_number']})" if task["pr_number"] else "")
        + " to SkillsBench.",
        f"I think a competent human could finish it in roughly"
        f" {task['estimated_minutes']} minutes, give or take.",
        "",
        "Happy to help with reviews or anything else!",
        "",
        f"Cheers,\n{name}" + (f"\nhttps://github.com/{github}" if github else ""),
    ]),
    # Template 2: formal — time expressed in hours if >= 60
    lambda name, task, github: "\n".join([
        "Dear SkillsBench team,",
        "",
        f"I am writing to announce my task submission: {task['task_name']}"
        + (f" (pull request #{task['pr_number']})" if task["pr_number"] else "")
        + ".",
        "",
        f"Based on my testing, the estimated completion time for a human is"
        f" approximately {_format_time_natural(task['estimated_minutes'])}.",
        "",
        "Please do not hesitate to reach out if you need additional information.",
        "",
        f"Sincerely,\n{name}" + (f"\nGitHub: @{github}" if github else ""),
    ]),
    # Template 3: casual — time buried in parenthetical
    lambda name, task, github: "\n".join([
        f"Hi team!",
        "",
        f"Super excited about SkillsBench! I just pushed {task['task_name']}"
        + (f" in PR #{task['pr_number']}" if task["pr_number"] else "")
        + f" (should take around {task['estimated_minutes']} min for someone to"
        f" work through).",
        "",
        "Let me know if you need anything from my end.",
        "",
        f"— {name}" + (f" (@{github})" if github else ""),
    ]),
]


def _format_time_natural(minutes: int) -> str:
    """Convert minutes to a natural-language time string."""
    if minutes < 60:
        return f"{minutes} minutes"
    hours = minutes / 60
    if hours == int(hours):
        h = int(hours)
        return f"{h} hour{'s' if h != 1 else ''}"
    return f"{hours:.1f} hours"


def _format_task_email_body(name: str, task: dict, github: str) -> str:
    """One email per task row — single task, varied template."""
    import hashlib
    # Deterministic template selection based on task name
    h = int(hashlib.md5(task["task_name"].encode()).hexdigest(), 16)
    template = _EMAIL_TEMPLATES[h % len(_EMAIL_TEMPLATES)]
    return template(name, task, github)


def _load_task_emails() -> list[dict]:
    """One email per CSV row (each individual task submission).

    Uses the author_email from the CSV row (not necessarily canonical), so a
    contributor with multiple email addresses appears under different senders.
    Timestamps are seeded-randomly spread over 2026-03-01 … 2026-03-24 to
    interleave naturally with scenario filler emails.
    """
    import random
    rng = random.Random(42)

    all_names = {c["name"] for c in CONTRIBUTORS}
    github_by_name = {c["name"]: c["github"] for c in CONTRIBUTORS}

    rows: list[dict] = []
    with open(CSV_TASKS, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            name = row["author_name"].strip()
            if name not in all_names:
                continue
            time_str = row.get(
                "estimated time for a human to complete the task (in minutes)", ""
            ).strip()
            try:
                minutes = int(time_str)
            except ValueError:
                continue
            email  = row["author_email"].strip()
            pr_raw = row.get("pr_number", "").strip()
            pr     = int(pr_raw) if pr_raw.isdigit() else None
            rows.append({
                "name":    name,
                "email":   email,
                "github":  github_by_name.get(name, ""),
                "task": {
                    "task_name":         row["task_name"].strip(),
                    "pr_number":         pr,
                    "estimated_minutes": minutes,
                },
            })

    # Shuffle order so emails from the same contributor are not consecutive
    rng.shuffle(rows)

    emails: list[dict] = []
    for i, r in enumerate(rows):
        # Spread over 24 days (2026-03-01 … 2026-03-24), random hour
        day  = 1 + (i % 24)
        hour = rng.randint(7, 21)
        emails.append({
            "subject":      f"[SkillsBench] Task Contribution: {r['task']['task_name']}",
            "sender_name":  r["name"],
            "sender_email": r["email"],
            "received_at":  f"2026-03-{day:02d}T{hour:02d}:00:00+00:00",
            "body_plain":   _format_task_email_body(r["name"], r["task"], r["github"]),
            "labels":       ["INBOX"],
        })
    return emails


# ---------------------------------------------------------------------------
# Pre-computed lists (module-level constants)
# ---------------------------------------------------------------------------

CONTRIBUTORS: list[dict] = load_contributors()

# One email per task row (85 total); timestamps randomised over 2026-03-01…24
EMAILS: list[dict] = _load_task_emails()
