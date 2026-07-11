"""Unit tests for gdoc-workflow-meeting-digest evaluate function."""

import importlib.util
import os

import pytest

_spec = importlib.util.spec_from_file_location(
    "evaluate", os.path.join(os.path.dirname(__file__), "evaluate.py")
)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
evaluate = _mod.evaluate

STANDUP_DOC_IDS = _mod.STANDUP_DOC_IDS
DIGEST_TITLE = _mod.DIGEST_TITLE

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _digest_doc(text: str, title: str = None) -> dict:
    """Build a digest document."""
    title = title or DIGEST_TITLE
    body = {
        "content": [
            {"paragraph": {"elements": [{"textRun": {"content": text}}]}}
        ]
    }
    return {"title": title, "body": body}


def _diff_with_doc(doc: dict) -> dict:
    return {"updated": {"user_0": {"documents": {"added": [doc]}}}}


def _state_with_standups() -> dict:
    """State where all standup docs exist."""
    docs = [{"id": did} for did in STANDUP_DOC_IDS]
    return {"users": {"user_0": {"documents": docs}}}


def _write_action() -> dict:
    return {"method": "POST", "path": "/v1/documents"}


FULL_DIGEST_TEXT = (
    "Week 1\n"
    "Highlights: Completed auth service deployment.\n"
    "Blockers: datetime conversion issues in the timezone module.\n\n"
    "Week 2\n"
    "Highlights: Migration to staging environment complete.\n"
    "Blockers: memory leak detected in the worker service.\n\n"
    "Week 3\n"
    "Highlights: Deployed rate limiter for API endpoints.\n"
    "Blockers: Waiting on ops team for maintenance window scheduling.\n\n"
    "Week 4\n"
    "Highlights: Achieved zero downtime during final migration.\n"
    "Blockers: no blockers reported this week.\n"
)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_pre_solve():
    """No action → reward == 0.0."""
    result = evaluate({"users": {}}, {}, [])
    assert result["reward"] == 0.0
    assert result["metrics"]["digest_created"] is False


def test_full_solve():
    """Perfect digest with all highlights, blockers, ordered, originals preserved → 1.0."""
    doc = _digest_doc(FULL_DIGEST_TEXT)
    diff = _diff_with_doc(doc)
    state = _state_with_standups()
    result = evaluate(state, diff, [_write_action()])
    assert result["reward"] == 1.0
    assert result["metrics"]["digest_created"] is True
    assert result["metrics"]["highlights_found"] == 4
    assert result["metrics"]["blockers_found"] == 4
    assert result["metrics"]["correctly_ordered"] is True
    assert result["metrics"]["originals_preserved"] is True


def test_digest_created_only():
    """Digest created but empty content → 0.2 (title match)."""
    doc = _digest_doc("No relevant content here.")
    diff = _diff_with_doc(doc)
    result = evaluate({"users": {}}, diff, [])
    assert result["reward"] == pytest.approx(0.2)
    assert result["metrics"]["highlights_found"] == 0
    assert result["metrics"]["blockers_found"] == 0


def test_partial_highlights():
    """Digest with 2 of 4 highlights, no blockers → 0.2 + 2*0.0875 = 0.375."""
    text = "Week 1: Completed auth service. Week 3: Deployed rate limiter."
    doc = _digest_doc(text)
    diff = _diff_with_doc(doc)
    result = evaluate({"users": {}}, diff, [])
    assert result["metrics"]["highlight_week1"] is True
    assert result["metrics"]["highlight_week3"] is True
    assert result["metrics"]["highlights_found"] == 2
    # 0.2 + 2*0.0875 + 0.1 (ordered: w1 before w3) = 0.475 → rounds to 0.47
    assert result["reward"] == pytest.approx(0.47)


def test_partial_blockers():
    """Digest with all highlights + 2 of 4 blockers."""
    text = (
        "Week 1: auth service deployed. datetime issues.\n"
        "Week 2: migration to staging. memory leak found.\n"
        "Week 3: rate limiter deployed.\n"
        "Week 4: zero downtime achieved.\n"
    )
    doc = _digest_doc(text)
    diff = _diff_with_doc(doc)
    state = _state_with_standups()
    result = evaluate(state, diff, [_write_action()])
    assert result["metrics"]["highlights_found"] == 4
    assert result["metrics"]["blockers_found"] == 2
    # 0.2 + 4*0.0875 + 2*0.0625 + 0.1 (ordered) + 0.1 (preserved) = 0.875
    assert result["reward"] == pytest.approx(0.88)  # rounded


