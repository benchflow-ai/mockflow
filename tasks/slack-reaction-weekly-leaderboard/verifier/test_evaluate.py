import importlib.util
import pathlib

import pytest

# ---------------------------------------------------------------------------
# Load evaluate.py by file path so the module resolves needles.py relative
# to its own location (parents[2] fallback in _load_needles()).
# ---------------------------------------------------------------------------

_EVALUATE_PATH = pathlib.Path(__file__).resolve().parent / "evaluate.py"
_spec = importlib.util.spec_from_file_location("_leaderboard_evaluate", _EVALUATE_PATH)
evaluate_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(evaluate_mod)

evaluate = evaluate_mod.evaluate

# ---------------------------------------------------------------------------
# Constants — read from the loaded module so tests stay in sync with needles.
# ---------------------------------------------------------------------------

WINNER_USER = evaluate_mod.WINNER_USER      # "sarah"
WINNER_COUNT = evaluate_mod.WINNER_COUNT    # 22
RANK2_USER = evaluate_mod.RANK2_USER        # "priya"
RANK2_COUNT = evaluate_mod.RANK2_COUNT      # 15
RANK3_USER = evaluate_mod.RANK3_USER        # "james"
RANK3_COUNT = evaluate_mod.RANK3_COUNT      # 13

# Channel IDs used throughout the tests
GENERAL_ID = "C01GENERAL"
RANDOM_ID = "C02RANDOM"

# ---------------------------------------------------------------------------
# Helper builders
# ---------------------------------------------------------------------------

def _state(general_id=GENERAL_ID, random_id=RANDOM_ID):
    """Minimal final_state with #general and #random channels."""
    return {
        "workspaces": {
            "workspace_001": {
                "channels": [
                    {"id": general_id, "name": "general"},
                    {"id": random_id, "name": "random"},
                ]
            }
        }
    }


def _diff(general_texts=(), random_texts=()):
    """Build a diff with posted messages to #general and/or #random."""
    messages_added = []
    for text in general_texts:
        messages_added.append({"channel_id": GENERAL_ID, "text": text})
    for text in random_texts:
        messages_added.append({"channel_id": RANDOM_ID, "text": text})
    return {
        "updated": {
            "workspace_001": {
                "messages": {"added": messages_added}
            }
        }
    }


def _full_general_post():
    """Text that satisfies winner + rank2 + rank3 criteria."""
    return (
        f"Weekly reaction leaderboard:\n"
        f"1. {WINNER_USER} — {WINNER_COUNT} reactions\n"
        f"2. {RANK2_USER} — {RANK2_COUNT} reactions\n"
        f"3. {RANK3_USER} — {RANK3_COUNT} reactions"
    )


def _full_random_post():
    """Text that satisfies the #random share criterion (winner name + count)."""
    return f"Congrats to {WINNER_USER} who topped the weekly leaderboard with {WINNER_COUNT} reactions!"


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_pre_solve():
    """Empty diff and empty action log → no work done → reward == 0.0."""
    result = evaluate(_state(), {}, [])
    assert result["reward"] == 0.0
    assert result["metrics"]["posted_to_general"] is False
    assert result["metrics"]["winner_in_post"] is False
    assert result["metrics"]["rank2_in_post"] is False
    assert result["metrics"]["rank3_in_post"] is False
    assert result["metrics"]["shared_to_random"] is False


def test_full_solve():
    """All criteria met: correct leaderboard in #general + shared to #random → reward == 1.0."""
    diff = _diff(
        general_texts=[_full_general_post()],
        random_texts=[_full_random_post()],
    )
    result = evaluate(_state(), diff, [])
    assert result["reward"] == 1.0
    assert result["metrics"]["posted_to_general"] is True
    assert result["metrics"]["winner_in_post"] is True
    assert result["metrics"]["rank2_in_post"] is True
    assert result["metrics"]["rank3_in_post"] is True
    assert result["metrics"]["shared_to_random"] is True


def test_time_window_failure():
    """Agent includes tom (30 reactions, outside 7-day window) as rank-1.

    The post says 'tom 30' instead of 'sarah 22', so winner_in_post fails.
    Maximum achievable reward is 0.2 (posted) + 0.2 (rank2) + 0.1 (rank3) = 0.5 ≤ 0.7.
    """
    # Post with tom as rank-1 but correct rank-2 and rank-3
    text = (
        f"Weekly leaderboard:\n"
        f"1. tom — 30 reactions\n"
        f"2. {RANK2_USER} — {RANK2_COUNT} reactions\n"
        f"3. {RANK3_USER} — {RANK3_COUNT} reactions"
    )
    diff = _diff(general_texts=[text])
    result = evaluate(_state(), diff, [])
    assert result["metrics"]["winner_in_post"] is False
    assert result["reward"] <= 0.7


