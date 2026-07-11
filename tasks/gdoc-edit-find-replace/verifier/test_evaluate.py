"""Unit tests for gdoc-edit-find-replace evaluate function."""

import importlib.util
import os
from pathlib import Path

_task_root = Path(__file__).resolve().parent.parent
os.environ.setdefault("TASKS_DIR", str(_task_root.parent))

_spec = importlib.util.spec_from_file_location(
    "evaluate_gdoc_edit_find_replace",
    _task_root / "verifier" / "evaluate.py",
)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

evaluate = _mod.evaluate
NEEDLE_DOC_IDS = list(_mod.NEEDLE_DOC_IDS)

_OTHER_DOC_ID = "other-doc-not-needle"


def _body(text):
    return {"content": [{"paragraph": {"elements": [{"textRun": {"content": text}}]}}]}


def _replaced_text():
    return "This document is about Meridian Labs and its services."


def _original_text():
    return "This document mentions Nexus AI as the company."


def _state(doc_ids, text_fn):
    docs = [{"id": did, "title": f"doc-{did}", "body": _body(text_fn(did))} for did in doc_ids]
    return {"users": {"user1": {"documents": docs}}}


def _diff(updated=None):
    return {"updated": {"user1": {"documents": {"updated": updated or [], "added": []}}}}


def _write_log():
    return [{"method": "PATCH", "path": "/docs/v1/documents/doc1"}]


def _search_write_log():
    return [
        {"method": "GET", "path": "/docs/v1/files?q=name+contains+'Nexus'"},
        {"method": "PATCH", "path": "/docs/v1/documents/doc1"},
    ]


# --- Pre-solve invariant ---

def test_no_action():
    result = evaluate({}, {}, [])
    assert result["reward"] == 0.0


def test_get_only_no_reward():
    """GET-only calls (harness init) must not trigger agent_acted bonuses."""
    result = evaluate({}, {}, [{"method": "GET", "path": "/docs/v1/files"}])
    assert result["reward"] == 0.0


# --- Positive scoring ---

def test_full_success():
    state = _state(NEEDLE_DOC_IDS, lambda _: _replaced_text())
    diff = _diff(updated=[{"id": did} for did in NEEDLE_DOC_IDS])
    result = evaluate(state, diff, _search_write_log())
    assert result["reward"] == 1.0
    assert result["metrics"]["needle_docs_replaced"] == 5


def test_partial_two_replaced():
    done = NEEDLE_DOC_IDS[:2]
    not_done = NEEDLE_DOC_IDS[2:]
    docs = (
        [{"id": did, "title": f"doc-{did}", "body": _body(_replaced_text())} for did in done]
        + [{"id": did, "title": f"doc-{did}", "body": _body(_original_text())} for did in not_done]
    )
    state = {"users": {"user1": {"documents": docs}}}
    diff = _diff(updated=[{"id": did} for did in done])
    result = evaluate(state, diff, _search_write_log())
    assert result["reward"] == 0.55  # 2*0.15 + 0.15 + 0.10
    assert result["metrics"]["needle_docs_replaced"] == 2


def test_one_replaced():
    done = NEEDLE_DOC_IDS[:1]
    not_done = NEEDLE_DOC_IDS[1:]
    docs = (
        [{"id": did, "title": f"doc-{did}", "body": _body(_replaced_text())} for did in done]
        + [{"id": did, "title": f"doc-{did}", "body": _body(_original_text())} for did in not_done]
    )
    state = {"users": {"user1": {"documents": docs}}}
    diff = _diff(updated=[{"id": did} for did in done])
    result = evaluate(state, diff, _write_log())
    assert result["reward"] == 0.30  # 0.15 + 0.15 (no_collateral), no search
    assert result["metrics"]["needle_docs_replaced"] == 1


# --- Penalty interactions ---

def test_collateral_damage_loses_precision_bonus():
    state = _state(NEEDLE_DOC_IDS, lambda _: _replaced_text())
    diff = _diff(updated=[{"id": did} for did in NEEDLE_DOC_IDS] + [{"id": _OTHER_DOC_ID}])
    result = evaluate(state, diff, _search_write_log())
    assert result["reward"] == 0.85  # 0.75 + 0.0 (collateral) + 0.10
    assert result["metrics"]["no_collateral_damage"] is False


def test_no_search_loses_search_bonus():
    state = _state(NEEDLE_DOC_IDS, lambda _: _replaced_text())
    diff = _diff(updated=[{"id": did} for did in NEEDLE_DOC_IDS])
    result = evaluate(state, diff, _write_log())
    assert result["reward"] == 0.90  # 0.75 + 0.15, no search
    assert result["metrics"]["used_search"] is False


# --- Edge cases ---

def test_old_name_still_present_not_counted():
    """Doc with Meridian Labs but still has Nexus AI should not count."""
    state = _state(NEEDLE_DOC_IDS, lambda _: "Nexus AI and Meridian Labs both mentioned.")
    diff = _diff(updated=[{"id": did} for did in NEEDLE_DOC_IDS])
    result = evaluate(state, diff, _write_log())
    assert result["metrics"]["needle_docs_replaced"] == 0


def test_reward_clamped():
    state = _state(NEEDLE_DOC_IDS, lambda _: _replaced_text())
    diff = _diff(updated=[{"id": did} for did in NEEDLE_DOC_IDS])
    result = evaluate(state, diff, _search_write_log())
    assert result["reward"] <= 1.0
    assert result["done"] is True
