"""Unit tests for gdoc-edit-append-status evaluate function."""

import importlib.util
import os
from pathlib import Path

_task_root = Path(__file__).resolve().parent.parent
os.environ.setdefault("TASKS_DIR", str(_task_root.parent))

_spec = importlib.util.spec_from_file_location(
    "evaluate_gdoc_edit_append_status",
    _task_root / "verifier" / "evaluate.py",
)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

evaluate = _mod.evaluate
PROJECT_DOC_IDS = list(_mod.PROJECT_DOC_IDS)
DECOY_DOC_IDS = list(_mod.DECOY_DOC_IDS)
EXPECTED_PHASES = _mod.EXPECTED_PHASES
PROJECT_NAMES = _mod.PROJECT_NAMES

# Full correct status blocks per doc
_PHOENIX_STATUS = "\n---\nSTATUS REVIEW — March 19, 2026\nProject: Project Phoenix\nCurrent Phase: Data migration\nStatus: Active\n---\n"
_ATLAS_STATUS = "\n---\nSTATUS REVIEW — March 19, 2026\nProject: Project Atlas\nCurrent Phase: Unified search platform\nStatus: Active\n---\n"
_HORIZON_STATUS = "\n---\nSTATUS REVIEW — March 19, 2026\nProject: Project Horizon\nCurrent Phase: GDPR compliance\nStatus: Active\n---\n"
_VELOCITY_STATUS = "\n---\nSTATUS REVIEW — March 19, 2026\nProject: Project Velocity\nCurrent Phase: User authentication redesign\nStatus: Active\n---\n"

_STATUS_BLOCKS = [_PHOENIX_STATUS, _ATLAS_STATUS, _HORIZON_STATUS, _VELOCITY_STATUS]

# Generic status block — has date + Active but NO project name, NO phase
_GENERIC_STATUS = "\n---\nSTATUS REVIEW — March 19, 2026\nProject: TBD\nCurrent Phase: TBD\nStatus: Active\n---\n"

_OTHER_DOC_ID = "other-doc-id-not-in-project"


def _body(text):
    return {"content": [{"paragraph": {"elements": [{"textRun": {"content": text}}]}}]}


def _state(doc_ids, texts):
    """Build state with specific text per doc."""
    if callable(texts):
        docs = [{"id": did, "title": f"doc-{did}", "body": _body(texts(did))} for did in doc_ids]
    else:
        docs = [{"id": did, "title": f"doc-{did}", "body": _body(t)} for did, t in zip(doc_ids, texts)]
    return {"users": {"user1": {"documents": docs}}}


def _diff(updated=None, added=None):
    return {"updated": {"user1": {"documents": {
        "updated": updated or [],
        "added": added or [],
    }}}}


def _write_log():
    return [{"method": "PATCH", "path": "/docs/v1/documents/doc1"}]


def _search_write_log():
    return [
        {"method": "GET", "path": "/docs/v1/files?q=title+contains+'Project'"},
        {"method": "PATCH", "path": "/docs/v1/documents/doc1"},
    ]


# --- Pre-solve invariant ---

def test_no_action():
    result = evaluate({}, {}, [])
    assert result["reward"] == 0.0


def test_get_only_no_reward():
    result = evaluate({}, {}, [{"method": "GET", "path": "/docs/v1/files"}])
    assert result["reward"] == 0.0


# --- Full success: all 4 docs with correct project name + phase ---

def test_full_success():
    """Perfect run: all 4 docs with date, label, project name, and correct phase."""
    texts = [f"Project content{block}" for block in _STATUS_BLOCKS]
    state = _state(PROJECT_DOC_IDS, texts)
    diff = _diff(updated=[{"id": did} for did in PROJECT_DOC_IDS])
    result = evaluate(state, diff, _search_write_log())
    assert result["reward"] == 1.0
    assert result["metrics"]["docs_appended"] == 4
    assert result["metrics"]["docs_with_name"] == 4
    assert result["metrics"]["docs_with_phase"] == 4


