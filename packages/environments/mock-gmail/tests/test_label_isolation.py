"""Regression tests for per-user labels (composite (id, user_id) primary key).

Previously labels.id was the table's sole primary key, so seeding system
labels for a second user raised IntegrityError (`seed --users 2` crashed) and
the multi_account scenario had to share global label rows (user_101 got no
per-user system labels).
"""

import pytest
from fastapi.testclient import TestClient

from mock_gmail.models import reset_engine, init_db
from mock_gmail.models.label import SYSTEM_LABELS
from mock_gmail.seed.generator import seed_database


def _make_client(db_path: str, scenario: str, num_users: int = 1) -> TestClient:
    reset_engine()
    seed_database(scenario=scenario, seed=42, db_path=db_path, num_users=num_users)
    init_db(db_path)
    from mock_gmail.api.app import app
    return TestClient(app)


@pytest.fixture
def two_user_client(db_path):
    """Client over a default-scenario DB seeded with TWO users."""
    with _make_client(db_path, scenario="default", num_users=2) as c:
        yield c
    reset_engine()


@pytest.fixture
def multi_account_client(db_path):
    """Client over the multi_account scenario (user1 work + user_101 personal)."""
    with _make_client(db_path, scenario="multi_account") as c:
        yield c
    reset_engine()


SYSTEM_LABEL_IDS = {label_id for label_id, _ in SYSTEM_LABELS}


class TestMultiUserSeed:
    def test_seed_two_users_succeeds(self, db_path):
        """seed --users 2 must not raise IntegrityError on system labels."""
        reset_engine()
        result = seed_database(scenario="default", seed=42, db_path=db_path, num_users=2)
        assert result["users"] == 2

    def test_each_user_has_own_system_labels(self, two_user_client):
        for user_id in ("user1", "user2"):
            resp = two_user_client.get(f"/gmail/v1/users/{user_id}/labels")
            assert resp.status_code == 200
            label_ids = {l["id"] for l in resp.json()["labels"]}
            assert SYSTEM_LABEL_IDS <= label_ids, (
                f"{user_id} is missing system labels: {SYSTEM_LABEL_IDS - label_ids}"
            )


class TestMultiAccountScenario:
    def test_user_101_exists_with_system_labels(self, multi_account_client):
        """labels.list for user_101 shows real per-user system labels."""
        resp = multi_account_client.get("/gmail/v1/users/user_101/labels")
        assert resp.status_code == 200
        labels = resp.json()["labels"]
        label_ids = {l["id"] for l in labels}
        assert SYSTEM_LABEL_IDS <= label_ids
        by_id = {l["id"]: l for l in labels}
        assert by_id["INBOX"]["type"] == "system"

    def test_user_101_label_counts_scoped_to_own_messages(self, multi_account_client):
        """labels.get counts must not leak the work account's messages."""
        resp = multi_account_client.get("/gmail/v1/users/user_101/labels/INBOX")
        assert resp.status_code == 200
        data = resp.json()
        # The personal account seed creates exactly 3 INBOX messages.
        assert data["messagesTotal"] == 3

        resp = multi_account_client.get("/gmail/v1/users/user_101/labels/SENT")
        assert resp.status_code == 200
        # ... and exactly 1 sent message.
        assert resp.json()["messagesTotal"] == 1

    def test_work_account_counts_unaffected_by_personal_account(self, multi_account_client):
        resp = multi_account_client.get("/gmail/v1/users/user1/labels/SENT")
        assert resp.status_code == 200
        work_sent = resp.json()["messagesTotal"]
        # user_101 has 1 SENT message; if counts leaked across users the work
        # total would include it. Verify by summing per-message ownership.
        resp = multi_account_client.get(
            "/gmail/v1/users/user1/messages",
            params={"labelIds": "SENT", "maxResults": 500, "includeSpamTrash": "true"},
        )
        assert resp.status_code == 200
        own_sent = resp.json()["resultSizeEstimate"]
        assert work_sent == own_sent