def test_self_reaction_failure():
    """Agent reports james with 17 reactions (not subtracting self-reactions).

    The post says 'james 17' instead of 'james 13', so rank3_in_post fails.
    """
    text = (
        f"Weekly leaderboard:\n"
        f"1. {WINNER_USER} — {WINNER_COUNT} reactions\n"
        f"2. {RANK2_USER} — {RANK2_COUNT} reactions\n"
        f"3. james — 17 reactions"
    )
    diff = _diff(general_texts=[text])
    result = evaluate(_state(), diff, [])
    assert result["metrics"]["rank3_in_post"] is False
    # posted + winner + rank2 = 0.2 + 0.3 + 0.2 = 0.7
    assert result["reward"] == pytest.approx(0.7)


def test_cross_channel_failure():
    """Agent only reads #general and reports sarah=12 (misses #engineering 10).

    'sarah' appears in the post but '22' does not, so winner_in_post fails.
    """
    text = (
        f"Weekly leaderboard:\n"
        f"1. {WINNER_USER} — 12 reactions\n"
        f"2. {RANK2_USER} — {RANK2_COUNT} reactions\n"
        f"3. {RANK3_USER} — {RANK3_COUNT} reactions"
    )
    diff = _diff(general_texts=[text])
    result = evaluate(_state(), diff, [])
    assert result["metrics"]["winner_in_post"] is False
    # posted + rank2 + rank3 = 0.2 + 0.2 + 0.1 = 0.5
    assert result["reward"] == pytest.approx(0.5)


def test_missing_random_post():
    """Correct #general post but no #random share → shared_to_random == False, reward ≤ 0.8."""
    diff = _diff(general_texts=[_full_general_post()])
    result = evaluate(_state(), diff, [])
    assert result["metrics"]["shared_to_random"] is False
    assert result["reward"] <= 0.8
    # posted + winner + rank2 + rank3 = 0.2 + 0.3 + 0.2 + 0.1 = 0.8
    assert result["reward"] == pytest.approx(0.8)


def test_partial_only_winner():
    """Only the winner is correctly identified; rank-2 and rank-3 are absent.

    Expected reward: posted (0.2) + winner (0.3) = 0.5.
    """
    text = f"This week's top reactor is {WINNER_USER} with {WINNER_COUNT} reactions!"
    diff = _diff(general_texts=[text])
    result = evaluate(_state(), diff, [])
    assert result["metrics"]["posted_to_general"] is True
    assert result["metrics"]["winner_in_post"] is True
    assert result["metrics"]["rank2_in_post"] is False
    assert result["metrics"]["rank3_in_post"] is False
    assert result["reward"] == pytest.approx(0.5)


def test_random_post_requires_winner_name_and_count():
    """#random post that omits the winner's name fails the shared_to_random criterion."""
    # Post to #random but omit winner name — only count is mentioned
    diff = _diff(
        general_texts=[_full_general_post()],
        random_texts=[f"Top user had {WINNER_COUNT} reactions this week!"],
    )
    result = evaluate(_state(), diff, [])
    assert result["metrics"]["shared_to_random"] is False
    # Should still get credit for #general work
    assert result["metrics"]["winner_in_post"] is True
    assert result["reward"] == pytest.approx(0.8)


def test_random_post_requires_winner_count():
    """#random post that mentions the winner's name but omits the count fails."""
    diff = _diff(
        general_texts=[_full_general_post()],
        random_texts=[f"Shoutout to {WINNER_USER} for the most reactions this week!"],
    )
    result = evaluate(_state(), diff, [])
    assert result["metrics"]["shared_to_random"] is False
    assert result["reward"] == pytest.approx(0.8)


def test_empty_general_no_random_credit():
    """A #random post alone (no #general post) earns shared_to_random (+0.2) but
    nothing for #general criteria, because posted_to_general, winner_in_post, etc.
    only look at #general messages."""
    diff = _diff(random_texts=[_full_random_post()])
    result = evaluate(_state(), diff, [])
    assert result["metrics"]["posted_to_general"] is False
    assert result["metrics"]["winner_in_post"] is False
    assert result["metrics"]["rank2_in_post"] is False
    assert result["metrics"]["rank3_in_post"] is False
    # shared_to_random is awarded independently — the evaluator gives +0.2 for a valid
    # #random post even when #general is empty.
    assert result["metrics"]["shared_to_random"] is True
    assert result["reward"] == pytest.approx(0.2)


