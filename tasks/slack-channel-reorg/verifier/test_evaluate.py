"""Tests for slack-channel-reorg evaluator."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Import evaluate.py by absolute path to avoid TASKS_DIR / package issues
# ---------------------------------------------------------------------------

_EVALUATE_PATH = Path(__file__).resolve().parent / "evaluate.py"
_spec = importlib.util.spec_from_file_location("evaluate", _EVALUATE_PATH)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
evaluate = _mod.evaluate

# ---------------------------------------------------------------------------
# Constants mirrored from evaluate.py
# ---------------------------------------------------------------------------

TOTAL_CORRECT = 11   # matched members
TOTAL_UNMATCHED = 6  # unmatched members

# All 11 matched usernames and their expected destination channels
EXPECTED_MATCHES: dict[str, set[str]] = {
    "platform-team-hiring":  {"james.wright", "alex.johnson", "diana.fox"},
    "aiml-team-hiring":      {"kevin.liu", "ryan.kim", "noah.patel"},
    "commerce-team-hiring":  {"emma.davis", "sophie.martin"},
    "infra-team-hiring":     {"priya.sharma"},
    "product-team-hiring":   {"sarah.chen", "lisa.park"},
}

UNMATCHED_USERNAMES = [
    "chris.taylor", "mike.torres", "mia.garcia", "david.lee",
    "natalie.brown", "tom.wilson",
]

SOURCE_CHANNELS = ["metaverse-general", "metaverse-engineering", "metaverse-product"]
STEALTH_CHANNEL_NAME = "metaverse-stealth"


# ---------------------------------------------------------------------------
# State / diff builders
# ---------------------------------------------------------------------------

def _uid(name: str) -> str:
    """Stable fake user-id from username."""
    return f"U_{name.replace('.', '_').upper()}"


def _cid(name: str) -> str:
    """Stable fake channel-id from channel name."""
    return f"C_{name.replace('-', '_').upper()}"


def _dm_cid(name: str) -> str:
    """Stable fake DM channel-id for a given username."""
    return f"DM_{name.replace('.', '_').upper()}"


def _make_user(name: str) -> dict:
    return {"id": _uid(name), "name": name}


def _make_channel(name: str, is_private: bool = False, is_im: bool = False) -> dict:
    ch = {"id": _cid(name), "name": name, "is_private": is_private}
    if is_im:
        ch["is_im"] = True
    return ch


def _make_dm_channel(name: str) -> dict:
    """DM channel for a given user (is_im=True)."""
    return {"id": _dm_cid(name), "name": f"dm_{name}", "is_im": True}


def _membership(channel_name: str, username: str) -> dict:
    return {"channel_id": _cid(channel_name), "user_id": _uid(username)}


def _dm_membership(username: str) -> dict:
    """Membership entry linking a user to their DM channel."""
    return {"channel_id": _dm_cid(username), "user_id": _uid(username)}


def _action_members_call(channel_name: str) -> dict:
    """Fake action_log entry for a conversations.members API call."""
    return {"path": f"/api/conversations.members?channel={_cid(channel_name)}"}


def _dm_message(username: str) -> dict:
    """A new DM message added to a user's DM channel."""
    return {"channel_id": _dm_cid(username), "text": "Hi, you have been matched!"}


# ---------------------------------------------------------------------------
# Full workspace state builder
# ---------------------------------------------------------------------------

_ALL_MATCHED = sorted({u for members in EXPECTED_MATCHES.values() for u in members})
_ALL_USERS = _ALL_MATCHED + UNMATCHED_USERNAMES
_ALL_CHANNEL_NAMES = (
    list(EXPECTED_MATCHES.keys())
    + SOURCE_CHANNELS
    + [STEALTH_CHANNEL_NAME]
)