class TestCrossUserLabelIsolation:
    def test_user_labels_not_visible_to_other_users(self, two_user_client):
        resp = two_user_client.post(
            "/gmail/v1/users/user1/labels", json={"name": "Receipts"}
        )
        assert resp.status_code == 201
        label_id = resp.json()["id"]

        resp = two_user_client.get(f"/gmail/v1/users/user2/labels/{label_id}")
        assert resp.status_code == 404

        resp = two_user_client.get("/gmail/v1/users/user2/labels")
        assert label_id not in {l["id"] for l in resp.json()["labels"]}

    def test_same_named_labels_are_independent(self, two_user_client):
        id1 = two_user_client.post(
            "/gmail/v1/users/user1/labels", json={"name": "Projects"}
        ).json()["id"]
        id2 = two_user_client.post(
            "/gmail/v1/users/user2/labels", json={"name": "Projects"}
        ).json()["id"]

        # Deleting user1's label must not affect user2's.
        resp = two_user_client.delete(f"/gmail/v1/users/user1/labels/{id1}")
        assert resp.status_code == 200
        resp = two_user_client.get(f"/gmail/v1/users/user2/labels/{id2}")
        assert resp.status_code == 200
        assert resp.json()["name"] == "Projects"

    def test_system_label_counts_scoped_per_user(self, two_user_client):
        """labels.get INBOX counts only the requesting user's messages."""
        for user_id in ("user1", "user2"):
            label = two_user_client.get(f"/gmail/v1/users/{user_id}/labels/INBOX").json()
            msgs = two_user_client.get(
                f"/gmail/v1/users/{user_id}/messages",
                params={"labelIds": "INBOX", "maxResults": 500, "includeSpamTrash": "true"},
            ).json()
            assert label["messagesTotal"] == msgs["resultSizeEstimate"]

    def test_label_attach_and_delete_cleans_message_associations(self, two_user_client):
        label_id = two_user_client.post(
            "/gmail/v1/users/user1/labels", json={"name": "ToDelete"}
        ).json()["id"]
        msg_id = two_user_client.get("/gmail/v1/users/user1/messages").json()["messages"][0]["id"]
        resp = two_user_client.post(
            f"/gmail/v1/users/user1/messages/{msg_id}/modify",
            json={"addLabelIds": [label_id]},
        )
        assert resp.status_code == 200
        assert label_id in resp.json()["labelIds"]

        two_user_client.delete(f"/gmail/v1/users/user1/labels/{label_id}")
        resp = two_user_client.get(f"/gmail/v1/users/user1/messages/{msg_id}")
        assert label_id not in resp.json()["labelIds"]


class TestSnapshotsWithMultipleUsers:
    def test_state_dump_restore_roundtrip_preserves_per_user_labels(self, multi_account_client):
        """Snapshot state keys are unchanged and restore handles per-user labels."""
        from mock_gmail.state.snapshots import get_state_dump, _restore_from_state

        before = get_state_dump()
        assert "user_101" in before["users"]
        labels_before = {
            uid: sorted(l["id"] for l in u["labels"])
            for uid, u in before["users"].items()
        }
        # Per-user system labels present in the serialized state
        assert SYSTEM_LABEL_IDS <= set(labels_before["user_101"])

        _restore_from_state(before)

        after = get_state_dump()
        labels_after = {
            uid: sorted(l["id"] for l in u["labels"])
            for uid, u in after["users"].items()
        }
        assert labels_after == labels_before
        # Message label associations survive the round trip too
        msgs_before = {
            m["id"]: sorted(m["labelIds"])
            for m in before["users"]["user_101"]["messages"]
        }
        msgs_after = {
            m["id"]: sorted(m["labelIds"])
            for m in after["users"]["user_101"]["messages"]
        }
        assert msgs_after == msgs_before
