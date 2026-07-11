"""Unit tests for workflow-event-rsvp evaluate function."""

import importlib.util
import os

import pytest

_spec = importlib.util.spec_from_file_location("evaluate", os.path.join(os.path.dirname(__file__), "evaluate.py"))
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
evaluate = _mod.evaluate

SAMPLE_MANIFEST = {
    "needles": [
        {"role": "next_week", "message_id": "nw1", "thread_id": "thread_nw1"},
        {"role": "next_week", "message_id": "nw2", "thread_id": "thread_nw2"},
        {"role": "future", "message_id": "fut1", "thread_id": "thread_fut1"},
        {"role": "future", "message_id": "fut2", "thread_id": "thread_fut2"},
        {"role": "ignore", "message_id": "ign1", "thread_id": "thread_ign1"},
        {"role": "ignore", "message_id": "ign2", "thread_id": "thread_ign2"},
        {"role": "ignore", "message_id": "ign3", "thread_id": "thread_ign3"},
        {"role": "ignore", "message_id": "ign4", "thread_id": "thread_ign4"},
        {"role": "ignore", "message_id": "ign5", "thread_id": "thread_ign5"},
    ]
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _msg(id, to="", body="", subject="", is_sent=False, thread_id="", in_reply_to="", label_ids=None):
    m = {"id": id, "to": to, "body": body, "subject": subject, "threadId": thread_id, "inReplyTo": in_reply_to}
    if is_sent:
        m["isSent"] = True
    if label_ids:
        m["labelIds"] = label_ids
    return m


def _state(messages=None, labels=None):
    user = {}
    if messages is not None:
        user["messages"] = messages
    if labels is not None:
        user["labels"] = labels
    return {"users": {"u1": user}}


def _diff(added_msgs=None, updated_msgs=None):
    msgs = {}
    if added_msgs:
        msgs["added"] = added_msgs
    if updated_msgs:
        msgs["updated"] = updated_msgs
    return {"updated": {"u1": {"messages": msgs}}, "deleted": {}}


def _empty_diff():
    return {"updated": {}, "deleted": {}}


# ---------------------------------------------------------------------------
# Pre-solve invariant
# ---------------------------------------------------------------------------

class TestPreSolve:
    def test_no_action_returns_zero(self):
        result = evaluate(_state(messages=[], labels=[]), _empty_diff(), [], SAMPLE_MANIFEST)
        assert result["reward"] == 0.0


# ---------------------------------------------------------------------------
# Positive scoring: replies
# ---------------------------------------------------------------------------

class TestReplies:
    def test_reply_one_next_week(self):
        sent_msg = _msg("s1", body="I have confirmed attendance", is_sent=True, thread_id="thread_nw1")
        state = _state(messages=[sent_msg], labels=[])
        diff = _diff(added_msgs=[sent_msg])
        result = evaluate(state, diff, [], SAMPLE_MANIFEST)
        assert result["reward"] == 0.30

    def test_reply_both_next_week(self):
        s1 = _msg("s1", body="confirmed!", is_sent=True, thread_id="thread_nw1")
        s2 = _msg("s2", body="confirmed!", is_sent=True, thread_id="thread_nw2")
        state = _state(messages=[s1, s2], labels=[])
        diff = _diff(added_msgs=[s1, s2])
        result = evaluate(state, diff, [], SAMPLE_MANIFEST)
        assert result["reward"] == 0.60

    def test_reply_without_confirmed(self):
        sent_msg = _msg("s1", body="Sounds great, I will be there!", is_sent=True, thread_id="thread_nw1")
        state = _state(messages=[sent_msg], labels=[])
        diff = _diff(added_msgs=[sent_msg])
        result = evaluate(state, diff, [], SAMPLE_MANIFEST)
        assert result["reward"] == 0.0


# ---------------------------------------------------------------------------
# Positive scoring: labeling
# ---------------------------------------------------------------------------

class TestLabeling:
    def test_label_one_future(self):
        fut_label = {"id": "lbl_future", "name": "Future Events"}
        updated_msg = {"id": "fut1", "labelIds": ["lbl_future"]}
        state = _state(messages=[], labels=[fut_label])
        diff = _diff(updated_msgs=[updated_msg])
        result = evaluate(state, diff, [], SAMPLE_MANIFEST)
        assert result["reward"] == 0.20

    def test_label_both_future(self):
        fut_label = {"id": "lbl_future", "name": "Future Events"}
        u1 = {"id": "fut1", "labelIds": ["lbl_future"]}
        u2 = {"id": "fut2", "labelIds": ["lbl_future"]}
        state = _state(messages=[], labels=[fut_label])
        diff = _diff(updated_msgs=[u1, u2])
        result = evaluate(state, diff, [], SAMPLE_MANIFEST)
        assert result["reward"] == 0.40


# ---------------------------------------------------------------------------
# Precision penalties: wrong replies
# ---------------------------------------------------------------------------

class TestWrongReplies:
    def test_reply_to_future_event(self):
        sent_msg = _msg("s1", body="confirmed", is_sent=True, thread_id="thread_fut1")
        state = _state(messages=[sent_msg], labels=[])
        diff = _diff(added_msgs=[sent_msg])
        result = evaluate(state, diff, [], SAMPLE_MANIFEST)
        assert result["reward"] == -0.50

    def test_reply_to_ignore_event(self):
        sent_msg = _msg("s1", body="confirmed", is_sent=True, thread_id="thread_ign1")
        state = _state(messages=[sent_msg], labels=[])
        diff = _diff(added_msgs=[sent_msg])
        result = evaluate(state, diff, [], SAMPLE_MANIFEST)
        assert result["reward"] == -0.50


# ---------------------------------------------------------------------------
# Label-spray penalty (TESTS THE BUG FIX)
# ---------------------------------------------------------------------------

class TestLabelSpray:
    def test_mislabel_next_week_as_future(self):
        fut_label = {"id": "lbl_future", "name": "Future Events"}
        updated_msg = {"id": "nw1", "labelIds": ["lbl_future"]}
        state = _state(messages=[], labels=[fut_label])
        diff = _diff(updated_msgs=[updated_msg])
        result = evaluate(state, diff, [], SAMPLE_MANIFEST)
        assert result["reward"] == -0.20
        assert result["metrics"]["mislabeled_future"] == 1

    def test_mislabel_ignore_as_future(self):
        fut_label = {"id": "lbl_future", "name": "Future Events"}
        updated_msg = {"id": "ign1", "labelIds": ["lbl_future"]}
        state = _state(messages=[], labels=[fut_label])
        diff = _diff(updated_msgs=[updated_msg])
        result = evaluate(state, diff, [], SAMPLE_MANIFEST)
        assert result["reward"] == -0.20
        assert result["metrics"]["mislabeled_future"] == 1

    def test_label_spray_all(self):
        """Label ALL messages as 'Future Events'. Future gets +0.40, but mislabeled penalty offsets."""
        fut_label = {"id": "lbl_future", "name": "Future Events"}
        # All 9 messages labeled
        updated = [
            {"id": "nw1", "labelIds": ["lbl_future"]},
            {"id": "nw2", "labelIds": ["lbl_future"]},
            {"id": "fut1", "labelIds": ["lbl_future"]},
            {"id": "fut2", "labelIds": ["lbl_future"]},
            {"id": "ign1", "labelIds": ["lbl_future"]},
            {"id": "ign2", "labelIds": ["lbl_future"]},
            {"id": "ign3", "labelIds": ["lbl_future"]},
            {"id": "ign4", "labelIds": ["lbl_future"]},
            {"id": "ign5", "labelIds": ["lbl_future"]},
        ]
        state = _state(messages=[], labels=[fut_label])
        diff = _diff(updated_msgs=updated)
        result = evaluate(state, diff, [], SAMPLE_MANIFEST)
        # +0.40 for 2 future labeled, -0.20 * 7 for mislabeled (2 next_week + 5 ignore)
        expected = 0.40 - 1.40
        assert result["reward"] == round(max(-1.0, min(expected, 1.0)), 2)
        assert result["metrics"]["future_labeled"] == 2
        assert result["metrics"]["mislabeled_future"] == 7


# ---------------------------------------------------------------------------
# Combined
# ---------------------------------------------------------------------------

class TestCombined:
    def test_perfect_score(self):
        fut_label = {"id": "lbl_future", "name": "Future Events"}
        s1 = _msg("s1", body="confirmed", is_sent=True, thread_id="thread_nw1")
        s2 = _msg("s2", body="confirmed", is_sent=True, thread_id="thread_nw2")
        u1 = {"id": "fut1", "labelIds": ["lbl_future"]}
        u2 = {"id": "fut2", "labelIds": ["lbl_future"]}
        state = _state(messages=[s1, s2], labels=[fut_label])
        diff = _diff(added_msgs=[s1, s2], updated_msgs=[u1, u2])
        result = evaluate(state, diff, [], SAMPLE_MANIFEST)
        assert result["reward"] == 1.0

    def test_mixed_correct_and_penalty(self):
        s1 = _msg("s1", body="confirmed", is_sent=True, thread_id="thread_nw1")
        s2 = _msg("s2", body="confirmed", is_sent=True, thread_id="thread_fut1")
        state = _state(messages=[s1, s2], labels=[])
        diff = _diff(added_msgs=[s1, s2])
        result = evaluate(state, diff, [], SAMPLE_MANIFEST)
        # +0.30 for nw1 reply, -0.50 for future reply = -0.20
        assert result["reward"] == -0.20


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_result_always_done(self):
        result = evaluate(_state(messages=[], labels=[]), _empty_diff(), [], SAMPLE_MANIFEST)
        assert result["done"] is True

    def test_reward_clamped_at_minus_1(self):
        # Reply to all future + ignore threads = -0.50 * 7 = -3.50, clamped to -1.0
        msgs = []
        for i, tid in enumerate(["thread_fut1", "thread_fut2", "thread_ign1", "thread_ign2", "thread_ign3", "thread_ign4", "thread_ign5"]):
            msgs.append(_msg(f"s{i}", body="confirmed", is_sent=True, thread_id=tid))
        state = _state(messages=msgs, labels=[])
        diff = _diff(added_msgs=msgs)
        result = evaluate(state, diff, [], SAMPLE_MANIFEST)
        assert result["reward"] == -1.0

    def test_in_reply_to_matching(self):
        """Reply matched via inReplyTo field instead of threadId."""
        sent_msg = _msg("s1", body="confirmed", is_sent=True, thread_id="", in_reply_to="nw1")
        state = _state(messages=[sent_msg], labels=[])
        diff = _diff(added_msgs=[sent_msg])
        result = evaluate(state, diff, [], SAMPLE_MANIFEST)
        assert result["reward"] == 0.30


# ---------------------------------------------------------------------------
# Filler reply penalty
# ---------------------------------------------------------------------------

class TestFillerReply:
    def test_reply_to_filler_penalized(self):
        """Replying to a non-needle thread incurs -0.05."""
        sent_msg = _msg("s1", body="thanks!", is_sent=True, thread_id="thread_filler_abc")
        state = _state(messages=[sent_msg], labels=[])
        diff = _diff(added_msgs=[sent_msg])
        result = evaluate(state, diff, [], SAMPLE_MANIFEST)
        assert result["reward"] == -0.05
        assert result["metrics"]["filler_replied"] == 1

    def test_many_filler_replies_capped(self):
        """Filler penalty caps at -1.0 even with many filler replies."""
        msgs = [_msg(f"s{i}", body="ok", is_sent=True, thread_id=f"thread_filler_{i}") for i in range(20)]
        state = _state(messages=msgs, labels=[])
        diff = _diff(added_msgs=msgs)
        result = evaluate(state, diff, [], SAMPLE_MANIFEST)
        assert result["reward"] == -1.0
        assert result["metrics"]["filler_replied"] == 20

    def test_correct_reply_not_counted_as_filler(self):
        """Reply to a next-week needle is NOT a filler reply."""
        sent_msg = _msg("s1", body="confirmed", is_sent=True, thread_id="thread_nw1")
        state = _state(messages=[sent_msg], labels=[])
        diff = _diff(added_msgs=[sent_msg])
        result = evaluate(state, diff, [], SAMPLE_MANIFEST)
        assert result["metrics"]["filler_replied"] == 0
        assert result["reward"] == 0.30

    def test_filler_reply_plus_correct_work(self):
        """Filler penalty subtracts from positive work."""
        s1 = _msg("s1", body="confirmed", is_sent=True, thread_id="thread_nw1")
        s2 = _msg("s2", body="thanks!", is_sent=True, thread_id="thread_filler_x")
        state = _state(messages=[s1, s2], labels=[])
        diff = _diff(added_msgs=[s1, s2])
        result = evaluate(state, diff, [], SAMPLE_MANIFEST)
        # +0.30 for nw1 reply, -0.05 for filler = 0.25
        assert result["reward"] == 0.25


# ---------------------------------------------------------------------------
# Filler label-spray penalty
# ---------------------------------------------------------------------------

class TestFillerLabelSpray:
    def test_single_filler_mislabeled(self):
        """Labeling a filler (non-needle) message as 'Future Events' costs -0.05."""
        fut_label = {"id": "lbl_future", "name": "Future Events"}
        updated_msg = {"id": "filler_msg_1", "labelIds": ["lbl_future"]}
        state = _state(messages=[], labels=[fut_label])
        diff = _diff(updated_msgs=[updated_msg])
        result = evaluate(state, diff, [], SAMPLE_MANIFEST)
        assert result["reward"] == -0.05
        assert result["metrics"]["filler_mislabeled"] == 1

    def test_many_filler_mislabels_capped(self):
        """Filler label-spray penalty caps at -1.0."""
        fut_label = {"id": "lbl_future", "name": "Future Events"}
        updated = [{"id": f"filler_{i}", "labelIds": ["lbl_future"]} for i in range(20)]
        state = _state(messages=[], labels=[fut_label])
        diff = _diff(updated_msgs=updated)
        result = evaluate(state, diff, [], SAMPLE_MANIFEST)
        assert result["reward"] == -1.0
        assert result["metrics"]["filler_mislabeled"] == 20

    def test_filler_label_spray_plus_correct_labels(self):
        """Correct future labels score positive, filler mislabels subtract."""
        fut_label = {"id": "lbl_future", "name": "Future Events"}
        updated = [
            {"id": "fut1", "labelIds": ["lbl_future"]},  # correct: +0.20
            {"id": "fut2", "labelIds": ["lbl_future"]},  # correct: +0.20
            {"id": "filler_1", "labelIds": ["lbl_future"]},  # filler: -0.05
            {"id": "filler_2", "labelIds": ["lbl_future"]},  # filler: -0.05
        ]
        state = _state(messages=[], labels=[fut_label])
        diff = _diff(updated_msgs=updated)
        result = evaluate(state, diff, [], SAMPLE_MANIFEST)
        # +0.40 - 0.10 = 0.30
        assert result["reward"] == 0.30
        assert result["metrics"]["future_labeled"] == 2
        assert result["metrics"]["filler_mislabeled"] == 2


# ---------------------------------------------------------------------------
# inReplyTo penalty test
# ---------------------------------------------------------------------------

class TestInReplyToPenalty:
    def test_wrong_reply_via_in_reply_to_future(self):
        """Reply to a future event matched via inReplyTo still incurs penalty."""
        sent_msg = _msg("s1", body="confirmed", is_sent=True, thread_id="", in_reply_to="fut1")
        state = _state(messages=[sent_msg], labels=[])
        diff = _diff(added_msgs=[sent_msg])
        result = evaluate(state, diff, [], SAMPLE_MANIFEST)
        assert result["reward"] == -0.50
        assert result["metrics"]["future_replied"] == 1

    def test_wrong_reply_via_in_reply_to_ignore(self):
        """Reply to an ignore event matched via inReplyTo still incurs penalty."""
        sent_msg = _msg("s1", body="confirmed", is_sent=True, thread_id="", in_reply_to="ign1")
        state = _state(messages=[sent_msg], labels=[])
        diff = _diff(added_msgs=[sent_msg])
        result = evaluate(state, diff, [], SAMPLE_MANIFEST)
        assert result["reward"] == -0.50
        assert result["metrics"]["ignore_replied"] == 1


# ---------------------------------------------------------------------------
# No-manifest test
# ---------------------------------------------------------------------------

class TestNoManifest:
    def test_none_manifest(self):
        """evaluate() returns reward 0.0 when manifest is None."""
        result = evaluate(_state(messages=[], labels=[]), _empty_diff(), [], None)
        assert result["reward"] == 0.0

    def test_empty_manifest(self):
        """evaluate() returns reward 0.0 when manifest is empty dict (falsy)."""
        result = evaluate(_state(messages=[], labels=[]), _empty_diff(), [], {})
        assert result["reward"] == 0.0
