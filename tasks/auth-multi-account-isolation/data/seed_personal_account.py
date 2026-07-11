"""Build-time gmail seed extension for auth-multi-account-isolation.

The gmail `task:<name>` seeder only seeds the primary work user (user1), so
this script — run in environment/Dockerfile right after the gmail seed — adds
Alex's personal account (user_101, alex.personal@gmail.local) using the
env-owned fixture from gmail's `multi_account` scenario, then refreshes
the "initial" snapshot so /_admin/diff is empty before the agent acts.

Usage: python3 seed_personal_account.py [db_path]   (default /data/gmail.db)
"""

from __future__ import annotations

import random
import sys


def main() -> None:
    db_path = sys.argv[1] if len(sys.argv) > 1 else "/data/gmail.db"
    random.seed(42)  # _seed_personal_account randomizes message hours

    from mock_gmail.models import User, get_session_factory, init_db
    from mock_gmail.seed.generator import (
        PERSONAL_ACCOUNT_ID,
        _seed_personal_account,
    )
    from mock_gmail.state.snapshots import take_snapshot

    init_db(db_path)
    db = get_session_factory()()
    try:
        if db.query(User).filter(User.id == PERSONAL_ACCOUNT_ID).first() is None:
            _seed_personal_account(db)
            db.commit()
            print(f"Seeded personal account {PERSONAL_ACCOUNT_ID} into {db_path}")
        else:
            print(f"Personal account {PERSONAL_ACCOUNT_ID} already present")
    finally:
        db.close()

    path = take_snapshot("initial")
    print(f"Refreshed initial snapshot: {path}")


if __name__ == "__main__":
    main()