def _make_base_state(
    place_in_hiring: dict[str, list[str]] | None = None,
    place_unmatched_in: dict[str, list[str]] | None = None,
    include_stealth_channel: bool = True,
    extra_memberships: list[dict] | None = None,
) -> dict:
    """Build a minimal ws_state with all standard channels and users.

    place_in_hiring: mapping channel_name -> list of usernames to add as members.
    place_unmatched_in: same but for unmatched users (for false-positive testing).
    """
    users = [_make_user(u) for u in _ALL_USERS]

    channels = [_make_channel(ch) for ch in EXPECTED_MATCHES.keys()]
    channels += [_make_channel(ch) for ch in SOURCE_CHANNELS]
    if include_stealth_channel:
        channels.append(_make_channel(STEALTH_CHANNEL_NAME, is_private=True))
    # Add DM channels for every user
    channels += [_make_dm_channel(u) for u in _ALL_USERS]

    channel_members: list[dict] = []

    # Source channel memberships (all matched + unmatched in metaverse-general)
    for ch in SOURCE_CHANNELS:
        for u in _ALL_MATCHED + UNMATCHED_USERNAMES:
            channel_members.append(_membership(ch, u))

    # Stealth channel – only diana.fox and noah.patel
    if include_stealth_channel:
        for u in ["diana.fox", "noah.patel"]:
            channel_members.append(_membership(STEALTH_CHANNEL_NAME, u))

    # Hiring channel placements requested by the test
    if place_in_hiring:
        for ch_name, users_list in place_in_hiring.items():
            for u in users_list:
                channel_members.append(_membership(ch_name, u))

    if place_unmatched_in:
        for ch_name, users_list in place_unmatched_in.items():
            for u in users_list:
                channel_members.append(_membership(ch_name, u))

    # DM channel memberships
    for u in _ALL_USERS:
        channel_members.append(_dm_membership(u))

    if extra_memberships:
        channel_members.extend(extra_memberships)

    ws_state = {
        "channels": channels,
        "users": users,
        "channel_members": channel_members,
        "messages": [],
    }
    return {"workspaces": {"workspace_001": ws_state}}


def _make_diff(dm_usernames: list[str] | None = None) -> dict:
    """Build a minimal diff with optional DM messages added."""
    added_messages = [_dm_message(u) for u in (dm_usernames or [])]
    return {
        "updated": {
            "workspace_001": {
                "messages": {"added": added_messages},
            }
        }
    }


def _make_action_log(queried_channels: list[str]) -> list[dict]:
    """Build a fake action_log with conversations.members calls for given channel names."""
    return [_action_members_call(ch) for ch in queried_channels]


# ---------------------------------------------------------------------------
# 1. Pre-solve invariant
# ---------------------------------------------------------------------------

class TestPreSolveInvariant:
    """Empty diff + empty action_log should yield reward == 0.0."""

    def test_empty_diff_empty_log(self):
        state = _make_base_state()
        result = evaluate(state, _make_diff(), [])
        assert result["reward"] == 0.0

    def test_no_placements_no_dms_no_queries(self):
        state = _make_base_state(place_in_hiring=None)
        result = evaluate(state, _make_diff(), [])
        assert result["done"] is True
        assert result["reward"] == 0.0
        assert result["metrics"]["correct_placements"] == 0
        assert result["metrics"]["placement_score"] == 0.0
        # fp_score and dedup_score are only added when correct_placements > 0
        assert result["metrics"]["false_positive_score"] == round(0.10 * 6 / 6, 4)
        assert result["metrics"]["deduplication_score"] == 0.0


# ---------------------------------------------------------------------------
# 2. Full-correct: reward == 1.0
# ---------------------------------------------------------------------------

class TestFullCorrect:
    """All placements correct + all source channels queried + stealth accessed/placed + all DMs sent."""

    def _full_placement(self) -> dict[str, list[str]]:
        return {ch: list(members) for ch, members in EXPECTED_MATCHES.items()}

    def test_perfect_score(self):
        placements = self._full_placement()
        state = _make_base_state(place_in_hiring=placements)

        # DMs to all 11 matched + 6 unmatched
        dm_targets = _ALL_MATCHED + UNMATCHED_USERNAMES
        diff = _make_diff(dm_usernames=dm_targets)

        # All 3 source channels + stealth channel queried
        action_log = _make_action_log(SOURCE_CHANNELS + [STEALTH_CHANNEL_NAME])

        result = evaluate(state, diff, action_log)
        assert result["reward"] == 1.0

    def test_perfect_score_metrics(self):
        placements = self._full_placement()
        state = _make_base_state(place_in_hiring=placements)
        dm_targets = _ALL_MATCHED + UNMATCHED_USERNAMES
        diff = _make_diff(dm_usernames=dm_targets)
        action_log = _make_action_log(SOURCE_CHANNELS + [STEALTH_CHANNEL_NAME])

        result = evaluate(state, diff, action_log)
        m = result["metrics"]

        assert m["correct_placements"] == TOTAL_CORRECT
        assert m["placement_score"] == 0.25
        assert m["unmatched_clean"] == TOTAL_UNMATCHED
        assert m["false_positive_score"] == 0.10
        assert m["deduplication_score"] == 0.20
        assert m["stealth_channel_accessed"] is True
        assert m["stealth_access_score"] == 0.15
        assert m["dm_matched_sent"] == TOTAL_CORRECT
        assert m["dm_matched_score"] == 0.20
        assert m["dm_unmatched_sent"] == TOTAL_UNMATCHED
        assert m["dm_unmatched_score"] == 0.10


