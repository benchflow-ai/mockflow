"""Unit tests for rebalance-on-call-rotation evaluator."""

import importlib.util
import os

_spec = importlib.util.spec_from_file_location(
    "evaluate", os.path.join(os.path.dirname(__file__), "evaluate.py")
)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
evaluate = _mod.evaluate

WEEKS = _mod.WEEKS
EXPECTED_SCHEDULE = _mod.EXPECTED_SCHEDULE
ENGINEERS = _mod.ENGINEERS


def _doc_state(schedule: list[dict] | None = None) -> dict:
    """Build a minimal docs_state with the given schedule."""
    if schedule is None:
        schedule = EXPECTED_SCHEDULE
    lines = [
        "On-Call Schedule \u2014 April\n",
        "\n",
        "Primary on-call rotation for April 2026.\n",
        "\n",
        "| Week | On-Call Engineer |\n",
        "|------|------------------|\n",
    ]
    for entry in schedule:
        lines.append(f"| {entry['week']} | {entry['assignee']} |\n")
    return {
        "documents": {
            "doc1": {
                "body": {
                    "content": [
                        {
                            "paragraph": {
                                "elements": [
                                    {"textRun": {"content": "".join(lines)}}
                                ]
                            }
                        }
                    ]
                }
            }
        }
    }


def _slack_state(posted: bool = False, schedule: list[dict] | None = None) -> dict:
    """Build a minimal slack_state.

    If *posted* is True, generates a schedule summary message.
    Uses *schedule* if provided; otherwise uses EXPECTED_SCHEDULE.
    """
    messages = []
    if posted:
        sched = schedule or EXPECTED_SCHEDULE
        text = "Updated on-call schedule for April:\n" + "\n".join(
            f"- {e['week']}: {e['assignee']}" for e in sched
        )
        messages.append({"text": text, "user": "agent"})
    return {
        "channels": {
            "C001": {
                "name": "on-call-swap",
                "messages": messages,
            }
        }
    }


def _empty_diff():
    return {}


def _action_log(entries=None):
    return entries or []


# ── Pre-solve invariant ──────────────────────────────────────────────────────

def test_no_action():
    """No action taken -> exactly 0.0."""
    initial_schedule = [
        {"week": WEEKS[0], "assignee": "Alice Chen"},
        {"week": WEEKS[1], "assignee": "Bob Martinez"},
        {"week": WEEKS[2], "assignee": "Carol Wu"},
        {"week": WEEKS[3], "assignee": "Derek Okafor"},
    ]
    initial_state = _doc_state(initial_schedule)
    result = evaluate(initial_state, _empty_diff(), _slack_state(), _empty_diff(), [])
    assert result["reward"] == 0.0


# ── Perfect score ─────────────────────────────────────────────────────────────

def test_perfect_score():
    """All correct + posted to Slack -> 1.0."""
    result = evaluate(
        _doc_state(),
        {"documents": {"doc1": "changed"}},
        _slack_state(posted=True),
        {"channels": {"C001": "changed"}},
        [{"action": "update_doc"}],
    )
    assert result["reward"] == 1.0


# ── Partial scores ────────────────────────────────────────────────────────────

def test_swap_honored_but_week3_wrong():
    """Week 1 correct (swap) but week 3 assigned to wrong person.

    Slack post contains the (wrong) schedule but is still a valid summary,
    so slack_posted should be True — correctness is scored by week checks.
    """
    schedule = [
        {"week": WEEKS[0], "assignee": "Elena Petrov"},
        {"week": WEEKS[1], "assignee": "Bob Martinez"},
        {"week": WEEKS[2], "assignee": "Derek Okafor"},  # Wrong — should be Alice
        {"week": WEEKS[3], "assignee": "Derek Okafor"},  # Also wrong — Derek gets 2
    ]
    result = evaluate(
        _doc_state(schedule),
        {"documents": {"doc1": "changed"}},
        _slack_state(posted=True, schedule=schedule),
        {"channels": {"C001": "changed"}},
        [{"action": "update_doc"}],
    )
    # Week 1 (+0.25) + Week 2 (+0.05) + Week 4 (Derek=Derek, +0.10)
    # + no_pto_assigned (+0.10) + ambig_rejected: Derek IS on week3, FAIL
    # + doc_modified (+0.05) + schedule_complete (+0.05) + slack (+0.10) = 0.70
    assert result["reward"] == 0.70


