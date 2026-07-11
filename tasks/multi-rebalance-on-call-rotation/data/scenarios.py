"""Single source of truth for rebalance-on-call-rotation.

Used by needles.py (seeder dispatcher) and evaluate.py (scoring).
"""

from __future__ import annotations

ENGINEERS = [
    {"name": "Alice Chen",    "email": "alice@nexusai.com",  "slack_key": "alice_chen",    "slack_username": "alice.chen",    "slack_id": "U001"},
    {"name": "Bob Martinez",  "email": "bob@nexusai.com",    "slack_key": "bob_martinez",  "slack_username": "bob.martinez",  "slack_id": "U002"},
    {"name": "Carol Wu",      "email": "carol@nexusai.com",  "slack_key": "carol_wu",      "slack_username": "carol.wu",      "slack_id": "U003"},
    {"name": "Derek Okafor",  "email": "derek@nexusai.com",  "slack_key": "derek_okafor",  "slack_username": "derek.okafor",  "slack_id": "U004"},
    {"name": "Elena Petrov",  "email": "elena@nexusai.com",  "slack_key": "elena_petrov",  "slack_username": "elena.petrov",  "slack_id": "U005"},
]

# Week labels (Monday-Friday of each April week)
WEEKS = [
    "April 7-11",
    "April 14-18",
    "April 21-25",
    "April 28-May 2",
]

# Initial schedule in the Google Doc (some will be invalidated by PTO)
INITIAL_SCHEDULE = [
    {"week": WEEKS[0], "assignee": "Alice Chen"},     # Alice has PTO -> needs reassignment
    {"week": WEEKS[1], "assignee": "Bob Martinez"},    # OK
    {"week": WEEKS[2], "assignee": "Carol Wu"},        # Carol has PTO -> needs reassignment
    {"week": WEEKS[3], "assignee": "Derek Okafor"},    # OK
]

# PTO events on Google Calendar
PTO_EVENTS = [
    {
        "summary": "Alice Chen - PTO",
        "email": "alice@nexusai.com",
        "start": "2026-04-06",
        "end": "2026-04-12",
    },
    {
        "summary": "Carol Wu - PTO",
        "email": "carol@nexusai.com",
        "start": "2026-04-20",
        "end": "2026-04-26",
    },
]

# Decoy calendar events.
# Bob's conference spans Sat-Mon (April 12-14), overlapping one day of his
# on-call week (April 14-18).  This is NOT PTO — it's a working conference
# and Bob confirmed in Slack he'll be reachable.  Agent should NOT remove Bob.
# Elena's dentist appointment is a single-hour event on a non-on-call day.
DECOY_EVENTS = [
    {
        "summary": "Bob Martinez - AI Conference (attending remotely Mon)",
        "email": "bob@nexusai.com",
        "start": "2026-04-12",
        "end": "2026-04-15",
    },
    {
        "summary": "Elena Petrov - Dentist",
        "email": "elena@nexusai.com",
        "start": "2026-04-22T10:00:00",
        "end": "2026-04-22T11:00:00",
    },
]

# Swap agreements in Slack #on-call-swap
SLACK_SWAP_MESSAGES = [
    {
        "sender_key": "elena_petrov",
        "text": "Hey @alice I can cover your week (April 7-11) since you're out. All good?",
        "days_ago": 3,
    },
    {
        "sender_key": "alice_chen",
        "text": "That would be amazing, thanks Elena! :pray:",
        "days_ago": 3,
    },
]

# Ambiguous swap: Derek volunteers to cover Carol's week and Carol thanks
# him, but she never confirms the actual swap — she says she'll "figure it
# out with the team."  Agent should NOT treat this as a confirmed swap.
AMBIGUOUS_SWAP_MESSAGES = [
    {
        "sender_key": "derek_okafor",
        "text": "I'm happy to take Carol's week (April 21-25) — I don't have anything that conflicts and I've covered on-call before so it's no problem on my end.",
        "days_ago": 1,
    },
    {
        "sender_key": "carol_wu",
        "text": "Thanks Derek, really appreciate you offering! I'll figure it out with the team and update the schedule.",
        "days_ago": 1,
    },
]

