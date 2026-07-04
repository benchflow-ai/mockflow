"""Tests for task-seed layering and env-owned pack behavior."""

from __future__ import annotations

from mock_gcal.models import Event, get_session_factory, init_db, reset_engine
from mock_gcal.seed.content import DEFAULT_TARGET_EVENTS
from mock_gcal.seed.generator import seed_database
from mock_gcal.seed.task_packs import get_seed_pack


def _open_db(db_path: str):
    reset_engine()
    init_db(db_path)
    return get_session_factory(db_path)()


def test_source_backed_tasks_overlay_shared_default_world(tmp_path):
    db_path = str(tmp_path / "gcal_federal_register_task.db")
    reset_engine()
    result = seed_database(
        scenario="task:gcal-federal-register-meeting-amendments",
        seed=42,
        db_path=db_path,
        num_users=1,
    )

    assert result["events"] == DEFAULT_TARGET_EVENTS

    db = _open_db(db_path)
    try:
        events = db.query(Event).all()
        summaries = {event.summary for event in events}

        assert "Customer Advisory Board Dinner" in summaries
        assert (
            "Gateway National Recreation Area Fort Hancock 21st Century "
            "Advisory Committee Notice of Public Meetings"
        ) in summaries
        assert "Notice of Public Meeting for the National Park System Advisory Board" in summaries

        gateway_events = [
            event
            for event in events
            if event.summary
            == "Gateway National Recreation Area Fort Hancock 21st Century Advisory Committee Notice of Public Meetings"
        ]
        assert any(
            event.start_dt.year == 2025 and event.location == "Virtual"
            for event in gateway_events
        )
        assert any(
            event.location == "At or near Joshua Tree National Park, California"
            for event in events
            if event.summary
            == "Notice of Public Meeting for the National Park System Advisory Board"
        )
    finally:
        db.close()
        reset_engine()


def test_pack_only_task_worlds_can_skip_shared_base(tmp_path):
    db_path = str(tmp_path / "gcal_multi_sync_task.db")
    reset_engine()

    min_expected = (
        len(get_seed_pack("multi_mail_cal_sync_week_layout").needle_events)
        + len(get_seed_pack("multi_mail_cal_sync_actions").needle_events)
    )

    result = seed_database(
        scenario="task:multi-mail-cal-sync",
        seed=7,
        db_path=db_path,
        num_users=1,
    )

    assert result["events"] >= min_expected

    db = _open_db(db_path)
    try:
        summaries = {event.summary for event in db.query(Event).all()}
        assert "Budget Review — Q2" in summaries
        assert "Design Review with Priya" in summaries
        assert "Quarterly OKR Review" not in summaries
    finally:
        db.close()
        reset_engine()
