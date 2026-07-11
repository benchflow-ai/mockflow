"""Tests for multi-mail-cal-ietf-core-interim-cancel evaluator."""

from __future__ import annotations

import importlib.util
from pathlib import Path

_tests_dir = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location(
    "evaluate_multi_mail_cal_ietf",
    _tests_dir / "evaluate.py",
)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
evaluate = _mod.evaluate
TARGET_SUMMARY = _mod.TARGET_SUMMARY
MATCH_KEYWORDS = _mod.MATCH_KEYWORDS
DECOY_SUMMARIES = _mod.DECOY_SUMMARIES

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_event(summary, start_iso="2026-04-01T15:00:00Z", end_iso="2026-04-01T16:30:00Z",
                location="", status="confirmed", description=""):
    return {
        "summary": summary,
        "start": {"dateTime": start_iso},
        "end": {"dateTime": end_iso},
        "location": location,
        "status": status,
        "description": description,
    }


def _state(*events):
    return {"users": {"me": {"events": list(events)}}}


def _empty_diff():
    return {"users": {"me": {"events": {"added": [], "updated": [], "deleted": []}}}}


def _diff(added=None, updated=None, deleted=None):
    return {
        "users": {
            "me": {
                "events": {
                    "added": added or [],
                    "updated": updated or [],
                    "deleted": deleted or [],
                }
            }
        }
    }


# Build a target event using the actual TARGET_SUMMARY from the loaded scenario
TARGET_EVENT = _make_event(TARGET_SUMMARY.title())  # keep original casing
# Build one that matches via exact summary (lowercase match)
TARGET_EVENT_EXACT = _make_event(TARGET_SUMMARY)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestPreSolve:
    """Empty diff + target still active => reward 0.0."""

    def test_pre_solve_reward_zero(self):
        event = _make_event(TARGET_SUMMARY)
        state = _state(event)
        result = evaluate(state, _empty_diff(), [])
        assert result["reward"] == 0.0
        assert result["action_count"] == 0


class TestDeletionPath:
    """Deleting the target event => reward 1.0."""

    def test_deleted_event_full_score(self):
        event = _make_event(TARGET_SUMMARY)
        state = _state()  # event gone from final state
        diff = _diff(deleted=[event])
        result = evaluate(state, diff, ["delete_action"])
        assert result["reward"] == 1.0
        assert result["details"]["reason"] == "deleted the cancelled interim event"


class TestMarkCancelledPath:
    """Marking the event as cancelled via update => reward 1.0."""

    def test_mark_cancelled_full_score(self):
        cancelled_event = _make_event(TARGET_SUMMARY, status="cancelled")
        state = _state(cancelled_event)
        diff = _diff(updated=[cancelled_event])
        result = evaluate(state, diff, ["update_action"])
        assert result["reward"] == 1.0
        assert result["details"]["reason"] == "marked the cancelled interim event as cancelled"

    def test_cancelled_in_state_but_no_diff_action(self):
        # Event is cancelled in final state but diff has no clear cancel action
        cancelled_event = _make_event(TARGET_SUMMARY, status="cancelled")
        state = _state(cancelled_event)
        result = evaluate(state, _empty_diff(), ["some_action"])
        assert result["reward"] == 0.5
        assert "diff does not show" in result["details"]["reason"]


class TestDuplicateCreation:
    """Creating a duplicate matching event => reward 0.0."""

    def test_duplicate_creation_zero(self):
        # Event still active AND a new matching one was added
        event = _make_event(TARGET_SUMMARY)
        new_event = _make_event(TARGET_SUMMARY, start_iso="2026-04-02T15:00:00Z")
        state = _state(event, new_event)
        diff = _diff(added=[new_event])
        result = evaluate(state, diff, ["create_action"])
        # active_matches > 0, so reward stays 0
        assert result["reward"] == 0.0

    def test_added_without_active_zero(self):
        # Original removed but a new match was added => added_matches triggers 0
        new_event = _make_event(TARGET_SUMMARY, start_iso="2026-04-02T15:00:00Z")
        state = _state(new_event)
        diff = _diff(added=[new_event])
        result = evaluate(state, diff, ["create_action"])
        # active_matches > 0 (new event is active), so reward = 0
        assert result["reward"] == 0.0


class TestKeywordMatching:
    """Events matched by keyword in description also count."""

    def test_keyword_in_description_matches(self):
        # Use a keyword from MATCH_KEYWORDS in the description
        if MATCH_KEYWORDS:
            keyword = MATCH_KEYWORDS[0]
            event = _make_event("Some Other Title", description=keyword)
            state = _state()  # event removed
            diff = _diff(deleted=[event])
            result = evaluate(state, diff, ["delete_action"])
            assert result["reward"] == 1.0


class TestDecoyProtection:
    """Decoy events must not be touched — touching them incurs a penalty."""

    def test_deleting_decoy_reduces_score(self):
        if not DECOY_SUMMARIES:
            return
        target = _make_event(TARGET_SUMMARY)
        decoy = _make_event(DECOY_SUMMARIES[0])
        state = _state()  # both removed
        diff = _diff(deleted=[target, decoy])
        result = evaluate(state, diff, ["del1", "del2"])
        # 1.0 for target - 0.5 for decoy = 0.5
        assert result["reward"] == 0.5
        assert result["details"]["decoy_deleted"] == 1

    def test_deleting_two_decoys_zeros_score(self):
        if len(DECOY_SUMMARIES) < 2:
            return
        target = _make_event(TARGET_SUMMARY)
        decoy1 = _make_event(DECOY_SUMMARIES[0])
        decoy2 = _make_event(DECOY_SUMMARIES[1])
        state = _state()
        diff = _diff(deleted=[target, decoy1, decoy2])
        result = evaluate(state, diff, ["d1", "d2", "d3"])
        # 1.0 - 2*0.5 = 0.0
        assert result["reward"] == 0.0
        assert result["details"]["decoy_deleted"] == 2

    def test_cancelling_decoy_penalizes(self):
        if not DECOY_SUMMARIES:
            return
        target = _make_event(TARGET_SUMMARY)
        decoy_cancelled = _make_event(DECOY_SUMMARIES[0], status="cancelled")
        state = _state(decoy_cancelled)
        diff = _diff(deleted=[target], updated=[decoy_cancelled])
        result = evaluate(state, diff, ["del", "upd"])
        assert result["reward"] == 0.5
        assert result["details"]["decoy_cancelled"] == 1

    def test_correct_delete_no_decoy_touch(self):
        """Perfect run: delete target, leave decoys alone."""
        target = _make_event(TARGET_SUMMARY)
        state = _state()
        diff = _diff(deleted=[target])
        result = evaluate(state, diff, ["del"])
        assert result["reward"] == 1.0
        assert result["details"]["decoy_deleted"] == 0
        assert result["details"]["decoy_cancelled"] == 0