def test_correct_schedule_no_slack_post():
    """Schedule correct but not posted to Slack -> 0.90.

    0.25+0.05+0.25+0.10+0.10+0.05+0.05+0.05 = 0.90 (missing slack 0.10)
    """
    result = evaluate(
        _doc_state(),
        {"documents": {"doc1": "changed"}},
        _slack_state(posted=False),
        {"channels": {}},
        [{"action": "update_doc"}],
    )
    assert result["reward"] == 0.90


def test_only_week1_and_week2_correct():
    """Only weeks 1 and 2 correct, weeks 3 and 4 wrong."""
    schedule = [
        {"week": WEEKS[0], "assignee": "Elena Petrov"},
        {"week": WEEKS[1], "assignee": "Bob Martinez"},
        {"week": WEEKS[2], "assignee": "Elena Petrov"},  # Wrong — Elena now has 2
        {"week": WEEKS[3], "assignee": "Carol Wu"},       # Wrong — Carol on PTO week3 but assigned week4
    ]
    result = evaluate(
        _doc_state(schedule),
        {"documents": {"doc1": "changed"}},
        _slack_state(posted=False),
        {},
        [{"action": "update_doc"}],
    )
    # Week 1 (+0.25) + Week 2 (+0.05) + no_pto_assigned: Carol assigned week4,
    # Carol's PTO is week3, so week4 is fine. OK (+0.10)
    # + ambig_rejected: Elena on week3 (not Derek), OK (+0.05)
    # + doc_modified (+0.05) + schedule_complete (+0.05) = 0.55
    assert result["reward"] == 0.55


def test_derek_on_week3_penalized():
    """Derek assigned to week 3 (ambiguous swap honored) -> ambig_rejected fails."""
    schedule = [
        {"week": WEEKS[0], "assignee": "Elena Petrov"},
        {"week": WEEKS[1], "assignee": "Bob Martinez"},
        {"week": WEEKS[2], "assignee": "Derek Okafor"},  # Ambiguous swap honored — bad
        {"week": WEEKS[3], "assignee": "Alice Chen"},
    ]
    result = evaluate(
        _doc_state(schedule),
        {"documents": {"doc1": "changed"}},
        _slack_state(posted=False),
        {},
        [{"action": "update_doc"}],
    )
    assert result["ambig_swap_rejected"] == 0
    # Week 1 (+0.25) + Week 2 (+0.05) + no_pto (+0.10) + doc_modified (+0.05)
    # + schedule_complete (+0.05) = 0.50
    # ambig_rejected FAIL, week3 wrong, week4 wrong
    assert result["reward"] == 0.50


# ── PTO conflict ─────────────────────────────────────────────────────────────

def test_pto_conflict():
    """Assigning Alice to week 1 (her PTO week) -> no_pto_assigned fails."""
    schedule = [
        {"week": WEEKS[0], "assignee": "Alice Chen"},     # Alice on PTO this week!
        {"week": WEEKS[1], "assignee": "Bob Martinez"},
        {"week": WEEKS[2], "assignee": "Elena Petrov"},
        {"week": WEEKS[3], "assignee": "Derek Okafor"},
    ]
    result = evaluate(
        _doc_state(schedule),
        {"documents": {"doc1": "changed"}},
        _slack_state(posted=False),
        {},
        [{"action": "update_doc"}],
    )
    assert result["no_pto_assigned"] == 0
    # Week 2 (+0.05) + Week 4 (+0.10) + ambig_rejected (Elena on week3, OK) (+0.05)
    # + doc_modified: week3 changed (Carol -> Elena) (+0.05)
    # + schedule_complete (+0.05) = 0.30
    assert result["reward"] == 0.30


# ── Edge case: empty doc ─────────────────────────────────────────────────────

def test_empty_doc_with_action():
    """Doc is empty but action was taken -> low score."""
    result = evaluate(
        {"documents": {}},
        {"documents": {"doc1": "changed"}},
        _slack_state(posted=False),
        {},
        [{"action": "something"}],
    )
    assert result["reward"] == 0.0
