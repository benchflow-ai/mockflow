#!/usr/bin/env python3
"""Seed-time hook for auth-emergency-revocation.

Run AFTER ``auth --db <db> seed --scenario task:auth-emergency-revocation``
(see environment/Dockerfile). The generic task seeder only inserts users,
clients and consent records; this hook adds the two pieces the scenario needs
that needles cannot express on their own:

  1. One REAL access token per active session (so ``/_admin/state`` exposes a
     concrete, revocable token per client with a ``revoked`` flag — the thing
     the evaluator and the agent both check).
  2. The suspicious-sign-in audit trail for ``unknown-device-x``: a
     ``token_issued`` event ~2h ago from the rogue IP plus a couple of
     ``resource_access`` events against broad scopes — matching the security
     alert in Alex's inbox so the agent can correlate the two.

It then re-takes the ``initial`` snapshot so ``/_admin/diff`` starts empty.

Usage:  python3 seed_sessions.py /data/auth.db

Only mock_auth's stable, already-public helpers are used (the same ones the
built-in seed scenarios call): issue_access_token, log_event, the ORM models
and take_snapshot. No mock_auth source is modified.
"""

from __future__ import annotations

import importlib.util
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from mock_auth.audit import log_event
from mock_auth.models import (
    AccessToken,
    OAuthClient,
    User,
    get_session_factory,
    init_db,
)
from mock_auth.state.snapshots import take_snapshot
from mock_auth.token_service import issue_access_token


def _load_needles():
    needles_path = Path(__file__).resolve().parent / "needles.py"
    spec = importlib.util.spec_from_file_location("aer_needles", needles_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _iso_hours_ago(hours: float) -> str:
    return (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()


def main(db_path: str) -> None:
    n = _load_needles()

    init_db(db_path)
    SessionLocal = get_session_factory(db_path)
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.id == n.OWNER_USER_ID).first()
        if user is None:
            raise SystemExit(f"User {n.OWNER_USER_ID!r} not found — seed auth first.")
        clients = {c.client_id: c for c in db.query(OAuthClient).all()}

        for spec in n.SESSION_TOKENS:
            client = clients.get(spec["client_id"])
            if client is None:
                raise SystemExit(
                    f"Client {spec['client_id']!r} missing — check needles AUTH_CLIENTS."
                )
            issued_at = _iso_hours_ago(spec["hours_ago"])
            # 24h-lived token; long enough that all five are "active" at eval time.
            _token, row = issue_access_token(
                db, client, user, spec["scope"], expires_in=86400
            )
            row.created_at = issued_at
            ev = log_event(
                db, "token_issued", client_id=client.client_id, user_id=user.id,
                scope=spec["scope"], ip_address=spec["ip"], user_agent=spec["user_agent"],
                details={"grant": "authorization_code", "jti": row.jti, "seeded": True},
            )
            ev.created_at = issued_at

            if spec.get("suspicious"):
                # The rogue device's authorization request + what it did next.
                auth_ev = log_event(
                    db, "authorization_request", client_id=client.client_id,
                    user_id=user.id, scope=spec["scope"], ip_address=spec["ip"],
                    user_agent=spec["user_agent"],
                    details={"redirect_uri": f"http://{spec['ip']}/callback",
                             "seeded": True},
                )
                auth_ev.created_at = _iso_hours_ago(spec["hours_ago"] + 0.05)
                for offset, (route, scope_used) in enumerate([
                    ("/gmail/v1/users/{userId}/messages", "gmail.full"),
                    ("/drive/v3/files", "drive.full"),
                    ("/gmail/v1/users/{userId}/messages/{messageId}", "gmail.full"),
                ]):
                    ra = log_event(
                        db, "resource_access", client_id=client.client_id,
                        user_id=user.id, scope=scope_used, ip_address=spec["ip"],
                        user_agent=spec["user_agent"],
                        details={"scope_used": scope_used, "route": route,
                                 "seeded": True},
                    )
                    ra.created_at = _iso_hours_ago(
                        spec["hours_ago"] - 0.1 * (offset + 1)
                    )

        db.commit()
    finally:
        db.close()

    # Re-snapshot so the seeded tokens/audit are part of the "initial" baseline.
    try:
        take_snapshot("initial")
    except Exception as exc:  # pragma: no cover - snapshot is best-effort
        print(f"warning: could not re-take initial snapshot: {exc}", file=sys.stderr)

    print(f"seed_sessions: issued {len(n.SESSION_TOKENS)} session tokens "
          f"(suspicious={n.SUSPICIOUS_CLIENT_ID})")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: seed_sessions.py <db_path>")
    main(sys.argv[1])
