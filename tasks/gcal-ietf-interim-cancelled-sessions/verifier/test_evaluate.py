"""Tests for gcal-ietf-interim-cancelled-sessions evaluator."""

from __future__ import annotations

import importlib.util
from pathlib import Path

_tests_dir = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location(
    "evaluate_gcal_ietf_interim",
    _tests_dir / "evaluate.py",
)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
evaluate = _mod.evaluate

# ---------------------------------------------------------------------------
# Helpers
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
# Event constants from data/scenarios.py
# ---------------------------------------------------------------------------

# 4 deletes
DELETE_CBOR = _make_event(
    "cbor - Concise Binary Object Representation Maintenance and Extensions",
    "2024-10-02T14:00:00Z", "2024-10-02T15:00:00Z",
)
DELETE_MOQ = _make_event(
    "moq - Media Over QUIC (We are not ready to build an agenda at this time.)",
    "2025-01-08T17:00:00Z", "2025-01-08T18:00:00Z",
)
DELETE_IDR = _make_event(
    "idr - Inter-Domain Routing (Interim canceled due to lack of presentations.)",
    "2024-06-24T14:00:00Z", "2024-06-24T17:00:00Z",
)
DELETE_CORE = _make_event(
    "core - Constrained RESTful Environments",
    "2026-02-25T15:00:00Z", "2026-02-25T16:30:00Z",
)

ALL_DELETES = [DELETE_CBOR, DELETE_MOQ, DELETE_IDR, DELETE_CORE]

# 4 traps (confirmed sessions that must not be touched)
TRAP_CBOR = _make_event(
    "cbor - Concise Binary Object Representation Maintenance and Extensions",
    "2024-10-16T14:00:00Z", "2024-10-16T15:00:00Z",
)
TRAP_MOQ = _make_event(
    "moq - Media Over QUIC",
    "2025-01-22T17:00:00Z", "2025-01-22T18:00:00Z",
)
TRAP_IDR = _make_event(
    "idr - Inter-Domain Routing (https://trac.ietf.org/trac/idr/wiki/)",
    "2024-06-03T14:00:00Z", "2024-06-03T15:30:00Z",
)
TRAP_CORE = _make_event(
    "core - Constrained RESTful Environments",
    "2026-02-11T15:00:00Z", "2026-02-11T16:30:00Z",
)

ALL_TRAPS = [TRAP_CBOR, TRAP_MOQ, TRAP_IDR, TRAP_CORE]

# SCOREABLE = 4 (4 delete actions)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestPreSolve:
    def test_pre_solve_reward_zero(self):
        state = _state(*ALL_DELETES, *ALL_TRAPS)
        result = evaluate(state, _empty_diff(), [])
        assert result["reward"] == 0.0
        assert result["action_count"] == 0


class TestFullScore:
    def test_all_four_deletes(self):
        state = _state(*ALL_TRAPS)
        diff = _diff(deleted=ALL_DELETES)
        result = evaluate(state, diff, ["a"] * 4)
        assert result["reward"] == 1.0
        assert result["action_count"] == 4


class TestPartialCredit:
    def test_two_of_four_deletes(self):
        remaining = [DELETE_IDR, DELETE_CORE]
        done = [DELETE_CBOR, DELETE_MOQ]
        state = _state(*remaining, *ALL_TRAPS)
        diff = _diff(deleted=done)
        result = evaluate(state, diff, ["a"] * 2)
        assert result["reward"] == 0.5

    def test_one_of_four_deletes(self):
        remaining = [DELETE_MOQ, DELETE_IDR, DELETE_CORE]
        done = [DELETE_CBOR]
        state = _state(*remaining, *ALL_TRAPS)
        diff = _diff(deleted=done)
        result = evaluate(state, diff, ["a"])
        assert result["reward"] == 0.25


class TestTrapPenalty:
    def test_deleting_confirmed_session_penalty(self):
        # All 4 correct deletes + 1 trap deleted
        state = _state(TRAP_MOQ, TRAP_IDR, TRAP_CORE)  # TRAP_CBOR gone
        diff = _diff(deleted=[*ALL_DELETES, TRAP_CBOR])
        result = evaluate(state, diff, ["a"] * 5)
        # (4 - 1) / 4 = 0.75
        assert result["reward"] == 0.75

    def test_trap_only_clamps_zero(self):
        # No correct deletes, only trap deleted
        state = _state(*ALL_DELETES, TRAP_MOQ, TRAP_IDR, TRAP_CORE)
        diff = _diff(deleted=[TRAP_CBOR])
        result = evaluate(state, diff, ["a"])
        # (0 - 1) / 4 clamped to 0
        assert result["reward"] == 0.0
