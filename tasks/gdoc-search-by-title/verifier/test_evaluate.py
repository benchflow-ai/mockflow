"""Unit tests for gdoc-search-by-title evaluate function."""

import importlib.util
import os
from pathlib import Path

_task_root = Path(__file__).resolve().parent.parent
os.environ.setdefault("TASKS_DIR", str(_task_root.parent))

_spec = importlib.util.spec_from_file_location(
    "evaluate_gdoc_search_by_title",
    _task_root / "verifier" / "evaluate.py",
)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

evaluate = _mod.evaluate
NEEDLE_DOC_IDS = list(_mod.NEEDLE_DOC_IDS)
PRIMARY_ACTION_ITEMS = list(_mod.PRIMARY_ACTION_ITEMS)
FOLLOWUP_ACTION_ITEMS = list(_mod.FOLLOWUP_ACTION_ITEMS)
ALL_ACTION_ITEMS = list(_mod.ALL_ACTION_ITEMS)
DECOY_ITEMS = list(_mod.DECOY_ITEMS)


def _body(text):
    return {"content": [{"paragraph": {"elements": [{"textRun": {"content": text}}]}}]}


def _action_doc(text):
    return {"id": "new-doc-id", "title": "Sprint Action Items", "body": _body(text)}


def _state_with_originals():
    return {"users": {"user1": {"documents": [
        {"id": NEEDLE_DOC_IDS[0], "title": "Q1 Sprint Planning Notes", "body": _body("original")},
        {"id": NEEDLE_DOC_IDS[1], "title": "Q1 Sprint Planning — Async Follow-ups", "body": _body("followup")},
    ]}}}


def _diff(added=None):
    return {"updated": {"user1": {"documents": {"added": added or []}}}}


def _write_log():
    return [{"method": "POST", "path": "/docs/v1/documents"}]


def _search_log():
    return [
        {"method": "GET", "path": "/drive/v3/files?q=name+contains"},
        {"method": "POST", "path": "/docs/v1/documents"},
    ]


# --- Pre-solve invariant: zero reward with no agent action ---

def test_no_action_zero():
    """Completely empty inputs must yield 0."""
    result = evaluate({}, {}, [])
    assert result["reward"] == 0.0


def test_get_only_no_reward():
    """GET-only action_log must not trigger any bonuses."""
    state = _state_with_originals()
    result = evaluate(state, {}, [{"method": "GET", "path": "/drive/v3/files"}])
    assert result["reward"] == 0.0


def test_original_exists_no_action_no_reward():
    """Original docs in state but no agent action => 0."""
    state = _state_with_originals()
    result = evaluate(state, _diff(), [])
    assert result["reward"] == 0.0


# --- Positive scoring ---

def test_full_success_with_search():
    """Perfect run: correct doc, all 7 items, no noise, no decoys, originals preserved, used search."""
    items_text = "\n".join(f"- {item}" for item in ALL_ACTION_ITEMS)
    state = _state_with_originals()
    diff = _diff(added=[_action_doc(items_text)])
    result = evaluate(state, diff, _search_log())
    # 0.15 (doc) + 0.50 (7/7 items) + 0.10 (no noise) + 0.10 (no decoys) + 0.05 (originals) + 0.10 (search)
    assert result["reward"] == 1.0
    assert result["metrics"]["action_items_found"] == 7
    assert result["metrics"]["primary_items_found"] == 4
    assert result["metrics"]["followup_items_found"] == 3
    assert result["metrics"]["noise_phrases_found"] == 0
    assert result["metrics"]["decoy_items_found"] == 0


def test_primary_only_partial():
    """Agent finds only the primary doc items (4/7) -- misses follow-up doc entirely."""
    items_text = "\n".join(f"- {item}" for item in PRIMARY_ACTION_ITEMS)
    state = _state_with_originals()
    diff = _diff(added=[_action_doc(items_text)])
    result = evaluate(state, diff, _search_log())
    # 0.15 + 0.50*(4/7)≈0.2857 + 0.10 + 0.10 + 0.05 + 0.10 = 0.79
    assert result["reward"] == 0.79
    assert result["metrics"]["primary_items_found"] == 4
    assert result["metrics"]["followup_items_found"] == 0


