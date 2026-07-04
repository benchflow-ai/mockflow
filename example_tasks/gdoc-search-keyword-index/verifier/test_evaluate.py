"""Unit tests for gdoc-search-keyword-index evaluate function."""

import importlib.util
import os

import pytest

_spec = importlib.util.spec_from_file_location(
    "evaluate", os.path.join(os.path.dirname(__file__), "evaluate.py")
)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
evaluate = _mod.evaluate

BUDGET_DOC_TITLES = _mod.BUDGET_DOC_TITLES
DECOY_TITLES = _mod.DECOY_TITLES

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _index_doc(text: str, title: str = "Budget Documents Index") -> dict:
    """Build a gdoc index document with the given body text."""
    body = {
        "content": [
            {"paragraph": {"elements": [{"textRun": {"content": text}}]}}
        ]
    }
    return {"title": title, "body": body}


def _diff_with_doc(doc: dict) -> dict:
    return {"updated": {"user_0": {"documents": {"added": [doc]}}}}


def _search_entry(query: str = "budget") -> dict:
    return {"method": "GET", "path": f"/drive/v3/files?q={query}"}


def _entries(titles) -> str:
    return "\n".join(
        f"{title}: Summary of budget planning, allocation, spend, and financial impact."
        for title in titles
    )


EMPTY_DIFF = {}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_pre_solve():
    """No action → reward == 0.0."""
    result = evaluate({}, EMPTY_DIFF, [])
    assert result["reward"] == 0.0
    assert result["metrics"]["index_doc_exists"] is False
    assert result["metrics"]["budget_docs_found"] == 0


def test_full_solve():
    """Index with all 5 budget titles, no FPs, 2 search queries → 1.0."""
    text = _entries(BUDGET_DOC_TITLES)
    doc = _index_doc(text)
    diff = _diff_with_doc(doc)
    action_log = [_search_entry("budget"), _search_entry("allocation")]
    result = evaluate({}, diff, action_log)
    # 0.15 (index) + 5*0.12 (docs) + 0.10 (no FP) + 0.05 (search) + 0.10 (multi) = 1.0
    assert result["reward"] == 1.0
    assert result["metrics"]["budget_docs_found"] == 5
    assert result["metrics"]["budget_docs_summarized"] == 5
    assert result["metrics"]["no_false_positives"] is True
    assert result["metrics"]["used_multiple_searches"] is True


def test_title_only_index_does_not_get_full_credit():
    """Titles without one-line summaries should not satisfy doc scoring."""
    text = "\n".join(BUDGET_DOC_TITLES)
    doc = _index_doc(text)
    diff = _diff_with_doc(doc)
    action_log = [_search_entry("budget"), _search_entry("allocation")]
    result = evaluate({}, diff, action_log)
    assert result["metrics"]["budget_docs_found"] == 5
    assert result["metrics"]["budget_docs_summarized"] == 0
    assert result["reward"] < 1.0


def test_index_only_no_docs():
    """Index exists but lists no budget docs → 0.15 only."""
    doc = _index_doc("This is an empty index document.")
    diff = _diff_with_doc(doc)
    result = evaluate({}, diff, [])
    assert result["reward"] == pytest.approx(0.15)
    assert result["metrics"]["budget_docs_found"] == 0


def test_partial_three_docs():
    """Index with 3 of 5 budget titles, no FPs, 1 search → 0.15 + 0.36 + 0.10 + 0.05 = 0.66."""
    text = _entries(BUDGET_DOC_TITLES[:3])
    doc = _index_doc(text)
    diff = _diff_with_doc(doc)
    action_log = [_search_entry()]
    result = evaluate({}, diff, action_log)
    assert result["reward"] == pytest.approx(0.66)
    assert result["metrics"]["budget_docs_found"] == 3


def test_false_positive_penalty():
    """Index with all budget docs + 1 decoy → -0.15 penalty, no precision bonus."""
    text = _entries(BUDGET_DOC_TITLES) + "\n" + DECOY_TITLES[0]
    doc = _index_doc(text)
    diff = _diff_with_doc(doc)
    action_log = [_search_entry(), _search_entry("other")]
    result = evaluate({}, diff, action_log)
    # 0.15 + 0.60 + 0.0 (FP present) - 0.15 + 0.05 + 0.10 = 0.75
    assert result["reward"] == pytest.approx(0.75)
    assert result["metrics"]["false_positives"] == 1
    assert result["metrics"]["no_false_positives"] is False


def test_multiple_false_positives_capped():
    """FP penalty capped at -0.45 even with many decoys."""
    text = _entries(BUDGET_DOC_TITLES) + "\n" + "\n".join(DECOY_TITLES[:5])
    doc = _index_doc(text)
    diff = _diff_with_doc(doc)
    result = evaluate({}, diff, [])
    # 0.15 + 0.60 - 0.45 = 0.30, clamped to 0.0 min
    assert result["metrics"]["false_positives"] == 5
    assert result["metrics"]["fp_penalty"] == 0.45
    assert result["reward"] == pytest.approx(0.30)


def test_search_bonus():
    """Single search query → +0.05 but not +0.10."""
    text = _entries(BUDGET_DOC_TITLES)
    doc = _index_doc(text)
    diff = _diff_with_doc(doc)
    action_log = [_search_entry()]
    result = evaluate({}, diff, action_log)
    assert result["metrics"]["used_search"] is True
    assert result["metrics"]["used_multiple_searches"] is False
    # 0.15 + 0.60 + 0.10 + 0.05 = 0.90
    assert result["reward"] == pytest.approx(0.90)


def test_no_precision_bonus_without_found():
    """Index with 0 budget docs and 0 FPs → no precision bonus (needs found >= 1)."""
    doc = _index_doc("Nothing relevant here.")
    diff = _diff_with_doc(doc)
    result = evaluate({}, diff, [])
    assert result["metrics"]["no_false_positives"] is True
    assert result["metrics"]["budget_docs_found"] == 0
    # Precision bonus requires found_count >= 1
    assert result["reward"] == pytest.approx(0.15)


def test_index_title_case_insensitive():
    """Index doc matched case-insensitively on title."""
    doc = _index_doc(BUDGET_DOC_TITLES[0], title="BUDGET documents INDEX")
    diff = _diff_with_doc(doc)
    result = evaluate({}, diff, [])
    assert result["metrics"]["index_doc_exists"] is True
