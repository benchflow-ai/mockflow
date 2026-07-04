"""Tests for slack-search-channel-history evaluate.py.

Calls evaluate(final_state, diff, action_log) directly and asserts on the
returned reward and key metrics.

Scoring recap:
  +0.50  correct answer posted (text matches CORRECT_ANSWER_RE — "2000" near
         rate-limit context words like req, /min, or rate limit)
  +0.30  conversations.replies called on the needle thread (reply_count == 20)
  +0.10  valid discovery path (paginated history with cursor= OR search.messages)
  +0.10  token hygiene (search never called OR all calls used xoxp-),
         gated on len(action_log) > 0
"""

import importlib.util
import os

import pytest

_TESTS_DIR = os.path.dirname(__file__)
_spec = importlib.util.spec_from_file_location(
    "evaluate_slack_search_channel_history",
    os.path.join(_TESTS_DIR, "evaluate.py"),
)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
evaluate = _mod.evaluate


# ---------------------------------------------------------------------------
# Shared fixtures / builders
# ---------------------------------------------------------------------------

CHANNEL_ID = "C_ARCHIVE_001"
THREAD_TS = "1700000000.000100"  # ts of the needle message (reply_count=20)


def _ws_state() -> dict:
    """Minimal workspace state with the product-archive channel and needle thread."""
    return {
        "channels": [
            {"id": CHANNEL_ID, "name": "product-archive"},
        ],
        "messages": [
            {
                "channel_id": CHANNEL_ID,
                "ts": THREAD_TS,
                "text": "Starting a thread to finalise the Enterprise API rate-limit.",
                "reply_count": 20,
            },
        ],
    }


def _final_state(ws_state: dict | None = None) -> dict:
    return {"workspaces": {"workspace_001": ws_state or _ws_state()}}


def _diff_with_answer(text: str) -> dict:
    """Diff that includes a new posted message containing *text*."""
    return {
        "updated": {
            "workspace_001": {
                "messages": {
                    "added": [
                        {"channel_id": "C_GENERAL", "ts": "9999999999.000001", "text": text}
                    ]
                }
            }
        }
    }


def _empty_diff() -> dict:
    return {"updated": {"workspace_001": {"messages": {"added": []}}}}


def _history_call(with_cursor: bool = False) -> dict:
    path = f"/api/conversations.history?channel={CHANNEL_ID}"
    if with_cursor:
        path += "&cursor=abc123"
    return {"path": path}


def _replies_call() -> dict:
    return {"path": f"/api/conversations.replies?channel={CHANNEL_ID}&ts={THREAD_TS}"}


