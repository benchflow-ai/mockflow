"""State snapshots, reset, and diff.

Generic over all models: each table is serialized as a list of plain column
dicts (values are str/int/bool/None — JSON columns are stored as text).
Snapshots live in <repo-root>/.data/snapshots_stripe/<name>.json (suffixed dir
so they never collide with other environment environments).
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import inspect as sa_inspect

from mock_stripe.models import MODEL_REGISTRY, Base, get_engine, get_session_factory
from mock_stripe.models.base import _data_root

SNAPSHOTS_DIR = _data_root() / "snapshots_stripe"


def _row_to_dict(obj) -> dict:
    mapper = sa_inspect(type(obj))
    return {c.key: getattr(obj, c.key) for c in mapper.columns}


def get_state_dump() -> dict:
    """Full state dump: every table as a list of column dicts."""
    SessionLocal = get_session_factory()
    db = SessionLocal()
    try:
        state: dict = {}
        for name, model in MODEL_REGISTRY:
            rows = db.query(model).order_by(model.seq.asc()).all()
            state[name] = [_row_to_dict(r) for r in rows]
        state["timestamp"] = datetime.now(timezone.utc).isoformat()
        return state
    finally:
        db.close()


def take_snapshot(name: str) -> Path:
    SNAPSHOTS_DIR.mkdir(parents=True, exist_ok=True)
    state = get_state_dump()
    path = SNAPSHOTS_DIR / f"{name}.json"
    path.write_text(json.dumps(state, indent=2))
    return path


def restore_snapshot(name: str) -> bool:
    path = SNAPSHOTS_DIR / f"{name}.json"
    if not path.exists():
        return False
    state = json.loads(path.read_text())
    _restore_from_state(state)
    return True


def _restore_from_state(state: dict):
    engine = get_engine()
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    SessionLocal = get_session_factory()
    db = SessionLocal()
    try:
        for name, model in MODEL_REGISTRY:
            for row in state.get(name, []):
                db.add(model(**row))
        db.commit()
    finally:
        db.close()


def _pk_field(name: str) -> str:
    return "key" if name == "idempotency_records" else "id"


def get_diff(initial_state: dict | None = None) -> dict:
    """Diff current state vs the 'initial' snapshot, per collection."""
    current = get_state_dump()

    if initial_state is None:
        path = SNAPSHOTS_DIR / "initial.json"
        if path.exists():
            initial_state = json.loads(path.read_text())
        else:
            return {"error": "No initial snapshot found"}

    diff: dict = {"added": {}, "updated": {}, "deleted": {}}
    for name, _model in MODEL_REGISTRY:
        pk = _pk_field(name)
        curr = {row[pk]: row for row in current.get(name, [])}
        init = {row[pk]: row for row in initial_state.get(name, [])}

        added = [row for rid, row in curr.items() if rid not in init]
        deleted = [row for rid, row in init.items() if rid not in curr]
        updated = []
        for rid, row in curr.items():
            if rid in init and row != init[rid]:
                changes = {k: v for k, v in row.items() if init[rid].get(k) != v}
                updated.append({pk: rid, **changes})

        if added:
            diff["added"][name] = added
        if updated:
            diff["updated"][name] = updated
        if deleted:
            diff["deleted"][name] = deleted
    return diff
