"""Tests for slack-extract-reaction-leaderboard evaluate.py.

Calls evaluate(final_state, diff, action_log) directly via importlib.
"""

import importlib.util
import pathlib
import sys

import pytest

# ---------------------------------------------------------------------------
# Load evaluate.py by absolute path so tests work regardless of cwd / install
# ---------------------------------------------------------------------------

_TASK_DIR  = pathlib.Path(__file__).resolve().parents[1]   # .../slack-extract-reaction-leaderboard
_EVAL_PATH = _TASK_DIR / "verifier" / "evaluate.py"

_spec = importlib.util.spec_from_file_location("_leaderboard_evaluate", _EVAL_PATH)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

evaluate = _mod.evaluate

# Pull the already-resolved needle constants from the loaded evaluator so our
# tests stay in sync if the needles file ever changes.
WINNER_SNIPPET = _mod.WINNER_SNIPPET   # first 25 chars of WINNER_TEXT, lowercased
RANK2_SNIPPET  = _mod.RANK2_SNIPPET
RANK3_SNIPPET  = _mod.RANK3_SNIPPET
WINNER_COUNT   = _mod.WINNER_COUNT     # 24
RANK2_COUNT    = _mod.RANK2_COUNT      # 19
RANK3_COUNT    = _mod.RANK3_COUNT      # 16
DISTRACTOR_SNIPPET = _mod.DISTRACTOR_SNIPPET

# ---------------------------------------------------------------------------
# Helpers to build fake state / diff / action_log
# ---------------------------------------------------------------------------

RANDOM_ID  = "C_RANDOM"
GENERAL_ID = "C_GENERAL"
OTHER_ID   = "C_OTHER"

# Message IDs for the winning (rank-1) message
WINNER_MSG_TS = "1700000000.000001"


def _make_state() -> dict:
    """Minimal final_state with workspaces containing #random and #general."""
    return {
        "workspaces": {
            "W1": {
                "channels": [
                    {"id": RANDOM_ID,  "name": "random"},
                    {"id": GENERAL_ID, "name": "general"},
                    {"id": OTHER_ID,   "name": "other"},
                ],
                "messages": [],
            }
        }
    }


def _make_diff(channel_id: str, text: str) -> dict:
    """Diff that adds a single message to the given channel."""
    return {
        "updated": {
            "W1": {
                "messages": {
                    "added": [
                        {"channel_id": channel_id, "text": text, "ts": "1800000001.000001"}
                    ]
                }
            }
        }
    }


def _empty_diff() -> dict:
    return {"updated": {}}


def _trophy_action(channel_id: str) -> dict:
    return {
        "method": "POST",
        "path": "/api/reactions.add",
        "request_body": {"channel": channel_id, "name": "trophy", "timestamp": WINNER_MSG_TS},
    }