# --- Partial: generic status block (no project name, no phase) ---

def test_generic_status_block_partial():
    """Agent appends a generic block (date + Active) but no project name or phase.
    Gets 0.10 per doc = 0.40 total."""
    state = _state(PROJECT_DOC_IDS, lambda _: "Project content" + _GENERIC_STATUS)
    diff = _diff(updated=[{"id": did} for did in PROJECT_DOC_IDS])
    result = evaluate(state, diff, _search_write_log())
    assert result["reward"] == 0.40  # 4 * 0.10
    assert result["metrics"]["docs_appended"] == 4
    assert result["metrics"]["docs_with_name"] == 0
    assert result["metrics"]["docs_with_phase"] == 0


# --- Partial: correct name but wrong/missing phase ---

def test_name_but_no_phase():
    """Status block has project name but generic phase placeholder."""
    phoenix_text = "Project Phoenix content\n---\nSTATUS REVIEW — March 19, 2026\nProject: Project Phoenix\nCurrent Phase: In progress\nStatus: Active\n---\n"
    state = _state([PROJECT_DOC_IDS[0]], [phoenix_text])
    diff = _diff(updated=[{"id": PROJECT_DOC_IDS[0]}])
    result = evaluate(state, diff, _write_log())
    # 0.10 (basic) + 0.05 (name) + 0.0 (wrong phase) = 0.15
    assert result["reward"] == 0.15


# --- Partial: correct phase but wrong project name ---

def test_phase_but_wrong_name():
    """Status block has correct phase but wrong project name."""
    phoenix_text = "content\n---\nSTATUS REVIEW — March 19, 2026\nProject: Project Foo\nCurrent Phase: Data migration in progress\nStatus: Active\n---\n"
    state = _state([PROJECT_DOC_IDS[0]], [phoenix_text])
    diff = _diff(updated=[{"id": PROJECT_DOC_IDS[0]}])
    result = evaluate(state, diff, _write_log())
    # 0.10 (basic) + 0.0 (wrong name) + 0.10 (phase) = 0.20
    assert result["reward"] == 0.20


# --- Two docs correct, two generic ---

def test_partial_two_full_two_generic():
    """2 docs with full blocks, 2 with generic blocks."""
    texts = [
        f"content{_PHOENIX_STATUS}",
        f"content{_ATLAS_STATUS}",
        "content" + _GENERIC_STATUS,
        "content" + _GENERIC_STATUS,
    ]
    state = _state(PROJECT_DOC_IDS, texts)
    diff = _diff(updated=[{"id": did} for did in PROJECT_DOC_IDS])
    result = evaluate(state, diff, _search_write_log())
    # 2 full * 0.25 + 2 generic * 0.10 = 0.70
    assert result["reward"] == 0.70
    assert result["metrics"]["docs_appended"] == 4
    assert result["metrics"]["docs_with_phase"] == 2


# --- Decoy penalties ---

def test_one_decoy_penalty():
    """Modifying 1 decoy costs -0.20."""
    state = _state(PROJECT_DOC_IDS, [f"content{b}" for b in _STATUS_BLOCKS])
    diff = _diff(updated=[{"id": did} for did in PROJECT_DOC_IDS] + [{"id": DECOY_DOC_IDS[0]}])
    result = evaluate(state, diff, _search_write_log())
    assert result["reward"] == 0.80  # 1.0 - 0.20
    assert result["metrics"]["decoys_modified"] == 1


def test_all_decoys_penalty():
    """Modifying all 5 decoys costs -1.0, capped at 0.0 total."""
    state = _state(PROJECT_DOC_IDS, [f"content{b}" for b in _STATUS_BLOCKS])
    diff = _diff(updated=[{"id": did} for did in PROJECT_DOC_IDS] + [{"id": did} for did in DECOY_DOC_IDS])
    result = evaluate(state, diff, _search_write_log())
    assert result["reward"] == 0.0  # max(1.0 - 1.0, 0) = 0.0
    assert result["metrics"]["decoys_modified"] == 5


