"""Shared pytest fixtures for mock-gcal."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

_PKG_ROOT = Path(__file__).resolve().parent.parent
if str(_PKG_ROOT) not in sys.path:
    sys.path.insert(0, str(_PKG_ROOT))

# Make sibling auth-client importable for auth integration tests without a
# pyproject path dependency, which would break shallow task-image installs.
_client_pkg = Path(__file__).resolve().parents[3] / "auth-client"
if _client_pkg.is_dir():
    try:
        import env_0_auth_client  # noqa: F401
    except ImportError:
        sys.path.insert(0, str(_client_pkg))

from mock_gcal.models import init_db, reset_engine
from mock_gcal.seed.generator import seed_database


@pytest.fixture
def db_path(tmp_path):
    """Temporary database path."""
    path = str(tmp_path / "test.db")
    yield path
    reset_engine()


@pytest.fixture
def seeded_db(db_path):
    """Seed a temporary database."""
    reset_engine()
    seed_database(scenario="default", seed=42, db_path=db_path)
    return db_path


@pytest.fixture
def client(seeded_db):
    """FastAPI test client with a seeded database."""
    reset_engine()
    init_db(seeded_db)
    from mock_gcal.api.app import app

    with TestClient(app) as test_client:
        yield test_client

    reset_engine()