def test_action_log_length_recorded():
    """api_calls metric equals the number of entries in action_log."""
    action_log = [{}, {}, {}]
    result = evaluate(_state(), {}, action_log)
    assert result["metrics"]["api_calls"] == 3


def test_case_insensitive_matching():
    """Evaluator lowercases all post text, so uppercase winner names still match."""
    text = (
        f"Leaderboard:\n"
        f"1. SARAH — {WINNER_COUNT}\n"
        f"2. PRIYA — {RANK2_COUNT}\n"
        f"3. JAMES — {RANK3_COUNT}"
    )
    diff = _diff(general_texts=[text])
    result = evaluate(_state(), diff, [])
    assert result["metrics"]["winner_in_post"] is True
    assert result["metrics"]["rank2_in_post"] is True
    assert result["metrics"]["rank3_in_post"] is True


def test_multiple_general_posts_combined():
    """Multiple messages to #general are combined — criteria can be split across posts."""
    diff = _diff(
        general_texts=[
            f"Winner: {WINNER_USER} with {WINNER_COUNT} reactions.",
            f"Runner-up: {RANK2_USER} ({RANK2_COUNT}), third: {RANK3_USER} ({RANK3_COUNT}).",
        ]
    )
    result = evaluate(_state(), diff, [])
    assert result["metrics"]["winner_in_post"] is True
    assert result["metrics"]["rank2_in_post"] is True
    assert result["metrics"]["rank3_in_post"] is True
    assert result["reward"] == pytest.approx(0.8)


def test_reward_capped_at_one():
    """Reward never exceeds 1.0 even if somehow all criteria are double-counted."""
    diff = _diff(
        general_texts=[_full_general_post(), _full_general_post()],
        random_texts=[_full_random_post(), _full_random_post()],
    )
    result = evaluate(_state(), diff, [])
    assert result["reward"] <= 1.0
    assert result["reward"] == pytest.approx(1.0)


def test_marcus_near_miss_not_in_top3():
    """Agent incorrectly includes marcus (12) as rank-3 instead of james (13).

    marcus (12 reactions after self-exclusion) is close to james (13) but should
    not appear in the top 3. Reporting marcus=12 in rank-3 means rank3_in_post fails.
    """
    text = (
        f"Weekly leaderboard:\n"
        f"1. {WINNER_USER} — {WINNER_COUNT} reactions\n"
        f"2. {RANK2_USER} — {RANK2_COUNT} reactions\n"
        f"3. marcus — 12 reactions"
    )
    diff = _diff(general_texts=[text])
    result = evaluate(_state(), diff, [])
    assert result["metrics"]["rank3_in_post"] is False
    # posted + winner + rank2 = 0.2 + 0.3 + 0.2 = 0.7
    assert result["reward"] == pytest.approx(0.7)


def test_boundary_time_window_rachel():
    """Agent includes rachel (18 reactions, 8 days ago) as rank-2.

    rachel's message is just outside the 7-day window. Including her yields
    a wrong rank-2 (rachel=18 instead of priya=15) and wrong rank-3.
    """
    text = (
        f"Weekly leaderboard:\n"
        f"1. {WINNER_USER} — {WINNER_COUNT} reactions\n"
        f"2. rachel — 18 reactions\n"
        f"3. {RANK2_USER} — {RANK2_COUNT} reactions"
    )
    diff = _diff(general_texts=[text])
    result = evaluate(_state(), diff, [])
    # rank2 check: looks for priya + 15. "priya" and "15" are in the text
    # but so is "rachel" and "18". The evaluator checks priya + 15 in the
    # combined text — priya appears at rank 3 with 15, so rank2_in_post passes.
    # But rank3 check looks for james + 13, which is absent → fails.
    assert result["metrics"]["rank2_in_post"] is True
    assert result["metrics"]["rank3_in_post"] is False
    assert result["reward"] == pytest.approx(0.7)


def test_self_reaction_skip_inflates_marcus():
    """Agent skips self-reaction exclusion, giving marcus 15 (ties with priya).

    Without self-exclusion: marcus gets 9 (#engineering) + 6 (#frontend) = 15.
    This ties with priya and may displace james from rank-3. The leaderboard
    becomes ambiguous and the agent reports wrong counts.
    """
    text = (
        f"Weekly leaderboard:\n"
        f"1. {WINNER_USER} — {WINNER_COUNT} reactions\n"
        f"2. {RANK2_USER} — {RANK2_COUNT} reactions\n"
        f"3. marcus — 15 reactions"
    )
    diff = _diff(general_texts=[text])
    result = evaluate(_state(), diff, [])
    assert result["metrics"]["rank3_in_post"] is False
    assert result["reward"] == pytest.approx(0.7)
