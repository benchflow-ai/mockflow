"""Tests for gcal-fosdem-2023-amendments evaluator."""

from __future__ import annotations

import importlib.util
from pathlib import Path

_tests_dir = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location(
    "evaluate_gcal_fosdem",
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

# 5 deletes
DELETE_LLVM = _make_event(
    "CANCELLED Eliminating ManagedStatic and llvm_shutdown",
    "2023-02-04T14:50:00Z", "2023-02-04T15:00:00Z", "AW1.120",
)
DELETE_GRUB = _make_event(
    "CANCELLED GRUB - Project Status Update",
    "2023-02-05T08:10:00Z", "2023-02-05T08:35:00Z", "K.4.201",
)
DELETE_CSI = _make_event(
    "CANCELLED Container Storage Interface Addons",
    "2023-02-04T15:30:00Z", "2023-02-04T16:05:00Z", "D.sds (online)",
)
DELETE_CEPH = _make_event(
    "CANCELLED Monitoring and Centralized Logging in Ceph",
    "2023-02-04T16:05:00Z", "2023-02-04T16:40:00Z", "D.sds (online)",
)
DELETE_SUPPORT = _make_event(
    "CANCELLED First class support in OSS",
    "2023-02-04T16:45:00Z", "2023-02-04T17:25:00Z", "H.2214",
)

ALL_DELETES = [DELETE_LLVM, DELETE_GRUB, DELETE_CSI, DELETE_CEPH, DELETE_SUPPORT]

# 1 create
CREATE_LLVM_MEETUPS = _make_event(
    "AMENDMENT Interactive discussion on organizing LLVM socials/meetups",
    "2023-02-04T14:50:00Z", "2023-02-04T15:00:00Z", "AW1.120",
)

# 2 traps
TRAP_KEDA = _make_event(
    "AMENDMENT Autoscaling with KEDA - Object Store Case Study",
    "2023-02-04T15:30:00Z", "2023-02-04T15:55:00Z", "H.2214",
)
TRAP_CEPH_RGW = _make_event(
    "Ceph RGW: S3 Select & Pushdown",
    "2023-02-04T14:30:00Z", "2023-02-04T15:05:00Z", "D.sds (online)",
)
TRAP_NETWORK_PERF = _make_event(
    "CANCELLED Network Performance in the Linux Kernel",
    "2023-02-04T13:00:00Z", "2023-02-04T13:50:00Z", "H.1308 (Rolin)",
)

ALL_TRAPS = [TRAP_KEDA, TRAP_CEPH_RGW, TRAP_NETWORK_PERF]

# SCOREABLE = 6 (5 deletes + 1 create)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestPreSolve:
    def test_pre_solve_reward_zero(self):
        # All seed events still present, traps untouched, nothing in diff
        state = _state(*ALL_DELETES, *ALL_TRAPS)
        result = evaluate(state, _empty_diff(), [])
        assert result["reward"] == 0.0
        assert result["action_count"] == 0


class TestFullScore:
    def test_all_actions_done(self):
        # All deletes removed, create present, traps untouched
        state = _state(CREATE_LLVM_MEETUPS, *ALL_TRAPS)
        diff = _diff(added=[CREATE_LLVM_MEETUPS], deleted=ALL_DELETES)
        result = evaluate(state, diff, ["a"] * 6)
        assert result["reward"] == 1.0
        assert result["action_count"] == 6


class TestPartialCredit:
    def test_three_of_six_actions(self):
        # Delete 3 of the 5 seed events, no create yet
        remaining_deletes = [DELETE_CEPH, DELETE_SUPPORT]
        done_deletes = [DELETE_LLVM, DELETE_GRUB, DELETE_CSI]
        state = _state(*remaining_deletes, *ALL_TRAPS)
        diff = _diff(deleted=done_deletes)
        result = evaluate(state, diff, ["a"] * 3)
        assert round(result["reward"], 4) == round(3.0 / 6.0, 4)

    def test_single_delete(self):
        # Only one delete done
        remaining = [d for d in ALL_DELETES if d is not DELETE_LLVM]
        state = _state(*remaining, *ALL_TRAPS)
        diff = _diff(deleted=[DELETE_LLVM])
        result = evaluate(state, diff, ["a"])
        assert round(result["reward"], 4) == round(1.0 / 6.0, 4)


class TestTrapPenalty:
    def test_touching_keda_trap(self):
        # All 6 actions done correctly, but KEDA trap was touched
        state = _state(CREATE_LLVM_MEETUPS, TRAP_CEPH_RGW, TRAP_NETWORK_PERF)
        diff = _diff(added=[CREATE_LLVM_MEETUPS], deleted=[*ALL_DELETES, TRAP_KEDA])
        result = evaluate(state, diff, ["a"] * 7)
        # (6 - 1) / 6 = 0.8333
        assert round(result["reward"], 4) == round(5.0 / 6.0, 4)

    def test_touching_all_traps(self):
        # All 6 actions done, all 3 traps touched
        state = _state(CREATE_LLVM_MEETUPS)
        diff = _diff(added=[CREATE_LLVM_MEETUPS], deleted=[*ALL_DELETES, *ALL_TRAPS])
        result = evaluate(state, diff, ["a"] * 9)
        # (6 - 3) / 6 = 0.5
        assert round(result["reward"], 4) == round(3.0 / 6.0, 4)

    def test_trap_only_no_actions_clamps_zero(self):
        # No correct actions, but traps touched => (0 - 3)/6 clamped to 0
        state = _state(*ALL_DELETES)  # traps removed, seeds still there
        diff = _diff(deleted=ALL_TRAPS)
        result = evaluate(state, diff, ["a"] * 3)
        assert result["reward"] == 0.0

    def test_touching_cancelled_name_trap(self):
        """Agent deletes the CANCELLED-titled trap that is NOT on the amendments list."""
        state = _state(CREATE_LLVM_MEETUPS, TRAP_KEDA, TRAP_CEPH_RGW)
        diff = _diff(added=[CREATE_LLVM_MEETUPS], deleted=[*ALL_DELETES, TRAP_NETWORK_PERF])
        result = evaluate(state, diff, ["a"] * 7)
        # (6 - 1) / 6 = 0.8333
        assert round(result["reward"], 4) == round(5.0 / 6.0, 4)
