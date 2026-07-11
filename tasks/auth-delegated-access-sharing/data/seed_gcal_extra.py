#!/usr/bin/env python3
"""Post-seed augmentation for auth-delegated-access-sharing.

gcal only seeds the fixed CALENDAR_TEMPLATES, and the per-task gcal seeder
cannot create new calendars (needle events only land in existing calendars).
This task needs a named "Project Plans" calendar owned by user1 to share, so we
create it here AFTER `gcal --db <path> seed --scenario task:...`, then
re-snapshot "initial" so the calendar is part of the reset/diff baseline.

Usage:  python3 seed_gcal_extra.py /data/gcal.db
"""

from __future__ import annotations

import sys

# Calendar definition (kept in sync with data/needles.py constants).
CAL_ID = "projectplans-alex@nexusai.com"
CAL_SUMMARY = "Project Plans"
CAL_DESCRIPTION = "Roadmap planning, milestones, and delivery dates"
OWNER_USER_ID = "user1"


def _acl_etag(calendar_id: str, scope_value: str, role: str) -> str:
    return f'"{calendar_id}:user:{scope_value}:{role}"'


def main(db_path: str) -> None:
    # Imported lazily so data/needles.py (which lives next to this file and is
    # imported by the auth/gdrive seeders too) never triggers a mock_gcal import.
    from mock_gcal.models import (
        AclRule,
        Calendar,
        User,
        get_session_factory,
        init_db,
        reset_engine,
    )
    from mock_gcal.state.snapshots import take_snapshot

    reset_engine()
    init_db(db_path)
    db = get_session_factory(db_path)()
    try:
        user = db.query(User).filter(User.id == OWNER_USER_ID).first()
        if user is None:
            raise SystemExit(
                f"user {OWNER_USER_ID!r} not found — seed gcal before running "
                "seed_gcal_extra.py"
            )

        if db.query(Calendar).filter(Calendar.id == CAL_ID).first() is None:
            db.add(
                Calendar(
                    id=CAL_ID,
                    user_id=user.id,
                    summary=CAL_SUMMARY,
                    description=CAL_DESCRIPTION,
                    location="",
                    timezone="America/Los_Angeles",
                    access_role="owner",
                    is_primary=False,
                    selected=True,
                    hidden=False,
                    summary_override="",
                    auto_accept_invitations=False,
                    color_id="9",
                )
            )
            # Owner ACL rule representing Alex's own access (mirrors the seeder).
            db.add(
                AclRule(
                    id=f"{CAL_ID}:user:{user.email_address}",
                    calendar_id=CAL_ID,
                    scope_type="user",
                    scope_value=user.email_address,
                    role="owner",
                    etag=_acl_etag(CAL_ID, user.email_address, "owner"),
                )
            )
            db.commit()

        # Re-baseline so /_admin/reset and /_admin/diff include the calendar.
        take_snapshot("initial")
        print(f"seeded calendar {CAL_SUMMARY!r} ({CAL_ID}) for {OWNER_USER_ID}")
    finally:
        db.close()


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "/data/gcal.db")
