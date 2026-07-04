"""State snapshots, reset, and diff functionality (gmail mechanism, table-based)."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy.orm import Session

from mock_auth.models import (
    AccessToken,
    AuthAuditLog,
    AuthorizationCode,
    ConsentRecord,
    DeviceCode,
    OAuthClient,
    RefreshToken,
    SigningKey,
    User,
    get_session_factory,
)
from mock_auth.models.base import _data_root


def _snapshots_base() -> Path:
    """Root for auth snapshots, honoring the DATA_DIR override."""
    return _data_root() / "snapshots_auth"


def _snapshots_dir() -> Path:
    """Per-database snapshot directory.

    Namespaced by a hash of the resolved DB path so concurrent auth
    instances (different --db files, e.g. parallel task validation runs)
    never overwrite each other's 'initial' snapshot.
    """
    import hashlib

    from mock_auth.models import get_engine

    try:
        db_path = str(get_engine().url.database or "memory")
    except Exception:
        db_path = "default"
    digest = hashlib.sha256(db_path.encode()).hexdigest()[:12]
    return _snapshots_base() / digest

# (state key, model, primary key attr) — order matters for FK-safe restore.
_TABLES = [
    ("users", User, "id"),
    ("oauth_clients", OAuthClient, "client_id"),
    ("signing_keys", SigningKey, "kid"),
    ("consent_records", ConsentRecord, "id"),
    ("authorization_codes", AuthorizationCode, "code"),
    ("access_tokens", AccessToken, "token_hash"),
    ("refresh_tokens", RefreshToken, "token_hash"),
    ("device_codes", DeviceCode, "device_code"),
    ("auth_audit_log", AuthAuditLog, "id"),
]


def _row_to_dict(obj) -> dict:
    return {
        col.name: getattr(obj, col.name)
        for col in obj.__table__.columns
    }


def get_state_dump() -> dict:
    """Full JSON state dump of every table."""
    SessionLocal = get_session_factory()
    db: Session = SessionLocal()
    try:
        state: dict = {}
        for key, model, pk in _TABLES:
            rows = db.query(model).all()
            state[key] = [_row_to_dict(r) for r in rows]
        state["timestamp"] = datetime.now(timezone.utc).isoformat()
        return state
    finally:
        db.close()


def take_snapshot(name: str) -> Path:
    """Save current state to a JSON snapshot (atomic write)."""
    snap_dir = _snapshots_dir()
    snap_dir.mkdir(parents=True, exist_ok=True)
    state = get_state_dump()
    path = snap_dir / f"{name}.json"
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(state, indent=2))
    os.replace(tmp, path)
    return path


def restore_snapshot(name: str) -> bool:
    """Restore DB from a snapshot. Returns True if successful."""
    path = _snapshots_dir() / f"{name}.json"
    if not path.exists():
        return False
    state = json.loads(path.read_text())
    _restore_from_state(state)
    return True


def _restore_from_state(state: dict):
    """Rebuild DB from a state dict."""
    from mock_auth.models import Base, get_engine

    engine = get_engine()
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)

    SessionLocal = get_session_factory()
    db = SessionLocal()
    try:
        # Flush per table: the models declare no relationship()s, so a single
        # flush may emit child INSERTs (e.g. consent_records) before their
        # users/oauth_clients parents and trip SQLite FK enforcement.
        for key, model, _pk in _TABLES:
            for row in state.get(key, []):
                db.add(model(**row))
            db.flush()
        db.commit()
    finally:
        db.close()


def get_diff(initial_state: dict | None = None) -> dict:
    """Compute per-table diff between the initial snapshot and the current state.

    Shape: {<table>: {"added": [...], "updated": [{pk, **changed_fields}], "deleted": [...]}}
    Tables with no changes are omitted.
    """
    current = get_state_dump()

    if initial_state is None:
        path = _snapshots_dir() / "initial.json"
        if path.exists():
            initial_state = json.loads(path.read_text())
        else:
            return {"error": "No initial snapshot found"}

    diff: dict = {}
    for key, _model, pk in _TABLES:
        curr_rows = {str(r[pk]): r for r in current.get(key, [])}
        init_rows = {str(r[pk]): r for r in initial_state.get(key, [])}

        table_diff = {"added": [], "updated": [], "deleted": []}
        for rid, row in curr_rows.items():
            if rid not in init_rows:
                table_diff["added"].append(row)
            elif row != init_rows[rid]:
                changes = {pk: row[pk]}
                for k, v in row.items():
                    if init_rows[rid].get(k) != v:
                        changes[k] = v
                table_diff["updated"].append(changes)
        for rid, row in init_rows.items():
            if rid not in curr_rows:
                table_diff["deleted"].append(row)

        if any(table_diff.values()):
            diff[key] = table_diff

    return diff