def test_followup_only_partial():
    """Agent finds only the follow-up doc items (3/7)."""
    items_text = "\n".join(f"- {item}" for item in FOLLOWUP_ACTION_ITEMS)
    state = _state_with_originals()
    diff = _diff(added=[_action_doc(items_text)])
    result = evaluate(state, diff, _search_log())
    # 0.15 + 0.50*(3/7)≈0.2143 + 0.10 + 0.10 + 0.05 + 0.10 = 0.71
    assert result["reward"] == 0.71
    assert result["metrics"]["primary_items_found"] == 0
    assert result["metrics"]["followup_items_found"] == 3


def test_doc_exists_no_items():
    """Created doc with right title but no action items."""
    state = _state_with_originals()
    diff = _diff(added=[_action_doc("Nothing relevant here")])
    result = evaluate(state, diff, _write_log())
    # 0.15 (doc) + 0.0 (no items) + 0.10 (no noise) + 0.10 (no decoys) + 0.05 (originals)
    assert result["reward"] == 0.4


def test_single_item():
    """Even one action item gets proportional credit."""
    text = PRIMARY_ACTION_ITEMS[0]
    diff = _diff(added=[_action_doc(text)])
    result = evaluate({}, diff, _write_log())
    # 0.15 + 0.50*(1/7)≈0.0714 + 0.10 + 0.10 = 0.42
    assert result["reward"] == 0.42
    assert result["metrics"]["action_items_found"] == 1


def test_noise_penalty():
    """Including non-action-item content loses the precision bonus."""
    text = "\n".join(ALL_ACTION_ITEMS) + "\nAttendees: Sarah Chen\nKey Decisions: ..."
    diff = _diff(added=[_action_doc(text)])
    result = evaluate({}, diff, _write_log())
    # 0.15 + 0.50 + 0.0 (noise) + 0.10 (no decoys) = 0.75
    assert result["reward"] == 0.75
    assert result["metrics"]["noise_phrases_found"] >= 1


# --- Decoy contamination (proportional) ---

def test_decoy_contamination_one_item():
    """One decoy item: partial loss of decoy bonus."""
    text = "\n".join(ALL_ACTION_ITEMS) + "\ninvestigate API v2 feasibility"
    diff = _diff(added=[_action_doc(text)])
    result = evaluate({}, diff, _write_log())
    # 0.15 + 0.50 + 0.10 (no noise) + 0.10*(1 - 1/3) = 0.10*0.667 ≈ 0.07
    # total ≈ 0.82
    assert result["reward"] == 0.82
    assert result["metrics"]["decoy_items_found"] == 1


def test_decoy_contamination_two_items():
    """Two decoy items: more loss."""
    text = "\n".join(ALL_ACTION_ITEMS) + "\ninvestigate API v2 feasibility\nlogin page redesign"
    diff = _diff(added=[_action_doc(text)])
    result = evaluate({}, diff, _write_log())
    # 0.15 + 0.50 + 0.10 + 0.10*(1 - 2/3) = 0.10*0.333 ≈ 0.03
    # total ≈ 0.78
    assert result["reward"] == 0.78
    assert result["metrics"]["decoy_items_found"] == 2


def test_decoy_contamination_three_plus():
    """Three or more decoy items: full loss of decoy bonus."""
    text = "\n".join(ALL_ACTION_ITEMS) + "\ninvestigate API v2 feasibility\nlogin page redesign\nfinalize headcount plan"
    diff = _diff(added=[_action_doc(text)])
    result = evaluate({}, diff, _write_log())
    # 0.15 + 0.50 + 0.10 + 0.0 (>=3 decoys) = 0.75
    assert result["reward"] == 0.75
    assert result["metrics"]["decoy_items_found"] == 3


def test_retro_decoy_contamination():
    """Retro action items (same people, same date) should be penalized."""
    text = "\n".join(ALL_ACTION_ITEMS) + "\nretry logic to flaky integration tests\nPR review SLA document\nautomated test failure alerts"
    diff = _diff(added=[_action_doc(text)])
    result = evaluate({}, diff, _write_log())
    # 3 decoy items -> full loss
    assert result["reward"] == 0.75
    assert result["metrics"]["decoy_items_found"] == 3