def test_three_decoys_with_generic_status():
    """3 decoys modified + only generic status blocks."""
    state = _state(PROJECT_DOC_IDS, lambda _: "content" + _GENERIC_STATUS)
    diff = _diff(updated=[{"id": did} for did in PROJECT_DOC_IDS] + [{"id": did} for did in DECOY_DOC_IDS[:3]])
    result = evaluate(state, diff, _search_write_log())
    # 4*0.10 - 3*0.20 = 0.40 - 0.60 = -0.20 -> clamped to 0.0
    assert result["reward"] == 0.0


def test_decoy_only_no_project_docs():
    """Modifying only decoys with no successful appends -> 0."""
    state = _state(PROJECT_DOC_IDS, lambda _: "Project no status")
    diff = _diff(updated=[{"id": did} for did in DECOY_DOC_IDS])
    result = evaluate(state, diff, _write_log())
    assert result["reward"] == 0.0
    assert result["metrics"]["decoys_modified"] == 5


# --- Collateral damage tracked as metric ---

def test_collateral_damage_tracked():
    state = _state(PROJECT_DOC_IDS, [f"content{b}" for b in _STATUS_BLOCKS])
    diff = _diff(updated=[{"id": did} for did in PROJECT_DOC_IDS] + [{"id": _OTHER_DOC_ID}])
    result = evaluate(state, diff, _search_write_log())
    assert result["reward"] == 1.0  # collateral tracked but not penalized
    assert result["metrics"]["non_project_modified"] == 1


# --- Edge cases ---

def test_missing_one_marker_not_counted():
    """Doc with Active + project name but no date should not count."""
    text = "STATUS REVIEW\nProject: Project Phoenix\nCurrent Phase: Data migration\nStatus: Active\n"
    state = _state([PROJECT_DOC_IDS[0]], [text])
    diff = _diff(updated=[{"id": PROJECT_DOC_IDS[0]}])
    result = evaluate(state, diff, _write_log())
    assert result["metrics"]["docs_appended"] == 0
    assert result["reward"] == 0.0


def test_reward_clamped_to_one():
    state = _state(PROJECT_DOC_IDS, [f"content{b}" for b in _STATUS_BLOCKS])
    diff = _diff(updated=[{"id": did} for did in PROJECT_DOC_IDS])
    result = evaluate(state, diff, _search_write_log())
    assert result["reward"] <= 1.0
    assert result["done"] is True


def test_subtle_decoy_on_hold():
    """The 'on hold' decoy (Aurora) should be penalized if modified."""
    state = _state(PROJECT_DOC_IDS[:1], [f"content{_PHOENIX_STATUS}"])
    aurora_id = DECOY_DOC_IDS[3]  # Project Aurora (on hold)
    diff = _diff(updated=[{"id": PROJECT_DOC_IDS[0]}, {"id": aurora_id}])
    result = evaluate(state, diff, _write_log())
    # 0.25 - 0.20 = 0.05
    assert result["reward"] == 0.05
    assert result["metrics"]["decoys_modified"] == 1


def test_subtle_decoy_indefinite_hold():
    """The 'indefinite hold' decoy (Cobalt) should be penalized if modified."""
    state = _state(PROJECT_DOC_IDS[:1], [f"content{_PHOENIX_STATUS}"])
    cobalt_id = DECOY_DOC_IDS[4]  # Project Cobalt (indefinite hold)
    diff = _diff(updated=[{"id": PROJECT_DOC_IDS[0]}, {"id": cobalt_id}])
    result = evaluate(state, diff, _write_log())
    assert result["reward"] == 0.05
    assert result["metrics"]["decoys_modified"] == 1
