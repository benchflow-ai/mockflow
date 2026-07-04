"""Tests for gcal-federal-register-meeting-amendments evaluator."""

from __future__ import annotations

import importlib.util
from pathlib import Path

_tests_dir = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location(
    "evaluate_gcal_federal_register",
    _verifier_dir / "evaluate.py",
)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
evaluate = _mod.evaluate

# ---------------------------------------------------------------------------
# Helpers – build the state / diff shapes the evaluator expects
# ---------------------------------------------------------------------------

def _make_event(summary, start_iso, end_iso, location="", status="confirmed"):
    return {
        "summary": summary,
        "start": {"dateTime": start_iso},
        "end": {"dateTime": end_iso},
        "location": location,
        "status": status,
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


# ---------------------------------------------------------------------------
# Scenario constants (from data/scenarios.py)
# ---------------------------------------------------------------------------

FORT_HANCOCK_SUMMARY = (
    "Gateway National Recreation Area Fort Hancock 21st Century Advisory Committee "
    "Notice of Public Meetings"
)
NPS_BOARD_SUMMARY = "Notice of Public Meeting for the National Park System Advisory Board"

# Seed events (pre-solve state)
SEED_FH_JAN = _make_event(FORT_HANCOCK_SUMMARY, "2025-01-15T14:00:00Z", "2025-01-15T19:00:00Z", "Virtual")
SEED_NPS_D1 = _make_event(NPS_BOARD_SUMMARY, "2024-03-07T17:00:00Z", "2024-03-08T01:00:00Z", "At or near Joshua Tree National Park, California")
SEED_NPS_D2 = _make_event(NPS_BOARD_SUMMARY, "2024-03-08T17:00:00Z", "2024-03-09T01:00:00Z", "At or near Joshua Tree National Park, California")

# Target events (post-solve state)
TARGET_FH_JAN = _make_event(FORT_HANCOCK_SUMMARY, "2025-02-06T14:00:00Z", "2025-02-06T17:00:00Z", "Online Conference")
TARGET_NPS_D1 = _make_event(NPS_BOARD_SUMMARY, "2024-05-01T13:00:00Z", "2024-05-01T21:00:00Z",
                            "Stuart Lee Udall Department of the Interior Building, 1849 C Street NW, Washington, DC 20240")
TARGET_NPS_D2 = _make_event(NPS_BOARD_SUMMARY, "2024-05-02T13:00:00Z", "2024-05-02T21:00:00Z",
                            "Stuart Lee Udall Department of the Interior Building, 1849 C Street NW, Washington, DC 20240")

# Trap events – must remain untouched
TRAP_FH_MAY = _make_event(FORT_HANCOCK_SUMMARY, "2025-05-08T13:00:00Z", "2025-05-08T18:00:00Z", "Virtual")
TRAP_FH_OCT = _make_event(FORT_HANCOCK_SUMMARY, "2025-10-10T13:00:00Z", "2025-10-10T18:00:00Z", "Virtual")

# SCOREABLE = 3 (3 update actions)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestPreSolve:
    """Empty action_log + empty diff + seed state => reward 0.0."""

    def test_pre_solve_reward_zero(self):
        # State still has all seed events + traps untouched
        state = _state(SEED_FH_JAN, SEED_NPS_D1, SEED_NPS_D2, TRAP_FH_MAY, TRAP_FH_OCT)
        result = evaluate(state, _empty_diff(), [])
        assert result["reward"] == 0.0
        assert result["action_count"] == 0


class TestFullScore:
    """All 3 updates done, traps untouched => reward 1.0."""

    def test_all_updates_done(self):
        state = _state(TARGET_FH_JAN, TARGET_NPS_D1, TARGET_NPS_D2, TRAP_FH_MAY, TRAP_FH_OCT)
        diff = _diff(updated=[TARGET_FH_JAN, TARGET_NPS_D1, TARGET_NPS_D2])
        result = evaluate(state, diff, ["a1", "a2", "a3"])
        assert result["reward"] == 1.0
        assert result["action_count"] == 3


class TestPartialCredit:
    """Each update independently contributes ~0.3333."""

    def test_one_update_of_three(self):
        # Only fort hancock january updated; others still seed
        state = _state(TARGET_FH_JAN, SEED_NPS_D1, SEED_NPS_D2, TRAP_FH_MAY, TRAP_FH_OCT)
        diff = _diff(updated=[TARGET_FH_JAN])
        result = evaluate(state, diff, ["a1"])
        assert round(result["reward"], 4) == round(1.0 / 3.0, 4)

    def test_two_updates_of_three(self):
        state = _state(TARGET_FH_JAN, TARGET_NPS_D1, SEED_NPS_D2, TRAP_FH_MAY, TRAP_FH_OCT)
        diff = _diff(updated=[TARGET_FH_JAN, TARGET_NPS_D1])
        result = evaluate(state, diff, ["a1", "a2"])
        assert round(result["reward"], 4) == round(2.0 / 3.0, 4)


class TestTrapPenalty:
    """Touching a trap event reduces the score; clamped at 0.0."""

    def test_trap_reduces_score(self):
        # All 3 updates done BUT trap_fort_hancock_may was deleted
        state = _state(TARGET_FH_JAN, TARGET_NPS_D1, TARGET_NPS_D2, TRAP_FH_OCT)
        diff = _diff(updated=[TARGET_FH_JAN, TARGET_NPS_D1, TARGET_NPS_D2],
                     deleted=[TRAP_FH_MAY])
        result = evaluate(state, diff, ["a1", "a2", "a3", "a4"])
        # (3 - 1) / 3 = 0.6667
        assert round(result["reward"], 4) == round(2.0 / 3.0, 4)

    def test_trap_clamps_at_zero(self):
        # No updates done, both traps touched => (0 - 2) / 3 clamped to 0
        state = _state(SEED_FH_JAN, SEED_NPS_D1, SEED_NPS_D2)
        diff = _diff(deleted=[TRAP_FH_MAY, TRAP_FH_OCT])
        result = evaluate(state, diff, ["a1", "a2"])
        assert result["reward"] == 0.0
