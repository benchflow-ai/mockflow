import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

# Make the sibling auth-client package importable for the auth integration
# tests without a [tool.uv.sources] path dependency (a relative path source
# breaks `uv pip install -e .` from shallow copies like the /app directory task
# Dockerfiles use). No-op when auth-client is installed (Docker base image)
# or the repo layout is absent.
_client_pkg = Path(__file__).resolve().parents[3] / "auth-client"
if _client_pkg.is_dir():
    try:
        import env_0_auth_client  # noqa: F401
    except ImportError:
        sys.path.insert(0, str(_client_pkg))

from mock_stripe.models import init_db, reset_engine  # noqa: E402
from mock_stripe.seed.generator import seed_database  # noqa: E402


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
    from mock_stripe.api.app import app
    with TestClient(app) as c:
        yield c
    reset_engine()


@pytest.fixture
def fresh_client(db_path):
    """FastAPI test client with the 'fresh' scenario (API key only)."""
    reset_engine()
    seed_database(scenario="fresh", seed=42, db_path=db_path)
    reset_engine()
    init_db(db_path)
    from mock_stripe.api.app import app
    with TestClient(app) as c:
        yield c
    reset_engine()