def test_platform_team_decoy_contamination():
    """Platform team items (same date, different team) should be penalized."""
    text = "\n".join(ALL_ACTION_ITEMS) + "\nKubernetes upgrade runbook\nDatadog dashboards"
    diff = _diff(added=[_action_doc(text)])
    result = evaluate({}, diff, _write_log())
    assert result["metrics"]["decoy_items_found"] == 2
    # 0.15 + 0.50 + 0.10 + 0.10*(1 - 2/3) ≈ 0.78
    assert result["reward"] == 0.78


def test_midcycle_decoy_contamination():
    """Mid-cycle re-scoped items should be penalized (they overlap with real items)."""
    text = "\n".join(ALL_ACTION_ITEMS) + "\nrollback strategy\nextend performance benchmarks\nedge cases to auth middleware"
    diff = _diff(added=[_action_doc(text)])
    result = evaluate({}, diff, _write_log())
    assert result["metrics"]["decoy_items_found"] == 3
    assert result["reward"] == 0.75


def test_noise_and_decoy_contamination():
    """Both noise and decoys present loses both bonuses."""
    text = "\n".join(ALL_ACTION_ITEMS) + "\nAttendees: someone\nlogin page redesign\nfinalize headcount plan\nKubernetes upgrade runbook"
    diff = _diff(added=[_action_doc(text)])
    result = evaluate({}, diff, _write_log())
    # 0.15 + 0.50 + 0.0 (noise) + 0.0 (>=3 decoys) = 0.65
    assert result["reward"] == 0.65


def test_original_preserved_requires_new_doc():
    """original_preserved bonus only fires when a new doc was created."""
    state = _state_with_originals()
    wrong_doc = {"id": "x", "title": "Random Notes", "body": _body("stuff")}
    diff = _diff(added=[wrong_doc])
    result = evaluate(state, diff, _write_log())
    assert result["reward"] == 0.0  # wrong title -> no scoring at all
    assert result["metrics"]["original_preserved"] is True


def test_search_bonus_requires_write():
    """used_search bonus requires agent_acted (mutating call)."""
    result = evaluate({}, {}, [{"method": "GET", "path": "/drive/v3/files?q=name"}])
    assert result["reward"] == 0.0
    assert result["metrics"]["used_search"] is True
    assert result["metrics"]["agent_acted"] is False


# --- Edge cases ---

def test_wrong_title_not_matched():
    """Doc with 'sprint' but not 'action' in title must not count."""
    wrong_doc = {"id": "x", "title": "Sprint Planning Notes", "body": _body(" ".join(ALL_ACTION_ITEMS))}
    diff = _diff(added=[wrong_doc])
    result = evaluate({}, diff, _write_log())
    assert result["reward"] == 0.0


def test_partial_originals_preserved():
    """Only one of two originals preserved -- no bonus."""
    state = {"users": {"user1": {"documents": [
        {"id": NEEDLE_DOC_IDS[0], "title": "Q1 Sprint Planning Notes", "body": _body("original")},
    ]}}}
    items_text = "\n".join(ALL_ACTION_ITEMS)
    diff = _diff(added=[_action_doc(items_text)])
    result = evaluate(state, diff, _write_log())
    assert result["metrics"]["original_preserved"] is False
    # 0.15 + 0.50 + 0.10 + 0.10 + 0.0 (partial originals) = 0.85
    assert result["reward"] == 0.85


def test_massive_decoy_contamination():
    """Many decoy items (>3) still caps at full loss of bonus."""
    text = "\n".join(ALL_ACTION_ITEMS) + "\n" + "\n".join(DECOY_ITEMS[:8])
    diff = _diff(added=[_action_doc(text)])
    result = evaluate({}, diff, _write_log())
    assert result["metrics"]["decoy_items_found"] == 8
    # 0.15 + 0.50 + 0.10 + 0.0 = 0.75
    assert result["reward"] == 0.75