def _full_leaderboard_text() -> str:
    """Construct a post that satisfies all three rank checks in correct order."""
    return (
        f"{WINNER_SNIPPET} — reactions: {WINNER_COUNT} | "
        f"{RANK2_SNIPPET} — reactions: {RANK2_COUNT} | "
        f"{RANK3_SNIPPET} — reactions: {RANK3_COUNT}"
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestPreSolve:
    """test_pre_solve: empty diff + empty action_log → reward == 0.0"""

    def test_pre_solve(self):
        result = evaluate(_make_state(), _empty_diff(), [])
        assert result["reward"] == pytest.approx(0.0)
        assert result["done"] is True
        m = result["metrics"]
        assert m["posted_to_random"] is False
        assert m["rank1_found"] is False
        assert m["rank2_found"] is False
        assert m["rank3_found"] is False
        assert m["trophy_added"] is False
        assert m["distractor_present"] is False
        assert m["api_calls"] == 0


class TestFullSolve:
    """test_full_solve: all criteria met → reward == 1.0"""

    def test_full_solve(self):
        diff = _make_diff(RANDOM_ID, _full_leaderboard_text())
        action_log = [_trophy_action(GENERAL_ID)]
        result = evaluate(_make_state(), diff, action_log)
        assert result["reward"] == 1.0
        m = result["metrics"]
        assert m["posted_to_random"] is True
        assert m["rank1_found"] is True
        assert m["rank2_found"] is True
        assert m["rank3_found"] is True
        assert m["trophy_added"] is True
        assert m["distractor_present"] is False


class TestPostedToRandomOnly:
    """test_posted_to_random_only: post to #random with no rank snippets/counts → reward == 0.05"""

    def test_posted_to_random_only(self):
        diff = _make_diff(RANDOM_ID, "Here is the leaderboard (details omitted).")
        result = evaluate(_make_state(), diff, [])
        assert result["reward"] == pytest.approx(0.05)
        m = result["metrics"]
        assert m["posted_to_random"] is True
        assert m["rank1_found"] is False
        assert m["rank2_found"] is False
        assert m["rank3_found"] is False
        assert m["trophy_added"] is False
        assert m["distractor_present"] is False


class TestRank1Found:
    """test_rank1_found: post contains rank-1 snippet + count → reward includes +0.30"""

    def test_rank1_found(self):
        text = f"{WINNER_SNIPPET} had {WINNER_COUNT} reactions"
        diff = _make_diff(RANDOM_ID, text)
        result = evaluate(_make_state(), diff, [])
        # posted_to_random (+0.05) + rank1_found (+0.30)
        assert result["reward"] == pytest.approx(0.35)
        assert result["metrics"]["rank1_found"] is True
        assert result["metrics"]["rank2_found"] is False
        assert result["metrics"]["rank3_found"] is False

    def test_rank1_snippet_without_count_not_awarded(self):
        """Snippet alone, without the count, must NOT award rank1 points."""
        text = f"{WINNER_SNIPPET} — lots of reactions"
        diff = _make_diff(RANDOM_ID, text)
        result = evaluate(_make_state(), diff, [])
        assert result["metrics"]["rank1_found"] is False

    def test_rank1_count_without_snippet_not_awarded(self):
        """Count alone, without the snippet, must NOT award rank1 points."""
        text = f"The top post got {WINNER_COUNT} reactions"
        diff = _make_diff(RANDOM_ID, text)
        result = evaluate(_make_state(), diff, [])
        assert result["metrics"]["rank1_found"] is False


class TestRank2Found:
    """test_rank2_found: post contains rank-2 snippet + count after rank-1 → reward includes +0.25"""

    def test_rank2_found(self):
        # rank2 requires rank1 to be present and rank2 positioned after rank1
        text = f"{WINNER_SNIPPET} had {WINNER_COUNT} reactions | {RANK2_SNIPPET} had {RANK2_COUNT} reactions"
        diff = _make_diff(RANDOM_ID, text)
        result = evaluate(_make_state(), diff, [])
        # posted_to_random (+0.05) + rank1_found (+0.30) + rank2_found (+0.25)
        assert result["reward"] == pytest.approx(0.60)
        assert result["metrics"]["rank2_found"] is True

    def test_rank2_snippet_without_count_not_awarded(self):
        text = f"{WINNER_SNIPPET} {WINNER_COUNT} | {RANK2_SNIPPET} — some reactions"
        diff = _make_diff(RANDOM_ID, text)
        result = evaluate(_make_state(), diff, [])
        assert result["metrics"]["rank2_found"] is False

    def test_rank2_without_rank1_not_awarded(self):
        """rank2 requires rank1 to be present first."""
        text = f"{RANK2_SNIPPET} had {RANK2_COUNT} reactions"
        diff = _make_diff(RANDOM_ID, text)
        result = evaluate(_make_state(), diff, [])
        assert result["metrics"]["rank2_found"] is False

    def test_rank2_before_rank1_not_awarded(self):
        """rank2 appearing before rank1 in the text does not count."""
        text = f"{RANK2_SNIPPET} had {RANK2_COUNT} reactions | {WINNER_SNIPPET} had {WINNER_COUNT} reactions"
        diff = _make_diff(RANDOM_ID, text)
        result = evaluate(_make_state(), diff, [])
        assert result["metrics"]["rank1_found"] is True
        assert result["metrics"]["rank2_found"] is False


class TestRank3Found:
    """test_rank3_found: post contains rank-3 snippet + count after rank-2 → reward includes +0.20"""

    def test_rank3_found(self):
        diff = _make_diff(RANDOM_ID, _full_leaderboard_text())
        result = evaluate(_make_state(), diff, [])
        assert result["metrics"]["rank3_found"] is True

    def test_rank3_snippet_without_count_not_awarded(self):
        text = (
            f"{WINNER_SNIPPET} {WINNER_COUNT} | "
            f"{RANK2_SNIPPET} {RANK2_COUNT} | "
            f"{RANK3_SNIPPET} — a few reactions"
        )
        diff = _make_diff(RANDOM_ID, text)
        result = evaluate(_make_state(), diff, [])
        assert result["metrics"]["rank3_found"] is False

    def test_rank3_without_rank2_not_awarded(self):
        """rank3 requires rank2 to be present and ordered."""
        text = f"{WINNER_SNIPPET} {WINNER_COUNT} | {RANK3_SNIPPET} {RANK3_COUNT}"
        diff = _make_diff(RANDOM_ID, text)
        result = evaluate(_make_state(), diff, [])
        assert result["metrics"]["rank3_found"] is False

    def test_rank3_before_rank2_not_awarded(self):
        """rank3 appearing before rank2 does not count — rank2 still counts (it's after rank1)."""
        text = (
            f"{WINNER_SNIPPET} {WINNER_COUNT} | "
            f"{RANK3_SNIPPET} {RANK3_COUNT} | "
            f"{RANK2_SNIPPET} {RANK2_COUNT}"
        )
        diff = _make_diff(RANDOM_ID, text)
        result = evaluate(_make_state(), diff, [])
        assert result["metrics"]["rank1_found"] is True
        assert result["metrics"]["rank2_found"] is True   # rank2 is after rank1
        assert result["metrics"]["rank3_found"] is False   # rank3 is before rank2


class TestOrdering:
    """test_ordering: snippets must appear in rank order for rank2/rank3 to count."""

    def test_correct_ordering(self):
        text = _full_leaderboard_text()
        diff = _make_diff(RANDOM_ID, text)
        result = evaluate(_make_state(), diff, [])
        assert result["metrics"]["rank1_found"] is True
        assert result["metrics"]["rank2_found"] is True
        assert result["metrics"]["rank3_found"] is True

    def test_reversed_ordering(self):
        """Rank-3 first, rank-1 last → only rank1 counts (it has no ordering dep)."""
        text = (
            f"{RANK3_SNIPPET} — reactions: {RANK3_COUNT} | "
            f"{RANK2_SNIPPET} — reactions: {RANK2_COUNT} | "
            f"{WINNER_SNIPPET} — reactions: {WINNER_COUNT}"
        )
        diff = _make_diff(RANDOM_ID, text)
        result = evaluate(_make_state(), diff, [])
        assert result["metrics"]["rank1_found"] is True
        assert result["metrics"]["rank2_found"] is False
        assert result["metrics"]["rank3_found"] is False


class TestDistractorPenalty:
    """test_distractor: including cross-channel distractor triggers -0.10 penalty."""

    def test_distractor_present_penalty(self):
        text = (
            f"{_full_leaderboard_text()} | "
            f"{DISTRACTOR_SNIPPET} — 30 reactions"
        )
        diff = _make_diff(RANDOM_ID, text)
        action_log = [_trophy_action(GENERAL_ID)]
        result = evaluate(_make_state(), diff, action_log)
        assert result["metrics"]["distractor_present"] is True
        # 0.05 + 0.30 + 0.25 + 0.20 + 0.20 - 0.10 = 0.90
        assert result["reward"] == pytest.approx(0.90)

    def test_distractor_absent_no_penalty(self):
        diff = _make_diff(RANDOM_ID, _full_leaderboard_text())
        action_log = [_trophy_action(GENERAL_ID)]
        result = evaluate(_make_state(), diff, action_log)
        assert result["metrics"]["distractor_present"] is False
        assert result["reward"] == pytest.approx(1.0)

    def test_distractor_no_post_no_penalty(self):
        """No post means distractor cannot be present (nothing to check)."""
        result = evaluate(_make_state(), _empty_diff(), [])
        assert result["metrics"]["distractor_present"] is False


class TestTrophyAdded:
    """test_trophy_added: reactions.add with trophy on #general → reward includes +0.20"""

    def test_trophy_added_alone(self):
        """Trophy with no post → only +0.20."""
        result = evaluate(_make_state(), _empty_diff(), [_trophy_action(GENERAL_ID)])
        assert result["reward"] == pytest.approx(0.20)
        assert result["metrics"]["trophy_added"] is True
        assert result["metrics"]["posted_to_random"] is False

    def test_trophy_added_with_post(self):
        """Trophy + post to #random with no rank content → 0.05 + 0.20 = 0.25."""
        diff = _make_diff(RANDOM_ID, "Here is the summary.")
        result = evaluate(_make_state(), diff, [_trophy_action(GENERAL_ID)])
        assert result["reward"] == pytest.approx(0.25)
        assert result["metrics"]["trophy_added"] is True

    def test_trophy_wrong_emoji_not_awarded(self):
        action = {
            "method": "POST",
            "path": "/api/reactions.add",
            "request_body": {"channel": GENERAL_ID, "name": "tada", "timestamp": WINNER_MSG_TS},
        }
        result = evaluate(_make_state(), _empty_diff(), [action])
        assert result["metrics"]["trophy_added"] is False
        assert result["reward"] == pytest.approx(0.0)

    def test_trophy_get_method_not_counted(self):
        """reactions.add via GET (unusual) must not count."""
        action = {
            "method": "GET",
            "path": "/api/reactions.add",
            "request_body": {"channel": GENERAL_ID, "name": "trophy", "timestamp": WINNER_MSG_TS},
        }
        result = evaluate(_make_state(), _empty_diff(), [action])
        assert result["metrics"]["trophy_added"] is False


class TestTrophyWrongChannel:
    """test_trophy_wrong_channel: reactions.add with trophy on wrong channel → NOT awarded."""

    def test_trophy_on_random_not_awarded(self):
        action = {
            "method": "POST",
            "path": "/api/reactions.add",
            "request_body": {"channel": RANDOM_ID, "name": "trophy", "timestamp": WINNER_MSG_TS},
        }
        result = evaluate(_make_state(), _empty_diff(), [action])
        assert result["metrics"]["trophy_added"] is False

    def test_trophy_on_other_channel_not_awarded(self):
        action = {
            "method": "POST",
            "path": "/api/reactions.add",
            "request_body": {"channel": OTHER_ID, "name": "trophy", "timestamp": WINNER_MSG_TS},
        }
        result = evaluate(_make_state(), _empty_diff(), [action])
        assert result["metrics"]["trophy_added"] is False

    def test_trophy_on_unknown_channel_id_not_awarded(self):
        action = {
            "method": "POST",
            "path": "/api/reactions.add",
            "request_body": {"channel": "C_BOGUS", "name": "trophy", "timestamp": WINNER_MSG_TS},
        }
        result = evaluate(_make_state(), _empty_diff(), [action])
        assert result["metrics"]["trophy_added"] is False


class TestWrongChannelPost:
    """test_wrong_channel_post: post to a channel other than #random → posted_to_random == False."""

    def test_post_to_general_not_random(self):
        diff = _make_diff(GENERAL_ID, _full_leaderboard_text())
        result = evaluate(_make_state(), diff, [])
        assert result["metrics"]["posted_to_random"] is False
        # rank* checks also fail because all_text is empty (no posts to #random)
        assert result["metrics"]["rank1_found"] is False
        assert result["metrics"]["rank2_found"] is False
        assert result["metrics"]["rank3_found"] is False
        assert result["reward"] == pytest.approx(0.0)

    def test_post_to_other_channel_not_random(self):
        diff = _make_diff(OTHER_ID, _full_leaderboard_text())
        result = evaluate(_make_state(), diff, [])
        assert result["metrics"]["posted_to_random"] is False
        assert result["reward"] == pytest.approx(0.0)

    def test_post_to_both_channels_counts_random(self):
        """If the agent posts to both #general and #random, #random should still register."""
        diff = {
            "updated": {
                "W1": {
                    "messages": {
                        "added": [
                            {"channel_id": GENERAL_ID, "text": "posted to general", "ts": "1800000001.000001"},
                            {"channel_id": RANDOM_ID,  "text": "posted to random",  "ts": "1800000002.000001"},
                        ]
                    }
                }
            }
        }
        result = evaluate(_make_state(), diff, [])
        assert result["metrics"]["posted_to_random"] is True
        # posted_to_random (+0.05) only
        assert result["reward"] == pytest.approx(0.05)


class TestNearThresholdDecoyNotPenalized:
    """test_near_threshold_decoy_not_penalized.

    The decoy messages (14 and 13 reactions) must NOT appear in the top-3,
    but the evaluator has no penalty for over-inclusion of in-channel decoys.
    Including their text in the post does not reduce the score.
    """

    DECOY_A_SNIPPET = "Quick reminder: please update"
    DECOY_B_SNIPPET = "Just published the v2 design"

    def test_decoy_text_in_post_no_penalty(self):
        """Post that mentions decoys alongside all three real ranks still scores full marks."""
        text = (
            f"{WINNER_SNIPPET} — {WINNER_COUNT} reactions | "
            f"{RANK2_SNIPPET} — {RANK2_COUNT} reactions | "
            f"{RANK3_SNIPPET} — {RANK3_COUNT} reactions | "
            f"{self.DECOY_A_SNIPPET} — 14 reactions | "
            f"{self.DECOY_B_SNIPPET} — 13 reactions"
        )
        diff = _make_diff(RANDOM_ID, text)
        action_log = [_trophy_action(GENERAL_ID)]
        result = evaluate(_make_state(), diff, action_log)
        assert result["reward"] == pytest.approx(1.0)

    def test_decoy_only_in_post_does_not_score_ranks(self):
        """A post that only mentions decoys scores only posted_to_random."""
        text = f"{self.DECOY_A_SNIPPET} — 14 reactions | {self.DECOY_B_SNIPPET} — 13 reactions"
        diff = _make_diff(RANDOM_ID, text)
        result = evaluate(_make_state(), diff, [])
        # 0.05 only
        assert result["reward"] == pytest.approx(0.05)
        assert result["metrics"]["rank1_found"] is False
        assert result["metrics"]["rank2_found"] is False
        assert result["metrics"]["rank3_found"] is False

    def test_decoy_counts_not_confused_with_rank_counts(self):
        """Decoy counts (14, 13) must never equal any rank count."""
        assert WINNER_COUNT != 14
        assert RANK2_COUNT  != 14
        assert RANK3_COUNT  != 14
        assert WINNER_COUNT != 13
        assert RANK2_COUNT  != 13
        assert RANK3_COUNT  != 13


class TestUniqueUserCountingTrap:
    """Verify that the expected counts are total reactions, not unique users.

    The winner message has users appearing on multiple emoji types (e.g., priya
    reacts with tada, rocket, AND heart). Total reactions = 24, but unique
    users = 12. An agent that counts unique users instead of total reactions
    would report the wrong number and fail the count check.
    """

    def test_unique_user_count_does_not_match(self):
        """If an agent reports 12 (unique users) instead of 24, rank1 should fail."""
        text = f"{WINNER_SNIPPET} had 12 reactions"
        diff = _make_diff(RANDOM_ID, text)
        result = evaluate(_make_state(), diff, [])
        assert result["metrics"]["rank1_found"] is False

    def test_correct_total_reaction_count_passes(self):
        """Reporting 24 (total reactions) passes."""
        text = f"{WINNER_SNIPPET} had {WINNER_COUNT} reactions"
        diff = _make_diff(RANDOM_ID, text)
        result = evaluate(_make_state(), diff, [])
        assert result["metrics"]["rank1_found"] is True


class TestBotReactionCountingTrap:
    """Verify that agents must exclude bot reactions from their counts.

    A bot user ("nexusbot") reacts to the top-3 messages.  Including bot
    reactions inflates the naive totals to 26/21/18 (vs correct 24/19/16).
    The evaluator only accepts the human-only counts.
    """

    def test_bot_inflated_rank1_count_fails(self):
        """Naive count including bot (26) must NOT pass rank1 check."""
        text = f"{WINNER_SNIPPET} had 26 reactions"
        diff = _make_diff(RANDOM_ID, text)
        result = evaluate(_make_state(), diff, [])
        assert result["metrics"]["rank1_found"] is False

    def test_bot_inflated_rank2_count_fails(self):
        """Naive count including bot (21) must NOT pass rank2 check."""
        text = (
            f"{WINNER_SNIPPET} had {WINNER_COUNT} reactions | "
            f"{RANK2_SNIPPET} had 21 reactions"
        )
        diff = _make_diff(RANDOM_ID, text)
        result = evaluate(_make_state(), diff, [])
        assert result["metrics"]["rank1_found"] is True
        assert result["metrics"]["rank2_found"] is False

    def test_bot_inflated_rank3_count_fails(self):
        """Naive count including bot (18) must NOT pass rank3 check."""
        text = (
            f"{WINNER_SNIPPET} had {WINNER_COUNT} reactions | "
            f"{RANK2_SNIPPET} had {RANK2_COUNT} reactions | "
            f"{RANK3_SNIPPET} had 18 reactions"
        )
        diff = _make_diff(RANDOM_ID, text)
        result = evaluate(_make_state(), diff, [])
        assert result["metrics"]["rank1_found"] is True
        assert result["metrics"]["rank2_found"] is True
        assert result["metrics"]["rank3_found"] is False


class TestApiCallsMetric:
    """Verify api_calls metric reflects action_log length."""

    def test_api_calls_zero(self):
        result = evaluate(_make_state(), _empty_diff(), [])
        assert result["metrics"]["api_calls"] == 0

    def test_api_calls_counted(self):
        action_log = [
            _trophy_action(GENERAL_ID),
            {"method": "GET", "path": "/api/conversations.list", "request_body": {}},
            {"method": "GET", "path": "/api/reactions.get", "request_body": {}},
        ]
        result = evaluate(_make_state(), _empty_diff(), action_log)
        assert result["metrics"]["api_calls"] == 3


class TestAdditiveScoring:
    """Verify individual partial scores are additive and do not exceed 1.0."""

    def test_rank1_and_rank2_additive(self):
        text = (
            f"{WINNER_SNIPPET} {WINNER_COUNT} | "
            f"{RANK2_SNIPPET} {RANK2_COUNT}"
        )
        diff = _make_diff(RANDOM_ID, text)
        result = evaluate(_make_state(), diff, [])
        # 0.05 + 0.30 + 0.25 = 0.60
        assert result["reward"] == pytest.approx(0.60)

    def test_all_ranks_no_trophy(self):
        diff = _make_diff(RANDOM_ID, _full_leaderboard_text())
        result = evaluate(_make_state(), diff, [])
        # 0.05 + 0.30 + 0.25 + 0.20 = 0.80
        assert result["reward"] == pytest.approx(0.80)

    def test_reward_capped_at_1(self):
        """Reward must never exceed 1.0 even if scoring logic were to over-count."""
        diff = _make_diff(RANDOM_ID, _full_leaderboard_text())
        action_log = [_trophy_action(GENERAL_ID)]
        result = evaluate(_make_state(), diff, action_log)
        assert result["reward"] <= 1.0


class TestMissingChannels:
    """Edge cases when channels are absent from final_state."""

    def test_no_random_channel_in_state(self):
        state = {
            "workspaces": {
                "W1": {
                    "channels": [
                        {"id": GENERAL_ID, "name": "general"},
                    ],
                    "messages": [],
                }
            }
        }
        diff = _make_diff(RANDOM_ID, _full_leaderboard_text())
        action_log = [_trophy_action(GENERAL_ID)]
        result = evaluate(state, diff, action_log)
        # #random not found → posts list is empty → no rank points
        assert result["metrics"]["posted_to_random"] is False
        assert result["metrics"]["rank1_found"] is False
        # Trophy can still be awarded if #general exists
        assert result["metrics"]["trophy_added"] is True

    def test_no_general_channel_in_state(self):
        state = {
            "workspaces": {
                "W1": {
                    "channels": [
                        {"id": RANDOM_ID, "name": "random"},
                    ],
                    "messages": [],
                }
            }
        }
        diff = _make_diff(RANDOM_ID, _full_leaderboard_text())
        action_log = [_trophy_action(GENERAL_ID)]
        result = evaluate(state, diff, action_log)
        # Trophy requires #general to resolve; without it trophy is False
        assert result["metrics"]["trophy_added"] is False
        assert result["metrics"]["posted_to_random"] is True

    def test_empty_workspaces(self):
        state = {"workspaces": {}}
        result = evaluate(state, _empty_diff(), [])
        assert result["reward"] == pytest.approx(0.0)


class TestRewardFloor:
    """Reward must never go below 0.0 even with penalties."""

    def test_distractor_only_post_floors_at_zero(self):
        """A post containing only the distractor snippet should not go negative."""
        text = f"{DISTRACTOR_SNIPPET} — 30 reactions"
        diff = _make_diff(RANDOM_ID, text)
        result = evaluate(_make_state(), diff, [])
        # 0.05 (posted) - 0.10 (distractor) = -0.05, floored to 0.0
        assert result["reward"] == pytest.approx(0.0)
