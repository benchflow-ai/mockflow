"""Unit tests for gdoc-workflow-changelog evaluate function."""

import importlib.util
import os
from pathlib import Path

_task_root = Path(__file__).resolve().parent.parent
os.environ.setdefault("TASKS_DIR", str(_task_root.parent))

_spec = importlib.util.spec_from_file_location(
    "evaluate_gdoc_workflow_changelog",
    _task_root / "verifier" / "evaluate.py",
)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

evaluate = _mod.evaluate
API_DOC_IDS = list(_mod.API_DOC_IDS)
KEY_CHANGES = list(_mod.KEY_CHANGES)   # 13 items
CHANGE_SCORE = _mod.CHANGE_SCORE       # 0.5 / 13


def _body(text):
    return {"content": [{"paragraph": {"elements": [{"textRun": {"content": text}}]}}]}


def _changelog_doc(text):
    return {"id": "changelog-doc-id", "title": "API Changelog", "body": _body(text)}


def _state_with_originals():
    docs = [{"id": did, "title": f"API Doc {i}", "body": _body("original content")}
            for i, did in enumerate(API_DOC_IDS)]
    return {"users": {"user1": {"documents": docs}}}


def _diff(added=None):
    return {"updated": {"user1": {"documents": {"added": added or [], "updated": []}}}}


def _write_log():
    return [{"method": "POST", "path": "/docs/v1/documents"}]


def _search_write_log():
    return [
        {"method": "GET", "path": "/docs/v1/files?q=name+contains+'API'"},
        {"method": "POST", "path": "/docs/v1/documents"},
    ]


def _all_changes_text():
    parts = []
    for change in KEY_CHANGES:
        for term_group in change["terms"]:
            parts.extend(term_group)
    return " ".join(parts)


# --- Pre-solve invariant ---

def test_no_action():
    result = evaluate({}, {}, [])
    assert result["reward"] == 0.0


def test_get_only_no_reward():
    state = _state_with_originals()
    result = evaluate(state, {}, [{"method": "GET", "path": "/docs/v1/files"}])
    assert result["reward"] == 0.0


# --- Positive scoring ---

def test_full_success():
    state = _state_with_originals()
    diff = _diff(added=[_changelog_doc(_all_changes_text())])
    result = evaluate(state, diff, _search_write_log())
    assert result["reward"] == 1.0
    assert result["metrics"]["changes_found"] == 13
    assert result["metrics"]["changelog_created"] is True


def test_partial_half_changes():
    # 6 of 13 changes — include all required terms for each change (in order → ordering bonus)
    text = " ".join(t for c in KEY_CHANGES[:6] for g in c["terms"] for t in g)
    diff = _diff(added=[_changelog_doc(text)])
    result = evaluate({}, diff, _search_write_log())
    # 0.2 (created) + 6 * CHANGE_SCORE + 0.1 (ordered) + 0.1 (search)
    expected = round(0.2 + 6 * CHANGE_SCORE + 0.1 + 0.1, 2)
    assert result["reward"] == expected
    assert result["metrics"]["changes_found"] == 6
    assert result["metrics"]["correctly_ordered"] is True


def test_changelog_exists_no_changes():
    diff = _diff(added=[_changelog_doc("no relevant keywords here")])
    result = evaluate({}, diff, _write_log())
    assert result["reward"] == 0.20  # doc exists but no changes found
    assert result["metrics"]["changes_found"] == 0


def test_originals_preserved_bonus():
    state = _state_with_originals()
    diff = _diff(added=[_changelog_doc(_all_changes_text())])
    result = evaluate(state, diff, _write_log())
    assert result["metrics"]["originals_preserved"] is True
    # 0.2 (created) + 0.5 (changes) + 0.1 (ordered) + 0.1 (originals) = 0.9 (no search)
    assert result["reward"] == round(0.2 + 0.5 + 0.1 + 0.1, 2)


def test_originals_preserved_no_bonus_without_write():
    state = _state_with_originals()
    result = evaluate(state, _diff(), [])
    assert result["reward"] == 0.0


# --- Penalty interaction ---

def test_no_search_loses_search_bonus():
    state = _state_with_originals()
    diff = _diff(added=[_changelog_doc(_all_changes_text())])
    result = evaluate(state, diff, _write_log())
    assert result["metrics"]["used_search"] is False
    # 0.2 + 0.5 + 0.1 (ordered) + 0.1 (originals) = 0.9 (no search)
    assert result["reward"] == round(0.2 + 0.5 + 0.1 + 0.1, 2)


# --- Edge cases ---

def test_wrong_title_not_matched():
    """Title needs both 'changelog' and 'api'."""
    wrong = {"id": "x", "title": "Release Notes", "body": _body(_all_changes_text())}
    result = evaluate({}, _diff(added=[wrong]), _write_log())
    assert result["metrics"]["changelog_created"] is False
    assert result["reward"] == 0.0
