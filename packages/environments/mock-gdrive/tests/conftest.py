"""Shared test fixtures."""

import os
import sys
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# Make sibling auth-client importable for auth integration tests without a
# pyproject path dependency, which would break shallow task-image installs.
_client_pkg = Path(__file__).resolve().parents[3] / "auth-client"
if _client_pkg.is_dir():
    try:
        import env_0_auth_client  # noqa: F401
    except ImportError:
        sys.path.insert(0, str(_client_pkg))

from mock_gdrive.models.base import Base
from mock_gdrive.models import User, File, Permission, Comment, Reply, Revision, Change, Drive
from mock_gdrive.api.app import app
from mock_gdrive.api.deps import get_db


@pytest.fixture()
def db_session():
    """Create a fresh in-memory SQLite database for each test."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def _set_pragma(dbapi_conn, _):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, expire_on_commit=False)
    session = Session()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine)


@pytest.fixture()
def client(db_session):
    """FastAPI test client with overridden DB dependency."""
    def _override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture()
def seed_user(db_session):
    """Create a primary test user."""
    user = User(id="user_test", email="test@example.com", display_name="Test User")
    db_session.add(user)
    db_session.commit()
    return user


@pytest.fixture()
def seed_users(db_session):
    """Create multiple test users."""
    users = [
        User(id="user_alice", email="alice@example.com", display_name="Alice"),
        User(id="user_bob", email="bob@example.com", display_name="Bob"),
    ]
    for u in users:
        db_session.add(u)
    db_session.commit()
    return {u.email: u for u in users}


@pytest.fixture()
def seed_folder(db_session, seed_user):
    """Create a test folder owned by the primary user."""
    folder = File(
        id="folder_root",
        name="Test Folder",
        mime_type="application/vnd.google-apps.folder",
        owner_id=seed_user.id,
        last_modifying_user_id=seed_user.id,
    )
    db_session.add(folder)
    db_session.add(Permission(
        id="perm_folder_owner",
        file_id="folder_root",
        role="owner",
        type="user",
        email_address=seed_user.email,
        display_name=seed_user.display_name,
    ))
    db_session.commit()
    return folder


@pytest.fixture()
def seed_file(db_session, seed_user, seed_folder):
    """Create a test file inside the test folder."""
    f = File(
        id="file_test",
        name="Test Document",
        mime_type="application/vnd.google-apps.document",
        parent_id=seed_folder.id,
        owner_id=seed_user.id,
        last_modifying_user_id=seed_user.id,
        content_text="This is the test document content with some keywords for searching.",
    )
    db_session.add(f)
    db_session.add(Permission(
        id="perm_file_owner",
        file_id="file_test",
        role="owner",
        type="user",
        email_address=seed_user.email,
        display_name=seed_user.display_name,
    ))
    db_session.commit()
    return f