# ---------------------------------------------------------------------------
# 3. Partial scoring
# ---------------------------------------------------------------------------

class TestPartialScoring:
    """Subset of correct placements yields proportional score."""

    def test_half_placements(self):
        # Place only platform (3) + aiml (3) = 6 of 11 correct
        placements = {
            "platform-team-hiring": list(EXPECTED_MATCHES["platform-team-hiring"]),
            "aiml-team-hiring":     list(EXPECTED_MATCHES["aiml-team-hiring"]),
        }
        state = _make_base_state(place_in_hiring=placements)
        result = evaluate(state, _make_diff(), [])
        expected_placement = round(0.25 * 6 / 11, 4)
        assert result["metrics"]["placement_score"] == expected_placement
        assert result["metrics"]["correct_placements"] == 6

    def test_one_correct_placement(self):
        placements = {"infra-team-hiring": ["priya.sharma"]}
        state = _make_base_state(place_in_hiring=placements)
        result = evaluate(state, _make_diff(), [])
        assert result["metrics"]["correct_placements"] == 1
        assert result["metrics"]["placement_score"] == round(0.25 * 1 / 11, 4)

    def test_partial_dedup_two_of_three_queried(self):
        placements = {ch: list(m) for ch, m in EXPECTED_MATCHES.items()}
        state = _make_base_state(place_in_hiring=placements)
        # Only query 2 of 3 source channels
        action_log = _make_action_log(SOURCE_CHANNELS[:2])
        result = evaluate(state, _make_diff(), action_log)
        assert result["metrics"]["deduplication_score"] == round(0.20 * 2 / 3, 4)

    def test_partial_dm_matched_some_sent(self):
        placements = {ch: list(m) for ch, m in EXPECTED_MATCHES.items()}
        state = _make_base_state(place_in_hiring=placements)
        # Only send DMs to 5 of the 11 matched
        dm_targets = _ALL_MATCHED[:5]
        diff = _make_diff(dm_usernames=dm_targets)
        result = evaluate(state, diff, [])
        assert result["metrics"]["dm_matched_sent"] == 5
        assert result["metrics"]["dm_matched_score"] == round(0.20 * 5 / 11, 4)

    def test_partial_dm_unmatched_some_sent(self):
        placements = {ch: list(m) for ch, m in EXPECTED_MATCHES.items()}
        state = _make_base_state(place_in_hiring=placements)
        # Send DMs to only 3 of 6 unmatched
        dm_targets = UNMATCHED_USERNAMES[:3]
        diff = _make_diff(dm_usernames=dm_targets)
        result = evaluate(state, diff, [])
        assert result["metrics"]["dm_unmatched_sent"] == 3
        assert result["metrics"]["dm_unmatched_score"] == round(0.10 * 3 / 6, 4)

    def test_reward_accumulates_proportionally(self):
        # 6 correct placements, 2 source channels queried, DMs to 6 matched, 0 unmatched DMs
        placements = {
            "platform-team-hiring": list(EXPECTED_MATCHES["platform-team-hiring"]),  # 3
            "aiml-team-hiring":     list(EXPECTED_MATCHES["aiml-team-hiring"]),       # 3
        }
        state = _make_base_state(place_in_hiring=placements)
        dm_targets = list(EXPECTED_MATCHES["platform-team-hiring"]) + list(EXPECTED_MATCHES["aiml-team-hiring"])
        diff = _make_diff(dm_usernames=dm_targets)
        action_log = _make_action_log(SOURCE_CHANNELS[:2])

        result = evaluate(state, diff, action_log)
        m = result["metrics"]

        placement = round(0.25 * 6 / 11, 4)
        fp = round(0.10 * 6 / 6, 4)   # no false positives
        dedup = round(0.20 * 2 / 3, 4)
        dm_matched = round(0.20 * 6 / 11, 4)
        dm_unmatched = 0.0
        stealth = 0.0  # not queried

        expected = round(placement + fp + dedup + dm_matched + dm_unmatched + stealth, 2)
        assert result["reward"] == expected


