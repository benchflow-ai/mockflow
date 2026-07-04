"""Unit tests for multi-doc-slack-spec-drift evaluate function."""

import importlib.util
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock

# Stub env_0_gdrive so needles.py can be imported without the real package
if "env_0_gdrive" not in sys.modules:
    _stub = MagicMock()
    _stub.seed.content.DOC = "application/vnd.google-apps.document"
    sys.modules["env_0_gdrive"] = _stub
    sys.modules["env_0_gdrive.seed"] = _stub.seed
    sys.modules["env_0_gdrive.seed.content"] = _stub.seed.content

_task_root = Path(__file__).resolve().parent.parent
os.environ.setdefault("TASKS_DIR", str(_task_root.parent))

_spec = importlib.util.spec_from_file_location(
    "evaluate_multi_doc_slack_spec_drift",
    _task_root / "verifier" / "evaluate.py",
)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

evaluate = _mod.evaluate
DOC_SPEC = _mod._get_doc_spec()
DRIFT_DECISIONS = _mod._get_drift_decisions()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _comment(content: str, doc_id: str = DOC_SPEC) -> dict:
    return {
        "id": f"comment_{hash(content) % 10000}",
        "documentId": doc_id,
        "content": content,
        "resolved": False,
        "quotedText": "some quoted text",
        "authorId": "agent_user",
        "replies": [],
        "createdTime": "2026-03-28T10:00:00Z",
        "modifiedTime": "2026-03-28T10:00:00Z",
    }


def _diff(comments=None, doc_updated=False):
    """Build a diff structure with optional comments and doc body edit."""
    user_data = {
        "documents": {
            "added": [],
            "updated": [],
            "deleted": [],
        },
        "comments": {
            "added": comments or [],
            "updated": [],
            "deleted": [],
        },
    }
    if doc_updated:
        user_data["documents"]["updated"] = [
            {"id": DOC_SPEC, "body": {"content": [{"paragraph": {}}]}}
        ]
    return {"updated": {"agent_user": user_data}}


def _empty_diff():
    return {"updated": {}}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_no_action():
    """No comments, no edits -> 0.0."""
    result = evaluate({}, _empty_diff(), [])
    assert result["reward"] == 0.0
    assert result["metrics"]["drifts_matched"] == 0
    assert result["metrics"]["precision_score"] == 0.0
    assert result["metrics"]["restraint_score"] == 0.0


def test_all_drifts_no_fp_no_edit():
    """All 3 drifts flagged, no false positives, no doc edit -> 1.0."""
    comments = [
        _comment("The Enterprise tier limit was bumped to 2500 req/min per Slack discussion."),
        _comment("Slack decided to use the Retry-After header instead of X-RateLimit-Reset."),
        _comment("The burst window was changed from 60s to 10s per Derek's update."),
    ]
    result = evaluate({}, _diff(comments), [])
    assert result["reward"] == 1.0
    assert result["metrics"]["drifts_matched"] == 3
    assert result["metrics"]["false_positives"] == 0
    assert result["metrics"]["precision_score"] == 0.15
    assert result["metrics"]["restraint_score"] == 0.10


def test_two_drifts_no_fp_no_edit():
    """2/3 drifts flagged, no FP, no edit -> 0.75."""
    comments = [
        _comment("Enterprise limit changed to 2500 per Slack."),
        _comment("Burst window is now 10s instead of 60s."),
    ]
    result = evaluate({}, _diff(comments), [])
    assert result["reward"] == 0.75
    assert result["metrics"]["drifts_matched"] == 2
    assert result["metrics"]["false_positives"] == 0


def test_all_drifts_with_two_fp():
    """All 3 drifts + 2 false positive comments -> 0.90."""
    comments = [
        _comment("Enterprise limit should be 2500 req/min now."),
        _comment("Switch to Retry-After header per Alice's message."),
        _comment("Burst window changed to 10s."),
        _comment("Per-endpoint limits were suggested but not decided."),
        _comment("Free tier might need adjustment too."),
    ]
    result = evaluate({}, _diff(comments), [])
    assert result["reward"] == 0.90
    assert result["metrics"]["drifts_matched"] == 3
    assert result["metrics"]["false_positives"] == 2
    assert result["metrics"]["precision_score"] == 0.05


def test_all_drifts_doc_edited():
    """All 3 drifts flagged, no FP, but doc body edited -> 0.90."""
    comments = [
        _comment("Enterprise limit is 2500 now per Slack."),
        _comment("Retry-After header replacing X-RateLimit-Reset."),
        _comment("Burst window shortened to 10s."),
    ]
    result = evaluate({}, _diff(comments, doc_updated=True), [])
    assert result["reward"] == 0.90
    assert result["metrics"]["drifts_matched"] == 3
    assert result["metrics"]["body_edited"] is True
    assert result["metrics"]["restraint_score"] == 0.0


def test_only_noise_comments():
    """Comments that match no drift -> 0.0 (gated on drift match)."""
    comments = [
        _comment("Per-endpoint limits might be worth considering."),
        _comment("The deploy went fine, no issues."),
    ]
    result = evaluate({}, _diff(comments), [])
    assert result["reward"] == 0.0
    assert result["metrics"]["drifts_matched"] == 0
    # Precision/restraint not awarded since no drift matched
    assert result["metrics"]["precision_score"] == 0.0
    assert result["metrics"]["restraint_score"] == 0.0


def test_enterprise_requires_both_keywords():
    """A comment mentioning '2500' for free tier should NOT match enterprise drift."""
    comments = [
        # Mentions 2500 but for free tier, not enterprise — should NOT match
        _comment("Carol raised that 2500 might be too high for the free tier."),
        _comment("Retry-After header should replace X-RateLimit-Reset per Slack."),
        _comment("Burst window needs to be 10 seconds, not 60."),
    ]
    result = evaluate({}, _diff(comments), [])
    # Only 2 drifts matched (retry-after + burst), not enterprise
    assert result["metrics"]["drifts_matched"] == 2
    assert result["metrics"]["drift_enterprise_limit"] is False
    # The free-tier comment is a false positive
    assert result["metrics"]["false_positives"] == 1


def test_single_comment_matching_multiple_drifts():
    """One comment covering two drifts should count for both."""
    comments = [
        _comment("Enterprise limit bumped to 2500 and burst window is 10 seconds now."),
        _comment("Retry-After header replacing X-RateLimit-Reset."),
    ]
    result = evaluate({}, _diff(comments), [])
    assert result["metrics"]["drifts_matched"] == 3
    assert result["metrics"]["false_positives"] == 0
    assert result["reward"] == 1.0
