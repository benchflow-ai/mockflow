"""Tests for the Gmail REST API."""

import pytest

from mock_gmail.api.mime import base64url_encode, build_rfc2822


def _raw(to="test@example.com", subject="Test", body="Test body"):
    """Build a raw base64url-encoded RFC 2822 payload for send/draft tests."""
    return base64url_encode(build_rfc2822(sender="me@test.com", to=to, subject=subject, body_plain=body))


class TestHealth:
    def test_health(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"


class TestProfile:
    def test_get_profile(self, client):
        resp = client.get("/gmail/v1/users/me/profile")
        assert resp.status_code == 200
        data = resp.json()
        assert "emailAddress" in data
        assert data["emailAddress"] == "alex@nexusai.com"
        assert data["messagesTotal"] > 0


class TestMessages:
    def test_list_messages(self, client):
        resp = client.get("/gmail/v1/users/me/messages")
        assert resp.status_code == 200
        data = resp.json()
        assert "messages" in data
        assert len(data["messages"]) > 0
        assert "id" in data["messages"][0]
        assert "threadId" in data["messages"][0]

    def test_get_message(self, client):
        # First list to get an ID
        resp = client.get("/gmail/v1/users/me/messages")
        msg_id = resp.json()["messages"][0]["id"]

        resp = client.get(f"/gmail/v1/users/me/messages/{msg_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == msg_id
        assert "payload" in data
        assert "labelIds" in data

    def test_get_message_not_found(self, client):
        resp = client.get("/gmail/v1/users/me/messages/nonexistent")
        assert resp.status_code == 404

    def test_send_message(self, client):
        resp = client.post("/gmail/v1/users/me/messages/send", json={
            "raw": _raw(subject="Test Subject", body="Test body content"),
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "SENT" in data["labelIds"]
        # Send returns minimal response: {id, threadId, labelIds}
        assert "snippet" not in data

    def test_modify_message_mark_read(self, client):
        # Find an unread message
        resp = client.get("/gmail/v1/users/me/messages?labelIds=UNREAD")
        messages = resp.json()["messages"]
        if not messages:
            pytest.skip("No unread messages")
        msg_id = messages[0]["id"]

        resp = client.post(f"/gmail/v1/users/me/messages/{msg_id}/modify", json={
            "removeLabelIds": ["UNREAD"],
        })
        assert resp.status_code == 200
        assert "UNREAD" not in resp.json()["labelIds"]

    def test_modify_message_star(self, client):
        resp = client.get("/gmail/v1/users/me/messages")
        msg_id = resp.json()["messages"][0]["id"]

        resp = client.post(f"/gmail/v1/users/me/messages/{msg_id}/modify", json={
            "addLabelIds": ["STARRED"],
        })
        assert resp.status_code == 200
        assert "STARRED" in resp.json()["labelIds"]

    def test_trash_message(self, client):
        resp = client.get("/gmail/v1/users/me/messages")
        msg_id = resp.json()["messages"][0]["id"]

        resp = client.post(f"/gmail/v1/users/me/messages/{msg_id}/trash")
        assert resp.status_code == 200
        assert "TRASH" in resp.json()["labelIds"]

    def test_untrash_message(self, client):
        resp = client.get("/gmail/v1/users/me/messages")
        msg_id = resp.json()["messages"][0]["id"]

        client.post(f"/gmail/v1/users/me/messages/{msg_id}/trash")
        resp = client.post(f"/gmail/v1/users/me/messages/{msg_id}/untrash")
        assert resp.status_code == 200
        assert "TRASH" not in resp.json()["labelIds"]

    def test_delete_message(self, client):
        resp = client.get("/gmail/v1/users/me/messages")
        msg_id = resp.json()["messages"][0]["id"]

        resp = client.delete(f"/gmail/v1/users/me/messages/{msg_id}")
        assert resp.status_code == 200

        resp = client.get(f"/gmail/v1/users/me/messages/{msg_id}")
        assert resp.status_code == 404

    def test_list_with_search(self, client):
        # Send a message with known content
        client.post("/gmail/v1/users/me/messages/send", json={
            "raw": _raw(subject="UniqueSearchTerm123"),
        })

        resp = client.get("/gmail/v1/users/me/messages?q=UniqueSearchTerm123")
        assert resp.status_code == 200
        assert resp.json()["resultSizeEstimate"] >= 1

    def test_batch_modify(self, client):
        resp = client.get("/gmail/v1/users/me/messages?maxResults=3")
        ids = [m["id"] for m in resp.json()["messages"][:3]]

        resp = client.post("/gmail/v1/users/me/messages/batchModify", json={
            "ids": ids,
            "addLabelIds": ["STARRED"],
        })
        assert resp.status_code == 200

    def test_send_with_raw(self, client):
        raw_bytes = build_rfc2822(
            sender="me@example.com",
            to="test@example.com",
            subject="Raw Test",
            body_plain="Sent via raw RFC 2822",
        )
        raw_b64 = base64url_encode(raw_bytes)
        resp = client.post("/gmail/v1/users/me/messages/send", json={"raw": raw_b64})
        assert resp.status_code == 200
        data = resp.json()
        assert "SENT" in data["labelIds"]
        # Send returns minimal response: {id, threadId, labelIds}
        assert "payload" not in data

    def test_get_message_format_raw(self, client):
        resp = client.get("/gmail/v1/users/me/messages")
        msg_id = resp.json()["messages"][0]["id"]

        resp = client.get(f"/gmail/v1/users/me/messages/{msg_id}?format=raw")
        assert resp.status_code == 200
        data = resp.json()
        assert data["raw"] is not None
        # Real Gmail: format=raw omits payload key entirely
        assert "payload" not in data

    def test_get_message_format_metadata(self, client):
        resp = client.get("/gmail/v1/users/me/messages")
        msg_id = resp.json()["messages"][0]["id"]

        resp = client.get(f"/gmail/v1/users/me/messages/{msg_id}?format=metadata")
        assert resp.status_code == 200
        data = resp.json()
        assert data["payload"] is not None
        # Real Gmail metadata payload has only {mimeType, headers}
        assert set(data["payload"].keys()) == {"mimeType", "headers"}

    def test_get_message_has_history_id(self, client):
        resp = client.get("/gmail/v1/users/me/messages")
        msg_id = resp.json()["messages"][0]["id"]

        resp = client.get(f"/gmail/v1/users/me/messages/{msg_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["historyId"] is not None

    def test_get_message_date_rfc2822_format(self, client):
        resp = client.get("/gmail/v1/users/me/messages")
        msg_id = resp.json()["messages"][0]["id"]

        resp = client.get(f"/gmail/v1/users/me/messages/{msg_id}")
        payload = resp.json()["payload"]
        date_header = next((h for h in payload["headers"] if h["name"] == "Date"), None)
        assert date_header is not None
        # RFC 2822 dates look like "Tue, 03 Mar 2026 12:06:43 +0000"
        # ISO 8601 would be "2026-03-03T12:06:43+00:00" — check it's not ISO
        from email.utils import parsedate_to_datetime
        parsedate_to_datetime(date_header["value"])  # raises if not RFC 2822

    def test_insert_message(self, client):
        raw_bytes = build_rfc2822(
            sender="external@example.com",
            to="me@example.com",
            subject="Inserted Message",
            body_plain="This was inserted directly",
        )
        raw_b64 = base64url_encode(raw_bytes)
        resp = client.post("/gmail/v1/users/me/messages", json={
            "raw": raw_b64,
            "labelIds": ["INBOX"],
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"]

    def test_import_message(self, client):
        raw_bytes = build_rfc2822(
            sender="external@example.com",
            to="me@example.com",
            subject="Imported Message",
            body_plain="This was imported",
        )
        raw_b64 = base64url_encode(raw_bytes)
        resp = client.post("/gmail/v1/users/me/messages/import", json={
            "raw": raw_b64,
        })
        assert resp.status_code == 200


class TestThreads:
    def test_list_threads(self, client):
        resp = client.get("/gmail/v1/users/me/threads")
        assert resp.status_code == 200
        data = resp.json()
        assert "threads" in data
        assert len(data["threads"]) > 0

    def test_get_thread(self, client):
        resp = client.get("/gmail/v1/users/me/threads")
        thread_id = resp.json()["threads"][0]["id"]

        resp = client.get(f"/gmail/v1/users/me/threads/{thread_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == thread_id
        assert "messages" in data
        assert len(data["messages"]) > 0


class TestLabels:
    def test_list_labels(self, client):
        resp = client.get("/gmail/v1/users/me/labels")
        assert resp.status_code == 200
        data = resp.json()
        assert "labels" in data
        label_ids = [l["id"] for l in data["labels"]]
        assert "INBOX" in label_ids
        assert "SENT" in label_ids
        assert "TRASH" in label_ids

    def test_create_label(self, client):
        resp = client.post("/gmail/v1/users/me/labels", json={
            "name": "Test Label",
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "Test Label"
        # Real Gmail create response doesn't include 'type'
        assert "type" not in data

    def test_delete_label(self, client):
        # Create then delete
        resp = client.post("/gmail/v1/users/me/labels", json={"name": "Temporary"})
        label_id = resp.json()["id"]

        resp = client.delete(f"/gmail/v1/users/me/labels/{label_id}")
        assert resp.status_code == 200

    def test_cannot_delete_system_label(self, client):
        resp = client.delete("/gmail/v1/users/me/labels/INBOX")
        assert resp.status_code == 400


class TestDrafts:
    def test_create_draft(self, client):
        resp = client.post("/gmail/v1/users/me/drafts", json={
            "message": {
                "raw": _raw(subject="Draft Subject", body="Draft body"),
            }
        })
        assert resp.status_code == 201
        data = resp.json()
        assert "id" in data
        assert "message" in data

    def test_list_drafts(self, client):
        resp = client.get("/gmail/v1/users/me/drafts")
        assert resp.status_code == 200
        assert "drafts" in resp.json()

    def test_send_draft(self, client):
        # Create draft first
        resp = client.post("/gmail/v1/users/me/drafts", json={
            "message": {
                "raw": _raw(subject="Send Draft Test", body="Sending this draft"),
            }
        })
        draft_id = resp.json()["id"]

        resp = client.post("/gmail/v1/users/me/drafts/send", json={"id": draft_id})
        assert resp.status_code == 200
        assert "SENT" in resp.json()["labelIds"]


class TestMessagesBatchDelete:
    def test_batch_delete(self, client):
        # Send 2 messages so we have known IDs to delete
        ids = []
        for i in range(2):
            resp = client.post("/gmail/v1/users/me/messages/send", json={
                "raw": _raw(subject=f"BatchDel {i}", body="to be deleted"),
            })
            ids.append(resp.json()["id"])

        resp = client.post("/gmail/v1/users/me/messages/batchDelete", json={"ids": ids})
        assert resp.status_code == 200

        # Verify all messages are gone
        for msg_id in ids:
            resp = client.get(f"/gmail/v1/users/me/messages/{msg_id}")
            assert resp.status_code == 404


class TestAttachments:
    def test_get_attachment(self, client):
        """Insert an attachment directly via ORM and verify the API returns it."""
        from mock_gmail.models import get_session_factory, Attachment, Message
        db = get_session_factory()()

        msg = db.query(Message).first()
        att = Attachment(
            id="att_test_001",
            message_id=msg.id,
            filename="report.pdf",
            mime_type="application/pdf",
            size=1234,
            data="dGVzdCBhdHRhY2htZW50IGRhdGE=",
        )
        db.add(att)
        db.commit()

        resp = client.get(
            f"/gmail/v1/users/me/messages/{msg.id}/attachments/att_test_001"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["attachmentId"] == "att_test_001"
        assert data["size"] == 1234
        assert data["data"] == "dGVzdCBhdHRhY2htZW50IGRhdGE="

    def test_get_attachment_not_found(self, client):
        resp = client.get(
            "/gmail/v1/users/me/messages/nonexistent/attachments/nonexistent"
        )
        assert resp.status_code == 404


class TestThreadsMutations:
    def test_modify_thread(self, client):
        resp = client.get("/gmail/v1/users/me/threads")
        thread_id = resp.json()["threads"][0]["id"]

        resp = client.post(f"/gmail/v1/users/me/threads/{thread_id}/modify", json={
            "addLabelIds": ["STARRED"],
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == thread_id
        # All messages in thread should now have STARRED
        for msg in data["messages"]:
            assert "STARRED" in msg["labelIds"]

    def test_modify_thread_remove_label(self, client):
        resp = client.get("/gmail/v1/users/me/threads")
        thread_id = resp.json()["threads"][0]["id"]

        # Add then remove
        client.post(f"/gmail/v1/users/me/threads/{thread_id}/modify", json={
            "addLabelIds": ["STARRED"],
        })
        resp = client.post(f"/gmail/v1/users/me/threads/{thread_id}/modify", json={
            "removeLabelIds": ["STARRED"],
        })
        assert resp.status_code == 200
        for msg in resp.json()["messages"]:
            assert "STARRED" not in msg["labelIds"]

    def test_modify_thread_not_found(self, client):
        resp = client.post("/gmail/v1/users/me/threads/nonexistent/modify", json={
            "addLabelIds": ["STARRED"],
        })
        assert resp.status_code == 404

    def test_trash_thread(self, client):
        resp = client.get("/gmail/v1/users/me/threads")
        thread_id = resp.json()["threads"][0]["id"]

        resp = client.post(f"/gmail/v1/users/me/threads/{thread_id}/trash")
        assert resp.status_code == 200
        for msg in resp.json()["messages"]:
            assert "TRASH" in msg["labelIds"]

    def test_untrash_thread(self, client):
        resp = client.get("/gmail/v1/users/me/threads")
        thread_id = resp.json()["threads"][0]["id"]

        client.post(f"/gmail/v1/users/me/threads/{thread_id}/trash")
        resp = client.post(f"/gmail/v1/users/me/threads/{thread_id}/untrash")
        assert resp.status_code == 200
        for msg in resp.json()["messages"]:
            assert "TRASH" not in msg["labelIds"]

    def test_delete_thread(self, client):
        # Pick a mailbox thread; deterministic date ordering puts the draft first.
        resp = client.get("/gmail/v1/users/me/threads?labelIds=INBOX")
        thread_id = resp.json()["threads"][0]["id"]

        resp = client.delete(f"/gmail/v1/users/me/threads/{thread_id}")
        assert resp.status_code == 200

        resp = client.get(f"/gmail/v1/users/me/threads/{thread_id}")
        assert resp.status_code == 404

    def test_delete_thread_not_found(self, client):
        resp = client.delete("/gmail/v1/users/me/threads/nonexistent")
        assert resp.status_code == 404


class TestLabelsExtended:
    def test_get_label(self, client):
        resp = client.get("/gmail/v1/users/me/labels/INBOX")
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == "INBOX"
        # labels.get includes counts
        assert "messagesTotal" in data

    def test_get_label_not_found(self, client):
        resp = client.get("/gmail/v1/users/me/labels/NONEXISTENT_LABEL")
        assert resp.status_code == 404

    def test_update_label(self, client):
        # Create a user label first
        resp = client.post("/gmail/v1/users/me/labels", json={"name": "Update Test"})
        label_id = resp.json()["id"]

        resp = client.put(f"/gmail/v1/users/me/labels/{label_id}", json={
            "name": "Updated Name",
            "messageListVisibility": "hide",
        })
        assert resp.status_code == 200
        assert resp.json()["name"] == "Updated Name"

    def test_update_system_label_fails(self, client):
        resp = client.put("/gmail/v1/users/me/labels/INBOX", json={
            "name": "My Inbox",
        })
        assert resp.status_code == 400

    def test_patch_label(self, client):
        resp = client.post("/gmail/v1/users/me/labels", json={"name": "Patch Test"})
        label_id = resp.json()["id"]

        resp = client.patch(f"/gmail/v1/users/me/labels/{label_id}", json={
            "name": "Patched Name",
        })
        assert resp.status_code == 200
        assert resp.json()["name"] == "Patched Name"

    def test_patch_label_not_found(self, client):
        resp = client.patch("/gmail/v1/users/me/labels/NONEXISTENT", json={
            "name": "Whatever",
        })
        assert resp.status_code == 404


class TestDraftsExtended:
    def test_get_draft(self, client):
        # Create a draft first
        resp = client.post("/gmail/v1/users/me/drafts", json={
            "message": {
                "raw": _raw(subject="Get Draft Test", body="Draft body content"),
            }
        })
        draft_id = resp.json()["id"]

        resp = client.get(f"/gmail/v1/users/me/drafts/{draft_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == draft_id
        assert "message" in data
        assert data["message"]["payload"] is not None

    def test_get_draft_not_found(self, client):
        resp = client.get("/gmail/v1/users/me/drafts/nonexistent")
        assert resp.status_code == 404

    def test_update_draft(self, client):
        # Create draft
        resp = client.post("/gmail/v1/users/me/drafts", json={
            "message": {
                "raw": _raw(subject="Original Subject", body="Original body"),
            }
        })
        draft_id = resp.json()["id"]

        # Update it
        resp = client.put(f"/gmail/v1/users/me/drafts/{draft_id}", json={
            "message": {
                "raw": _raw(subject="Updated Subject", body="Updated body"),
            }
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == draft_id

        # Verify via get
        resp = client.get(f"/gmail/v1/users/me/drafts/{draft_id}")
        msg = resp.json()["message"]
        subject_header = next(
            h for h in msg["payload"]["headers"] if h["name"] == "Subject"
        )
        assert subject_header["value"] == "Updated Subject"

    def test_update_draft_not_found(self, client):
        resp = client.put("/gmail/v1/users/me/drafts/nonexistent", json={
            "message": {"raw": _raw(subject="X", body="Y")}
        })
        assert resp.status_code == 404

    def test_delete_draft(self, client):
        # Create draft
        resp = client.post("/gmail/v1/users/me/drafts", json={
            "message": {
                "raw": _raw(subject="Delete Draft Test", body="Will be deleted"),
            }
        })
        draft_id = resp.json()["id"]

        resp = client.delete(f"/gmail/v1/users/me/drafts/{draft_id}")
        assert resp.status_code == 200

        resp = client.get(f"/gmail/v1/users/me/drafts/{draft_id}")
        assert resp.status_code == 404

    def test_delete_draft_not_found(self, client):
        resp = client.delete("/gmail/v1/users/me/drafts/nonexistent")
        assert resp.status_code == 404


class TestHistory:
    def test_list_history(self, client):
        resp = client.get("/gmail/v1/users/me/profile")
        history_id = resp.json()["historyId"]

        # Perform an action to generate history
        resp = client.get("/gmail/v1/users/me/messages")
        msg_id = resp.json()["messages"][0]["id"]
        client.post(f"/gmail/v1/users/me/messages/{msg_id}/modify", json={
            "addLabelIds": ["STARRED"],
        })

        resp = client.get(
            f"/gmail/v1/users/me/history?startHistoryId={history_id}"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "history" in data
        assert "historyId" in data

    def test_list_history_invalid_start_id(self, client):
        resp = client.get(
            "/gmail/v1/users/me/history?startHistoryId=invalid"
        )
        assert resp.status_code == 400


class TestSettingsImap:
    def test_get_imap_default(self, client):
        resp = client.get("/gmail/v1/users/me/settings/imap")
        assert resp.status_code == 200
        data = resp.json()
        assert data["enabled"] is False
        assert data["autoExpunge"] is True

    def test_update_imap(self, client):
        resp = client.put("/gmail/v1/users/me/settings/imap", json={
            "enabled": True,
            "autoExpunge": False,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["enabled"] is True
        assert data["autoExpunge"] is False

        # Verify persistence
        resp = client.get("/gmail/v1/users/me/settings/imap")
        assert resp.json()["enabled"] is True


class TestSettingsPop:
    def test_get_pop_default(self, client):
        resp = client.get("/gmail/v1/users/me/settings/pop")
        assert resp.status_code == 200
        data = resp.json()
        assert data["accessWindow"] == "disabled"

    def test_update_pop(self, client):
        resp = client.put("/gmail/v1/users/me/settings/pop", json={
            "accessWindow": "allMail",
        })
        assert resp.status_code == 200
        assert resp.json()["accessWindow"] == "allMail"


class TestSettingsLanguage:
    def test_get_language_default(self, client):
        resp = client.get("/gmail/v1/users/me/settings/language")
        assert resp.status_code == 200
        assert resp.json()["displayLanguage"] == "en"

    def test_update_language(self, client):
        resp = client.put("/gmail/v1/users/me/settings/language", json={
            "displayLanguage": "ja",
        })
        assert resp.status_code == 200
        assert resp.json()["displayLanguage"] == "ja"


class TestAdmin:
    def test_state(self, client):
        resp = client.get("/_admin/state")
        assert resp.status_code == 200
        data = resp.json()
        assert "users" in data
        assert "user1" in data["users"]

    def test_diff(self, client):
        resp = client.get("/_admin/diff")
        assert resp.status_code == 200

    def test_action_log(self, client):
        # Make some calls first
        client.get("/gmail/v1/users/me/messages")
        resp = client.get("/_admin/action_log")
        assert resp.status_code == 200
        assert "entries" in resp.json()

    def test_snapshot_and_restore(self, client):
        resp = client.post("/_admin/snapshot/test_snap")
        assert resp.status_code == 200

        resp = client.post("/_admin/restore/test_snap")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    def test_reset(self, client):
        resp = client.post("/_admin/reset")
        assert resp.status_code == 200


class TestTasks:
    def test_list_tasks(self):
        from mock_gmail.tasks import list_tasks
        tasks = list_tasks()
        assert len(tasks) > 0
        assert "targeted-promo-delete" in tasks
        assert "ambiguous-cleanup" in tasks

    def test_get_task(self):
        from mock_gmail.tasks import get_task
        task = get_task("targeted-promo-delete")
        assert task is not None
        assert task.category == "mixed"
        assert task.instruction