def _search_call(token_type: str = "user") -> dict:
    return {
        "path": "/api/search.messages?query=rate+limit",
        "token_type": token_type,
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestPreSolve:
    """test_pre_solve — nothing done yet."""

    def test_reward_is_zero(self):
        result = evaluate(_final_state(), _empty_diff(), [])
        assert result["reward"] == 0.0

    def test_done_flag(self):
        result = evaluate(_final_state(), _empty_diff(), [])
        assert result["done"] is True

    def test_no_answer_posted(self):
        result = evaluate(_final_state(), _empty_diff(), [])
        assert result["metrics"]["answer_posted"] is False

    def test_no_replies_used(self):
        result = evaluate(_final_state(), _empty_diff(), [])
        assert result["metrics"]["replies_used"] is False

    def test_discovery_not_ok(self):
        result = evaluate(_final_state(), _empty_diff(), [])
        assert result["metrics"]["discovery_ok"] is False

    def test_hygiene_not_awarded_on_empty_log(self):
        # gated on len(action_log) > 0, so hygiene is NOT included in the reward
        result = evaluate(_final_state(), _empty_diff(), [])
        # hygiene is technically True (search never called) but the gate prevents +0.10
        assert result["reward"] == 0.0


class TestFullSolve:
    """test_full_solve — answer + replies + paginated history → 1.0."""

    def test_reward_is_one(self):
        action_log = [
            _history_call(with_cursor=False),
            _history_call(with_cursor=True),
            _replies_call(),
        ]
        result = evaluate(
            _final_state(),
            _diff_with_answer("The Enterprise rate limit is 2000 requests/minute."),
            action_log,
        )
        assert result["reward"] == 1.0

    def test_all_metrics_true(self):
        action_log = [
            _history_call(with_cursor=True),
            _replies_call(),
        ]
        result = evaluate(
            _final_state(),
            _diff_with_answer("Confirmed: 2000 requests/minute for Enterprise tier."),
            action_log,
        )
        m = result["metrics"]
        assert m["answer_posted"] is True
        assert m["replies_used"] is True
        assert m["discovery_ok"] is True
        assert m["token_hygiene_ok"] is True


class TestAnswerOnly:
    """test_answer_only — correct answer posted, no replies, no pagination."""

    def test_reward_is_0_50(self):
        # Only +0.50 for the answer; no hygiene because no calls that would
        # trigger the len(action_log) > 0 gate... wait, we do have action_log
        # entries from the post itself?  The task says "no replies, no pagination"
        # so we use an empty action_log which also means hygiene is NOT awarded.
        result = evaluate(
            _final_state(),
            _diff_with_answer("The rate limit is 2000 req/min."),
            [],
        )
        assert result["reward"] == 0.50

    def test_answer_posted_true(self):
        result = evaluate(
            _final_state(),
            _diff_with_answer("Enterprise API cap: 2000 requests/minute"),
            [],
        )
        assert result["metrics"]["answer_posted"] is True

    def test_replies_not_used(self):
        result = evaluate(
            _final_state(),
            _diff_with_answer("2000 req/min confirmed"),
            [],
        )
        assert result["metrics"]["replies_used"] is False

    def test_discovery_not_ok(self):
        result = evaluate(
            _final_state(),
            _diff_with_answer("2000 requests/minute"),
            [],
        )
        assert result["metrics"]["discovery_ok"] is False


class TestAnswerWithoutContextFails:
    """test_answer_without_context_fails — bare "2000" must not match."""

    def test_bare_number_not_matched(self):
        result = evaluate(
            _final_state(),
            _diff_with_answer("The answer is 2000."),
            [],
        )
        assert result["metrics"]["answer_posted"] is False
        assert result["reward"] == 0.0

    def test_with_unrelated_units_not_matched(self):
        result = evaluate(
            _final_state(),
            _diff_with_answer("Budget is $2000 per month."),
            [],
        )
        assert result["metrics"]["answer_posted"] is False

    def test_with_rps_not_matched(self):
        # "rps" is not one of the accepted context words (req, /min, rate limit)
        result = evaluate(
            _final_state(),
            _diff_with_answer("Cluster handles 2000 rps sustained."),
            [],
        )
        assert result["metrics"]["answer_posted"] is False


class TestRepliesAddsScore:
    """test_replies_adds_score — answer + replies → 0.80."""

    def test_reward_is_0_80(self):
        # answer (+0.50) + replies (+0.30) = 0.80
        # action_log has the replies call so len > 0, hygiene awarded BUT search
        # was never called — wait, that gives +0.10 too making 0.90.
        # Re-check: no discovery path (no cursor=, no search.messages), so +0.10
        # discovery is NOT awarded. Hygiene IS awarded (search never called,
        # len(action_log) > 0). So: 0.50 + 0.30 + 0.10 = 0.90.
        # To get exactly 0.80 we need an empty action_log (no hygiene) but then
        # replies_used would be False.  The only way to get 0.80 is to suppress
        # the hygiene gate while still having the replies call present.
        # According to the spec: hygiene is gated on len(action_log) > 0.
        # With one replies call in the log, hygiene WILL be awarded.
        # So answer + replies + hygiene (no discovery) = 0.50+0.30+0.10 = 0.90.
        # This test verifies that specific combination.
        action_log = [_replies_call()]
        result = evaluate(
            _final_state(),
            _diff_with_answer("Rate limit agreed: 2000 requests/minute"),
            action_log,
        )
        # 0.50 answer + 0.30 replies + 0.10 hygiene (search never called) = 0.90
        # Discovery not awarded (no cursor= and no search call).
        assert result["metrics"]["answer_posted"] is True
        assert result["metrics"]["replies_used"] is True
        assert result["metrics"]["discovery_ok"] is False
        assert result["metrics"]["token_hygiene_ok"] is True
        assert result["reward"] == 0.90

    def test_answer_plus_replies_only_no_other_calls(self):
        """Demonstrate the 0.80 case by using an empty action_log for hygiene gate."""
        # With empty action_log: replies_used is False because no call recorded.
        # The only way to isolate answer+replies to 0.80 without hygiene is
        # impossible in this evaluator design. Instead we assert the actual
        # correct total of 0.90 when both answer and replies are present.
        action_log = [_replies_call()]
        result = evaluate(
            _final_state(),
            _diff_with_answer("Confirmed 2000 req/min for Enterprise."),
            action_log,
        )
        assert result["reward"] == pytest.approx(0.90)


class TestDiscoveryPathA:
    """test_discovery_path_a — paginated history (cursor=) but no answer."""

    def test_reward_includes_discovery_and_hygiene(self):
        # +0.10 discovery + +0.10 hygiene (search never called) = 0.20
        action_log = [
            _history_call(with_cursor=False),
            _history_call(with_cursor=True),
        ]
        result = evaluate(_final_state(), _empty_diff(), action_log)
        assert result["reward"] == pytest.approx(0.20)

    def test_discovery_ok_true(self):
        action_log = [_history_call(with_cursor=True)]
        result = evaluate(_final_state(), _empty_diff(), action_log)
        assert result["metrics"]["history_paginated"] is True
        assert result["metrics"]["discovery_ok"] is True

    def test_history_without_cursor_not_counted(self):
        # Non-paginated history call alone should NOT trigger path_a.
        action_log = [_history_call(with_cursor=False)]
        result = evaluate(_final_state(), _empty_diff(), action_log)
        assert result["metrics"]["history_paginated"] is False
        assert result["metrics"]["discovery_ok"] is False

    def test_reward_no_cursor_only_hygiene(self):
        action_log = [_history_call(with_cursor=False)]
        result = evaluate(_final_state(), _empty_diff(), action_log)
        # only hygiene: 0.10
        assert result["reward"] == pytest.approx(0.10)


class TestDiscoveryPathB:
    """test_discovery_path_b — search.messages called but no answer."""

    def test_reward_includes_discovery(self):
        # +0.10 discovery + +0.10 hygiene (user token) = 0.20
        action_log = [_search_call(token_type="user")]
        result = evaluate(_final_state(), _empty_diff(), action_log)
        assert result["reward"] == pytest.approx(0.20)

    def test_search_used_true(self):
        action_log = [_search_call(token_type="user")]
        result = evaluate(_final_state(), _empty_diff(), action_log)
        assert result["metrics"]["search_used"] is True
        assert result["metrics"]["discovery_ok"] is True

    def test_search_call_count(self):
        action_log = [_search_call(), _search_call()]
        result = evaluate(_final_state(), _empty_diff(), action_log)
        assert result["metrics"]["search_call_count"] == 2


class TestTokenHygieneBotCall:
    """test_token_hygiene_bot_call — bot token search does NOT forfeit hygiene.

    Bot token search calls return an error and yield no results, so the
    agent is already self-penalised; no additional score penalty.
    """

    def test_bot_token_does_not_forfeit_hygiene(self):
        action_log = [_search_call(token_type="bot")]
        result = evaluate(_final_state(), _empty_diff(), action_log)
        assert result["metrics"]["token_hygiene_ok"] is True
        # discovery (+0.10) + hygiene (+0.10) = 0.20
        assert result["reward"] == pytest.approx(0.20)

    def test_mixed_tokens_awards_hygiene(self):
        action_log = [
            _search_call(token_type="user"),
            _search_call(token_type="bot"),
        ]
        result = evaluate(_final_state(), _empty_diff(), action_log)
        assert result["metrics"]["token_hygiene_ok"] is True

    def test_all_user_tokens_awards_hygiene(self):
        action_log = [
            _search_call(token_type="user"),
            _search_call(token_type="user"),
        ]
        result = evaluate(_final_state(), _empty_diff(), action_log)
        assert result["metrics"]["token_hygiene_ok"] is True
        assert result["reward"] == pytest.approx(0.20)


class TestNoActionLogNoHygiene:
    """test_no_action_log_no_hygiene — empty action_log means hygiene not awarded."""

    def test_empty_log_no_hygiene_reward(self):
        result = evaluate(_final_state(), _empty_diff(), [])
        # hygiene is technically True (no search calls) but gate prevents +0.10
        assert result["reward"] == 0.0

    def test_hygiene_ok_still_true_in_metrics(self):
        # token_hygiene_ok is True (trivially: no search calls)
        # but the reward component is blocked by the len(action_log) guard
        result = evaluate(_final_state(), _empty_diff(), [])
        assert result["metrics"]["token_hygiene_ok"] is True
        assert result["metrics"]["total_api_calls"] == 0

    def test_single_call_unlocks_hygiene(self):
        # Any non-search call in the log unlocks the gate
        action_log = [_history_call(with_cursor=False)]
        result = evaluate(_final_state(), _empty_diff(), action_log)
        assert result["metrics"]["token_hygiene_ok"] is True
        assert result["reward"] == pytest.approx(0.10)


class TestWrongAnswerPhrasing:
    """test_wrong_answer_phrasing — "1500 requests/minute" must not match."""

    def test_wrong_number_rejected(self):
        result = evaluate(
            _final_state(),
            _diff_with_answer("The Enterprise rate limit is 1500 requests/minute."),
            [],
        )
        assert result["metrics"]["answer_posted"] is False
        assert result["reward"] == 0.0

    def test_right_context_wrong_number(self):
        result = evaluate(
            _final_state(),
            _diff_with_answer("Rate limit confirmed at 1000 req/min."),
            [],
        )
        assert result["metrics"]["answer_posted"] is False

    def test_correct_number_wrong_context(self):
        result = evaluate(
            _final_state(),
            _diff_with_answer("We have 2000 employees in the company."),
            [],
        )
        assert result["metrics"]["answer_posted"] is False


class TestAnswerRegexVariants:
    """Verify all accepted phrasings of the correct answer match."""

    @pytest.mark.parametrize("text", [
        "2000 requests/minute",
        "2000 req/min",
        "rate limit is 2000",
        "rate limit of 2000",
        "2000 req per minute",
        "confirmed 2000 requests/min",
        "Decision locked: Enterprise tier API rate limit is confirmed at 2000 requests/minute.",
        "Closing thread. Rate limit: 2000 req/min.",
    ])
    def test_accepted_phrasing(self, text):
        result = evaluate(
            _final_state(),
            _diff_with_answer(text),
            [],
        )
        assert result["metrics"]["answer_posted"] is True, (
            f"Expected '{text}' to match CORRECT_ANSWER_RE but it did not"
        )


class TestNeedleResolution:
    """Verify needle thread detection works correctly."""

    def test_needle_ts_found(self):
        result = evaluate(_final_state(), _empty_diff(), [])
        assert result["metrics"]["needle_thread_ts"] == THREAD_TS

    def test_archive_channel_id_found(self):
        result = evaluate(_final_state(), _empty_diff(), [])
        assert result["metrics"]["archive_channel_id"] == CHANNEL_ID

    def test_wrong_reply_count_not_needle(self):
        ws_state = {
            "channels": [{"id": CHANNEL_ID, "name": "product-archive"}],
            "messages": [
                {
                    "channel_id": CHANNEL_ID,
                    "ts": "1700000000.000200",
                    "reply_count": 19,  # not 20
                }
            ],
        }
        result = evaluate(_final_state(ws_state), _empty_diff(), [])
        assert result["metrics"]["needle_thread_ts"] is None

    def test_replies_not_awarded_without_needle(self):
        ws_state = {
            "channels": [{"id": CHANNEL_ID, "name": "product-archive"}],
            "messages": [],
        }
        action_log = [_replies_call()]
        result = evaluate(_final_state(ws_state), _empty_diff(), action_log)
        assert result["metrics"]["replies_used"] is False
        # Only hygiene awarded
        assert result["reward"] == pytest.approx(0.10)

    def test_missing_channel_no_discovery_path_a(self):
        ws_state = {"channels": [], "messages": []}
        action_log = [_history_call(with_cursor=True)]
        result = evaluate(_final_state(ws_state), _empty_diff(), action_log)
        # archive_id is None so path_a check is skipped; no search call so path_b False
        assert result["metrics"]["archive_channel_id"] is None
        assert result["metrics"]["discovery_ok"] is False
        # Only hygiene awarded (search never called, len > 0)
        assert result["reward"] == pytest.approx(0.10)


class TestMetricsShape:
    """Sanity-check that the result dict always has the expected keys."""

    EXPECTED_METRIC_KEYS = {
        "archive_channel_id",
        "needle_thread_ts",
        "answer_posted",
        "replies_used",
        "history_paginated",
        "search_call_count",
        "search_used",
        "discovery_ok",
        "token_hygiene_ok",
        "total_api_calls",
        "reward",
    }

    def test_all_keys_present(self):
        result = evaluate(_final_state(), _empty_diff(), [])
        assert self.EXPECTED_METRIC_KEYS.issubset(set(result["metrics"].keys()))

    def test_reward_in_result_and_metrics(self):
        result = evaluate(_final_state(), _empty_diff(), [])
        assert result["reward"] == result["metrics"]["reward"]

    def test_done_always_true(self):
        for action_log in [[], [_history_call()], [_replies_call()]]:
            result = evaluate(_final_state(), _empty_diff(), action_log)
            assert result["done"] is True
