"""Unit tests for gdrive-archive-stale-drafts evaluate function."""

import importlib.util
import os
from pathlib import Path


_task_root = Path(__file__).resolve().parent.parent
os.environ.setdefault("TASK_ROOT", str(_task_root))

_spec = importlib.util.spec_from_file_location(
    "evaluate_gdrive_archive_stale_drafts",
    _task_root / "verifier" / "evaluate.py",
)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

evaluate = _mod.evaluate
TARGET_IDS = list(_mod.TARGET_IDS)
PROTECTED_IDS = list(_mod.PROTECTED_IDS)
ARCHIVE_DRAFTS_FOLDER = _mod.ARCHIVE_DRAFTS_FOLDER


def _folder(file_id, name, parent_id=None):
    return {
        "id": file_id,
        "name": name,
        "mimeType": "application/vnd.google-apps.folder",
        "parentId": parent_id,
    }


def _file(file_id, name, parent_id, trashed=False):
    return {
        "id": file_id,
        "name": name,
        "mimeType": "application/vnd.google-apps.document",
        "parentId": parent_id,
        "trashed": trashed,
    }


def _base_state():
    archive_id = "folder_archive"
    archive_drafts_id = "folder_archive_drafts"
    marketing_id = "folder_marketing"
    shared_id = "folder_shared"
    finance_id = "folder_finance"
    eng_id = "folder_engineering"
    all_hands_id = "folder_all_hands"

    files = [
        _folder(archive_id, "Archive"),
        _folder(archive_drafts_id, "Drafts", archive_id),
        _folder(marketing_id, "Campaigns"),
        _folder(shared_id, "Templates"),
        _folder(finance_id, "Finance"),
        _folder(eng_id, "Monitoring"),
        _folder(all_hands_id, "All Hands"),
        _file(TARGET_IDS[0], "Q3 Pricing Page Draft", marketing_id),
        _file(TARGET_IDS[1], "Partner Onboarding Draft v2", shared_id),
        _file(TARGET_IDS[2], "Hiring Panel Rubric Draft", finance_id),
        _file(PROTECTED_IDS[0], "Product Launch Draft Timeline", marketing_id),
        _file(PROTECTED_IDS[1], "Board Update Draft", finance_id),
        _file(PROTECTED_IDS[2], "Security Review Draft", eng_id),
        _file(PROTECTED_IDS[3], "Final OKR Plan", all_hands_id),
        _file(PROTECTED_IDS[4], "API Migration Draft", eng_id),
    ]
    return {"files": files}


def _diff(updated=None):
    return {"files": {"added": [], "updated": updated or [], "deleted": []}}


def _move_update(file_id, parent_id):
    return {
        "id": file_id,
        "parentId": parent_id,
        "modifiedTime": "2026-03-23T10:00:00Z",
        "modifiedByMeTime": "2026-03-23T10:00:00Z",
        "lastModifyingUserId": "user_alex",
        "version": 2,
    }


def test_evaluate_full_success():
    state = _base_state()
    archive_drafts_id = "folder_archive_drafts"
    for file in state["files"]:
        if file["id"] in TARGET_IDS:
            file["parentId"] = archive_drafts_id

    diff = _diff([_move_update(file_id, archive_drafts_id) for file_id in TARGET_IDS])
    action_log = [{"method": "GET", "path": "/drive/v3/files?q=name+contains+'Draft'"}]

    result = evaluate(state, diff, action_log)

    assert result["reward"] == 1.0
    assert result["done"] is True
    assert result["metrics"]["target_moved"] == 3
    assert result["metrics"]["protected_moved"] == 0


def test_evaluate_penalizes_protected_move():
    state = _base_state()
    archive_drafts_id = "folder_archive_drafts"
    for file in state["files"]:
        if file["id"] in TARGET_IDS or file["id"] == PROTECTED_IDS[0]:
            file["parentId"] = archive_drafts_id

    diff = _diff(
        [_move_update(file_id, archive_drafts_id) for file_id in TARGET_IDS + [PROTECTED_IDS[0]]]
    )
    action_log = [{"method": "GET", "path": "/drive/v3/files?q=name+contains+'Draft'"}]

    result = evaluate(state, diff, action_log)

    assert result["reward"] == -1.0
    assert result["done"] is False
    assert result["metrics"]["protected_moved"] == 1


def test_evaluate_boundary_decoy_triggers_penalty():
    """Moving the 89-day boundary decoy into Archive/Drafts should trigger -1."""
    state = _base_state()
    archive_drafts_id = "folder_archive_drafts"
    # Move only the boundary decoy (89 days since last edit — under 90-day threshold)
    for file in state["files"]:
        if file["id"] == PROTECTED_IDS[4]:
            file["parentId"] = archive_drafts_id

    diff = _diff([_move_update(PROTECTED_IDS[4], archive_drafts_id)])
    action_log = [{"method": "GET", "path": "/drive/v3/files?q=name+contains+'Draft'"}]

    result = evaluate(state, diff, action_log)

    assert result["reward"] == -1.0
    assert result["metrics"]["protected_moved"] == 1


def test_evaluate_partial_completion_without_search_bonus():
    state = _base_state()
    archive_drafts_id = "folder_archive_drafts"
    moved_targets = TARGET_IDS[:2]
    for file in state["files"]:
        if file["id"] in moved_targets:
            file["parentId"] = archive_drafts_id

    diff = _diff([_move_update(file_id, archive_drafts_id) for file_id in moved_targets])

    result = evaluate(state, diff, [])

    assert result["reward"] == 0.6
    assert result["done"] is False
    assert result["metrics"]["target_moved"] == 2
    assert result["metrics"]["used_search"] is False