def test_wrong_order():
    """Content out of chronological order → correctly_ordered == False."""
    text = (
        "Week 4: zero downtime.\n"
        "Week 1: auth service.\n"
        "Week 3: rate limiter.\n"
    )
    doc = _digest_doc(text)
    diff = _diff_with_doc(doc)
    result = evaluate({"users": {}}, diff, [])
    assert result["metrics"]["correctly_ordered"] is False


def test_originals_not_preserved():
    """Standup docs missing from final state → no preservation bonus."""
    doc = _digest_doc(FULL_DIGEST_TEXT)
    diff = _diff_with_doc(doc)
    # State without standup docs
    result = evaluate({"users": {}}, diff, [_write_action()])
    assert result["metrics"]["originals_preserved"] is False
    # 0.2 + 4*0.0875 + 4*0.0625 + 0.1 = 0.9 (no preservation bonus)
    assert result["reward"] == pytest.approx(0.9)


def test_preservation_requires_action():
    """Even if originals present, no bonus without agent action."""
    result = evaluate(_state_with_standups(), {}, [])
    assert result["metrics"]["originals_preserved"] is True
    assert result["reward"] == 0.0


def test_alternative_title():
    """Title with 'standup' and 'digest' keywords matches."""
    doc = _digest_doc("auth service. memory leak.", title="Weekly Standup Digest March")
    diff = _diff_with_doc(doc)
    result = evaluate({"users": {}}, diff, [])
    assert result["metrics"]["digest_created"] is True


def test_partial_credit_wrong_title():
    """Doc created with wrong title → no digest_created but partial content credit."""
    doc = _digest_doc(FULL_DIGEST_TEXT, title="Meeting Notes Summary")
    diff = _diff_with_doc(doc)
    result = evaluate({"users": {}}, diff, [])
    assert result["metrics"]["digest_created"] is False
    # 4 highlights + 4 blockers = 8 * 0.0125 = 0.1, capped at 0.15
    assert result["reward"] == pytest.approx(0.1)
    assert result["metrics"]["partial_content_credit"] == pytest.approx(0.1)


def test_partial_credit_action_log_body():
    """Content in action log request body → partial credit."""
    action = {
        "method": "POST",
        "path": "/v1/documents",
        "body": "auth service deployment. migration to staging. memory leak found. rate limiter deployed. zero downtime.",
    }
    result = evaluate({"users": {}}, {}, [action])
    assert result["metrics"]["digest_created"] is False
    assert result["reward"] > 0.0
    assert result["reward"] <= 0.15


def test_partial_credit_docs_read():
    """Agent read all 4 standup docs but didn't create digest → partial credit."""
    actions = [
        {"method": "GET", "path": f"/v1/documents/{did}"} for did in STANDUP_DOC_IDS
    ]
    state = _state_with_standups()
    result = evaluate(state, {}, actions)
    assert result["metrics"]["digest_created"] is False
    assert result["metrics"]["standup_docs_read"] == 4
    # 4 docs * 0.025 = 0.10 for reads (no preservation bonus — GETs aren't "action")
    assert result["metrics"]["partial_content_credit"] == pytest.approx(0.1)
    assert result["reward"] == pytest.approx(0.1)


def test_partial_credit_capped():
    """Partial content credit capped at 0.15."""
    actions = [
        {"method": "POST", "path": f"/v1/documents/{did}",
         "body": (
            "auth service. migration staging. rate limiter. zero downtime. "
            "datetime conversion. memory leak. maintenance window. no blockers."
         )} for did in STANDUP_DOC_IDS
    ]
    result = evaluate({"users": {}}, {}, actions)
    assert result["metrics"]["digest_created"] is False
    # content: 8 * 0.0125 = 0.1, docs_read: 4 * 0.025 = 0.1 → total 0.2, capped at 0.15
    assert result["reward"] == pytest.approx(0.15)
    assert result["reward"] <= 0.15
