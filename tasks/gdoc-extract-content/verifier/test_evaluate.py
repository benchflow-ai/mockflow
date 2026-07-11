"""Unit tests for gdoc-extract-content evaluate function."""

import importlib.util
import os
from pathlib import Path

_task_root = Path(__file__).resolve().parent.parent
os.environ.setdefault("TASKS_DIR", str(_task_root.parent))

_spec = importlib.util.spec_from_file_location(
    "evaluate_gdoc_extract_content",
    _task_root / "verifier" / "evaluate.py",
)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

evaluate = _mod.evaluate
AURORA_DOC_IDS = list(_mod.AURORA_DOC_IDS)
KEY_DECISIONS = list(_mod.KEY_DECISIONS)   # 5 items
KEY_DEADLINES = list(_mod.KEY_DEADLINES)   # 5 items


def _body(text):
    return {"content": [{"paragraph": {"elements": [{"textRun": {"content": text}}]}}]}


def _summary_doc(text):
    return {"id": "summary-doc-id", "title": "Project Aurora Summary", "body": _body(text)}


def _state_with_originals():
    docs = [{"id": did, "title": f"Aurora Doc {i}", "body": _body("original")}
            for i, did in enumerate(AURORA_DOC_IDS)]
    return {"users": {"user1": {"documents": docs}}}


def _diff(added=None, updated=None):
    return {"updated": {"user1": {"documents": {
        "added": added or [],
        "updated": updated or [],
    }}}}


def _write_log():
    return [{"method": "POST", "path": "/docs/v1/documents"}]


# --- Pre-solve invariant ---

def test_no_action():
    result = evaluate({}, {}, [])
    assert result["reward"] == 0.0


def test_get_only_no_reward():
    """GET-only action_log must not trigger agent_acted bonuses."""
    state = _state_with_originals()
    result = evaluate(state, {}, [{"method": "GET", "path": "/docs/v1/files"}])
    assert result["reward"] == 0.0


# --- Positive scoring ---

def test_full_success():
    all_text = " ".join(KEY_DECISIONS + KEY_DEADLINES)
    state = _state_with_originals()
    diff = _diff(added=[_summary_doc(all_text)])
    result = evaluate(state, diff, _write_log())
    assert result["reward"] == 1.0  # 0.2 + 0.4 + 0.3 + 0.1
    assert result["metrics"]["decisions_found"] == 5
    assert result["metrics"]["deadlines_found"] == 5


def test_summary_exists_with_partial_decisions():
    # 2 decisions (< 3 threshold): +0.2 + 0.1
    text = f"{KEY_DECISIONS[0]} {KEY_DECISIONS[1]}"
    diff = _diff(added=[_summary_doc(text)])
    result = evaluate({}, diff, _write_log())
    assert result["reward"] == 0.30
    assert result["metrics"]["decisions_found"] == 2


def test_summary_three_decisions_no_deadlines():
    # 3 decisions → proportional 0.4*(3/5)=0.24; 0 deadlines → 0
    text = " ".join(KEY_DECISIONS[:3])
    diff = _diff(added=[_summary_doc(text)])
    result = evaluate({}, diff, _write_log())
    assert round(result["reward"], 2) == round(0.2 + 0.4 * 3 / 5, 2)


def test_originals_preserved_bonus():
    """Bonus only when agent made a write AND originals present in state."""
    all_text = " ".join(KEY_DECISIONS + KEY_DEADLINES)
    state = _state_with_originals()
    diff = _diff(added=[_summary_doc(all_text)])
    result = evaluate(state, diff, _write_log())
    assert result["metrics"]["originals_preserved"] is True
    assert result["reward"] == 1.0


def test_originals_preserved_no_bonus_without_write():
    """No originals_preserved bonus if agent_acted is False."""
    state = _state_with_originals()
    result = evaluate(state, {}, [])
    assert result["reward"] == 0.0


# --- Edge cases ---

def test_no_summary_doc_zero_reward():
    """If no summary doc added, reward is 0 even with originals in state."""
    state = _state_with_originals()
    result = evaluate(state, _diff(), _write_log())
    assert result["reward"] == 0.0


def test_wrong_title_not_matched():
    """Doc with 'aurora' but not 'summary' in title must not count."""
    wrong_doc = {"id": "x", "title": "Project Aurora Notes", "body": _body(" ".join(KEY_DECISIONS))}
    diff = _diff(added=[wrong_doc])
    result = evaluate({}, diff, _write_log())
    assert result["reward"] == 0.0