# Noise messages in #on-call-swap — realistic chatter that also provides
# contrast between confirmed and unconfirmed swaps.
NOISE_SWAP_MESSAGES = [
    # Cancelled swap: Bob initially offered to swap with Derek for a different
    # month, then backed out.  Agent must not treat this as active.
    {
        "sender_key": "bob_martinez",
        "text": "Hey Derek, I could take your March 31-Apr 4 week if you want. Happy to swap.",
        "days_ago": 10,
    },
    {
        "sender_key": "derek_okafor",
        "text": "That would be great, thanks Bob!",
        "days_ago": 10,
    },
    {
        "sender_key": "bob_martinez",
        "text": "Actually sorry, just realized I have a conflict that week. Ignore my offer, can't do it after all.",
        "days_ago": 9,
    },
    # Bob clarifies he's reachable during his conference
    {
        "sender_key": "bob_martinez",
        "text": "FYI I have an AI conference April 12-14 but I'll be attending remotely on Monday so I'm still good for on-call that week.",
        "days_ago": 6,
    },
    # Swap confirmation norms reminder
    {
        "sender_key": "bob_martinez",
        "text": "Reminder: if you swap on-call, make sure to actually confirm in this channel so we have a record. Just volunteering isn't enough — both people need to agree.",
        "days_ago": 5,
    },
    {
        "sender_key": "elena_petrov",
        "text": "Does anyone know where the incident runbook lives? I thought it was in the wiki but can't find it.",
        "days_ago": 4,
    },
    {
        "sender_key": "bob_martinez",
        "text": "It's in the eng-docs folder on Drive. Search for 'Incident Response Playbook'.",
        "days_ago": 4,
    },
    {
        "sender_key": "derek_okafor",
        "text": "Last month's rotation went smoothly. No pages after Wednesday which was nice.",
        "days_ago": 2,
    },
]

# EXPECTED final schedule (what the evaluator checks)
EXPECTED_SCHEDULE = [
    {"week": WEEKS[0], "assignee": "Elena Petrov"},    # Swap honored
    {"week": WEEKS[1], "assignee": "Bob Martinez"},     # Unchanged
    {"week": WEEKS[2], "assignee": "Alice Chen"},       # Fewest weeks (0), alphabetically first among eligible
    {"week": WEEKS[3], "assignee": "Derek Okafor"},     # Unchanged
]
# Why Alice for week 3:
#   After removing Alice from week 1 (PTO) and assigning Elena (swap):
#     Alice=0, Bob=1, Carol=PTO, Derek=1, Elena=1
#   Alice has fewest weeks (0) and is not on PTO week 3. She gets it.
#   Final: Alice=1, Bob=1, Derek=1, Elena=1. All <= 2. OK.


def build_schedule_doc(schedule: list[dict] | None = None) -> str:
    """Build the Google Doc content for the on-call schedule."""
    if schedule is None:
        schedule = INITIAL_SCHEDULE
    lines = [
        "On-Call Schedule \u2014 April",
        "",
        "Primary on-call rotation for April 2026.",
        "Each engineer covers one week (Monday\u2013Friday).",
        "Max 2 weeks per person; alphabetical tiebreaker for reassignments.",
        "",
        "| Week | On-Call Engineer |",
        "|------|-----------------|",
    ]
    for entry in schedule:
        lines.append(f"| {entry['week']} | {entry['assignee']} |")
    lines.append("")
    lines.append("If you need to swap, post in #on-call-swap and get confirmation from the other person.")
    return "\n".join(lines)


# Stable Google Doc ID (44-char base64-ish)
DOC_SCHEDULE_ID = "1Tr8vKmW2xYnQp4Ls7JdRcFh0BuAe6Zi9Go3Nj5Mw1Xb"