# ---------------------------------------------------------------------------
# 4. False positives
# ---------------------------------------------------------------------------

class TestFalsePositives:
    """Unmatched members incorrectly placed into hiring channels should reduce fp_score."""

    def test_one_false_positive_reduces_fp_score(self):
        # Correct placements + chris.taylor (unmatched) added to platform-team-hiring
        placements = {ch: list(m) for ch, m in EXPECTED_MATCHES.items()}
        fp_placement = {"platform-team-hiring": ["chris.taylor"]}
        state = _make_base_state(
            place_in_hiring=placements,
            place_unmatched_in=fp_placement,
        )
        result = evaluate(state, _make_diff(), [])
        # 5 of 6 unmatched are clean
        assert result["metrics"]["unmatched_clean"] == 5
        assert result["metrics"]["false_positive_score"] == round(0.10 * 5 / 6, 4)

    def test_all_unmatched_placed_fp_score_zero(self):
        # Put every unmatched person into a hiring channel
        placements = {ch: list(m) for ch, m in EXPECTED_MATCHES.items()}
        fp_placements = {
            "platform-team-hiring": UNMATCHED_USERNAMES[:2],
            "aiml-team-hiring": UNMATCHED_USERNAMES[2:4],
            "infra-team-hiring": UNMATCHED_USERNAMES[4:6],
        }
        state = _make_base_state(
            place_in_hiring=placements,
            place_unmatched_in=fp_placements,
        )
        result = evaluate(state, _make_diff(), [])
        assert result["metrics"]["unmatched_clean"] == 0
        assert result["metrics"]["false_positive_score"] == 0.0

    def test_fp_score_not_counted_when_no_correct_placements(self):
        # No correct placements but unmatched are also not placed -> fp_score not added to reward
        state = _make_base_state()
        result = evaluate(state, _make_diff(), [])
        # fp_score metric is computed but NOT added to reward (gate: correct_placements > 0)
        assert result["metrics"]["correct_placements"] == 0
        assert result["reward"] == 0.0

    def test_fp_details_accuracy(self):
        placements = {"infra-team-hiring": ["priya.sharma"]}
        fp_placements = {"infra-team-hiring": ["natalie.brown"]}
        state = _make_base_state(
            place_in_hiring=placements,
            place_unmatched_in=fp_placements,
        )
        result = evaluate(state, _make_diff(), [])
        details = result["metrics"]["false_positive_details"]
        assert details["natalie.brown"] is False  # incorrectly placed
        # The others should all be clean
        for u in UNMATCHED_USERNAMES:
            if u != "natalie.brown":
                assert details[u] is True


