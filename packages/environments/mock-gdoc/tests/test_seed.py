"""Seed-path and scenario tests for mock-gdoc."""

from __future__ import annotations

from mock_gdoc.models import reset_engine
from mock_gdoc.seed.generator import seed_database


def test_task_seed_works_without_tasks_dir(monkeypatch, db_path):
    monkeypatch.delenv("TASKS_DIR", raising=False)
    reset_engine()

    stats = seed_database(
        scenario="task:gdoc-search-keyword-index",
        seed=42,
        db_path=db_path,
    )

    assert stats["users"] == 1
    assert stats["documents"] >= 1  # needle + filler docs; exact count varies with seed data
