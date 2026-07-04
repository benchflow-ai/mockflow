"""Test fixtures."""

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

# Make sibling auth-client importable for auth integration tests without a
# pyproject path dependency, which would break shallow task-image installs.
_client_pkg = Path(__file__).resolve().parents[3] / "auth-client"
if _client_pkg.is_dir():
    try:
        import env_0_auth_client  # noqa: F401
    except ImportError:
        sys.path.insert(0, str(_client_pkg))

from mock_gmail.models import reset_engine, init_db, get_session_factory
from mock_gmail.seed.generator import seed_database


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
    """FastAPI test client with seeded database."""
    reset_engine()
    init_db(seeded_db)
    from mock_gmail.api.app import app
    with TestClient(app) as c:
        yield c
    reset_engine()