# ---------------------------------------------------------------------------
# 5. Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    """Stealth and channel-name edge cases."""

    def test_stealth_queried_but_members_not_placed_gives_zero_stealth_score(self):
        # Place all non-stealth matched members, but NOT diana.fox / noah.patel
        placements = {
            "platform-team-hiring": ["james.wright", "alex.johnson"],  # missing diana.fox
            "aiml-team-hiring":     ["kevin.liu", "ryan.kim"],          # missing noah.patel
            "commerce-team-hiring": list(EXPECTED_MATCHES["commerce-team-hiring"]),
            "infra-team-hiring":    list(EXPECTED_MATCHES["infra-team-hiring"]),
            "product-team-hiring":  list(EXPECTED_MATCHES["product-team-hiring"]),
        }
        state = _make_base_state(place_in_hiring=placements)
        action_log = _make_action_log(SOURCE_CHANNELS + [STEALTH_CHANNEL_NAME])

        result = evaluate(state, _make_diff(), action_log)
        assert result["metrics"]["stealth_channel_accessed"] is True
        assert result["metrics"]["stealth_access_score"] == 0.0

    def test_stealth_members_placed_but_channel_not_queried_gives_zero_stealth_score(self):
        placements = {ch: list(m) for ch, m in EXPECTED_MATCHES.items()}
        state = _make_base_state(place_in_hiring=placements)
        # Action log has source channels but NOT stealth
        action_log = _make_action_log(SOURCE_CHANNELS)

        result = evaluate(state, _make_diff(), action_log)
        assert result["metrics"]["stealth_channel_accessed"] is False
        assert result["metrics"]["stealth_access_score"] == 0.0

    def test_stealth_channel_absent_from_state_gives_zero_stealth_score(self):
        placements = {ch: list(m) for ch, m in EXPECTED_MATCHES.items()}
        state = _make_base_state(place_in_hiring=placements, include_stealth_channel=False)
        # Even if action_log includes the stealth ID, channel not in state
        action_log = _make_action_log(SOURCE_CHANNELS + [STEALTH_CHANNEL_NAME])

        result = evaluate(state, _make_diff(), action_log)
        assert result["metrics"]["stealth_channel_accessed"] is False
        assert result["metrics"]["stealth_access_score"] == 0.0

    def test_wrong_channel_name_means_no_placements_counted(self):
        # Put members in a channel with a typo — evaluator won't find it
        wrong_placement_state = _make_base_state()
        ws = wrong_placement_state["workspaces"]["workspace_001"]
        # Add a misspelled channel + put platform members in it
        wrong_ch_name = "platform-team-hirring"
        ws["channels"].append({"id": _cid(wrong_ch_name), "name": wrong_ch_name})
        for u in EXPECTED_MATCHES["platform-team-hiring"]:
            ws["channel_members"].append({"channel_id": _cid(wrong_ch_name), "user_id": _uid(u)})

        result = evaluate(wrong_placement_state, _make_diff(), [])
        assert result["metrics"]["correct_placements"] == 0

    def test_source_channel_queried_but_no_correct_placements_dedup_not_rewarded(self):
        # All 3 source channels queried, but zero correct placements
        state = _make_base_state()
        action_log = _make_action_log(SOURCE_CHANNELS)
        result = evaluate(state, _make_diff(), action_log)
        # dedup_score metric is computed but NOT added to reward (gate: correct_placements > 0)
        assert result["metrics"]["deduplication_score"] == round(0.20 * 3 / 3, 4)
        assert result["reward"] == 0.0

    def test_dedup_channel_id_must_match_exactly(self):
        # Only one source channel queried
        placements = {ch: list(m) for ch, m in EXPECTED_MATCHES.items()}
        state = _make_base_state(place_in_hiring=placements)
        action_log = _make_action_log([SOURCE_CHANNELS[0]])

        result = evaluate(state, _make_diff(), action_log)
        assert result["metrics"]["deduplication_score"] == round(0.20 * 1 / 3, 4)

    def test_dm_not_counted_when_user_has_no_dm_channel(self):
        # Build state where one matched user has no DM channel
        placements = {"infra-team-hiring": ["priya.sharma"]}
        state = _make_base_state(place_in_hiring=placements)
        # Remove priya.sharma's DM channel and membership
        ws = state["workspaces"]["workspace_001"]
        priya_dm_id = _dm_cid("priya.sharma")
        ws["channels"] = [c for c in ws["channels"] if c["id"] != priya_dm_id]
        ws["channel_members"] = [
            m for m in ws["channel_members"]
            if not (m["channel_id"] == priya_dm_id)
        ]
        # diff says a message was sent to that DM (but channel is gone)
        diff = _make_diff(dm_usernames=["priya.sharma"])

        result = evaluate(state, diff, [])
        assert result["metrics"]["dm_matched_details"]["priya.sharma"] is False

    def test_full_score_components_sum_to_one(self):
        """Sanity check: individual score components sum exactly to 1.0 on a perfect run."""
        placements = {ch: list(m) for ch, m in EXPECTED_MATCHES.items()}
        state = _make_base_state(place_in_hiring=placements)
        dm_targets = _ALL_MATCHED + UNMATCHED_USERNAMES
        diff = _make_diff(dm_usernames=dm_targets)
        action_log = _make_action_log(SOURCE_CHANNELS + [STEALTH_CHANNEL_NAME])

        result = evaluate(state, diff, action_log)
        m = result["metrics"]

        total = (
            m["placement_score"]
            + m["false_positive_score"]
            + m["deduplication_score"]
            + m["stealth_access_score"]
            + m["dm_matched_score"]
            + m["dm_unmatched_score"]
        )
        assert round(total, 2) == 1.0
