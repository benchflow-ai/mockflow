"""DATA_DIR override: the .data root is configurable via env var.

Regression guard for the fixed ``.parent``-hop default breaking when the package
is relocated to a shallower path. Setting ``DATA_DIR`` must redirect both the
database file and the snapshots directory; leaving it unset must keep the exact
historical default.
"""

from __future__ import annotations

from mock_auth.models import reset_engine, resolve_db_path
from mock_auth.models.base import _data_root
from mock_auth.seed.generator import seed_database


def test_data_root_defaults_without_env(monkeypatch):
    """With DATA_DIR unset, the data root is the <repo-root>/.data default."""
    monkeypatch.delenv("DATA_DIR", raising=False)
    root = _data_root()
    assert root.name == ".data"
    # resolve_db_path(None) keeps the historical default db location.
    assert resolve_db_path(None) == root / "mock_auth.db"


def test_env_0_data_dir_redirects_data_root(tmp_path, monkeypatch):
    """Setting DATA_DIR redirects db + snapshot files under it."""
    data_dir = tmp_path / "custom_data"
    monkeypatch.setenv("DATA_DIR", str(data_dir))

    # The helper and db-path resolution both honor the override.
    assert _data_root() == data_dir
    assert resolve_db_path(None) == data_dir / "mock_auth.db"

    from mock_auth import scheduler

    reset_engine()
    try:
        # db_path=None -> resolves under the overridden data root.
        seed_database(scenario="default", seed=42)

        db_file = data_dir / "mock_auth.db"
        assert db_file.exists(), (
            f"db did not land under override: {list(data_dir.rglob('*'))}"
        )

        # seed_database also writes the 'initial' snapshot; it must follow the override.
        snap_root = data_dir / "snapshots_auth"
        assert snap_root.exists()
        assert list(snap_root.rglob("initial.json")), "initial snapshot not under override"
    finally:
        scheduler.clear()
        reset_engine()
