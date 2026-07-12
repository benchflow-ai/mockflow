"""Conformance tests — verify mock response shapes match real Gmail golden fixtures.

These tests don't compare exact values (IDs, timestamps differ) but verify that
the response structure (keys present/absent, types, nesting) matches real Gmail.
"""

import json
from pathlib import Path

import pytest

from mock_gmail.api.mime import base64url_encode, build_rfc2822

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "real_gmail"


def _raw(to="test@example.com", subject="Test", body="Test body"):
    """Build a raw base64url-encoded RFC 2822 payload for send/draft tests."""
    return base64url_encode(build_rfc2822(sender="me@test.com", to=to, subject=subject, body_plain=body))


def load_fixture(name: str) -> dict:
    path = FIXTURES_DIR / name
    if not path.exists():
        pytest.skip(f"Golden fixture {name} not found")
    data = json.loads(path.read_text())
    data.pop("_captured_at", None)
    return data


def _assert_shape(real, mock, path="", strict=True):
    """Recursively assert mock response shape matches real fixture.

    Checks:
    - Missing keys: real_keys - mock_keys (always)
    - Extra keys: mock_keys - real_keys (when strict=True)
    - Type mismatches at leaf nodes
    """
    if isinstance(real, dict) and isinstance(mock, dict):
        real_keys = set(real.keys())
        mock_keys = set(mock.keys())
        missing = real_keys - mock_keys
        assert not missing, f"Mock MISSING keys at {path or 'root'}: {missing}"
        if strict:
            extra = mock_keys - real_keys
            assert not extra, f"Mock has EXTRA keys at {path or 'root'}: {extra}"
        for key in real_keys & mock_keys:
            _assert_shape(real[key], mock[key], f"{path}.{key}" if path else key, strict)
    elif isinstance(real, list) and isinstance(mock, list):
        if real and not mock:
            pytest.fail(f"Mock list is empty at {path}, real fixture has items")
        if not real:
            return
        for idx, item in enumerate(mock):
            _assert_any_shape(real, item, f"{path}[{idx}]", strict)
    else:
        if real is not None and mock is not None:
            real_type = type(real).__name__
            mock_type = type(mock).__name__
            assert real_type == mock_type, f"TYPE MISMATCH at {path}: real={real_type}, mock={mock_type}"


def _assert_any_shape(real_items: list, mock_item, path: str, strict: bool) -> None:
    errors = []
    for real_item in real_items:
        try:
            _assert_shape(real_item, mock_item, path, strict)
            return
        except AssertionError as exc:
            errors.append(str(exc))
    pytest.fail(f"Mock item at {path} matches no fixture item shape: {'; '.join(errors)}")


def _assert_thread_message_core_types(message: dict) -> None:
    for key in ("id", "threadId", "snippet", "historyId", "internalDate"):
        assert isinstance(message[key], str)
    assert isinstance(message["labelIds"], list)
    assert all(isinstance(label_id, str) for label_id in message["labelIds"])
    assert isinstance(message["sizeEstimate"], int)


class TestProfileConformance:
    def test_profile_keys(self, client):
        """Profile response has same keys as real Gmail."""
        real = load_fixture("profile.json")
        resp = client.get("/gmail/v1/users/me/profile")
        mock = resp.json()
        assert set(real.keys()) == set(mock.keys())


class TestErrorConformance:
    def test_error_400_envelope_shape(self, client):
        """400 error has Gmail error envelope: {error: {code, message, errors, status}}."""
        real = load_fixture("error_invalid_message_send.json")
        # Request a non-existent message to trigger an error
        resp = client.get("/gmail/v1/users/me/messages/NONEXISTENT_ID_000")
        mock = resp.json()

        assert resp.status_code in (400, 404)
        assert "error" in mock
        real_error_keys = set(real["error"].keys())
        mock_error_keys = set(mock["error"].keys())
        assert mock_error_keys == real_error_keys

        # Each error item has {message, domain, reason}
        assert len(mock["error"]["errors"]) > 0
        real_item_keys = set(real["error"]["errors"][0].keys())
        mock_item_keys = set(mock["error"]["errors"][0].keys())
        assert mock_item_keys == real_item_keys

    def test_error_404_envelope_shape(self, client):
        """404 error has same envelope structure as real Gmail errors."""
        real = load_fixture("error_message_not_found.json")
        resp = client.get("/gmail/v1/users/me/messages/NONEXISTENT_ID_000")
        mock = resp.json()

        assert "error" in mock
        assert "code" in mock["error"]
        assert "message" in mock["error"]
        assert "errors" in mock["error"]
        assert "status" in mock["error"]
        # Error items have consistent shape
        real_item_keys = set(real["error"]["errors"][0].keys())
        mock_item_keys = set(mock["error"]["errors"][0].keys())
        assert mock_item_keys == real_item_keys


class TestLabelsConformance:
    def test_labels_list_structure(self, client):
        """labels.list response has 'labels' key with correct per-label structure."""
        real = load_fixture("labels_list.json")
        resp = client.get("/gmail/v1/users/me/labels")
        mock = resp.json()

        assert "labels" in mock
        assert len(mock["labels"]) > 0

        # Every real label has at least {id, name, type}
        for real_label in real["labels"]:
            assert "id" in real_label
            assert "name" in real_label
            assert "type" in real_label

        # Every mock label should also have at least {id, name, type}
        for mock_label in mock["labels"]:
            assert "id" in mock_label
            assert "name" in mock_label
            assert "type" in mock_label

    def test_chat_label_exists(self, client):
        """CHAT label exists in labels.list."""
        resp = client.get("/gmail/v1/users/me/labels")
        label_ids = [l["id"] for l in resp.json()["labels"]]
        assert "CHAT" in label_ids

    def test_system_label_visibility_patterns(self, client):
        """System labels match real Gmail's visibility pattern."""
        real = load_fixture("labels_list.json")
        resp = client.get("/gmail/v1/users/me/labels")
        mock_labels = {l["id"]: l for l in resp.json()["labels"]}

        # Labels that should have NO visibility fields (matching real Gmail)
        no_visibility = {"SENT", "INBOX", "DRAFT", "STARRED", "UNREAD"}
        # Labels that should have hide/labelHide
        hidden = {"CHAT", "IMPORTANT", "TRASH", "SPAM",
                  "CATEGORY_FORUMS", "CATEGORY_UPDATES",
                  "CATEGORY_PERSONAL", "CATEGORY_PROMOTIONS", "CATEGORY_SOCIAL"}

        for label_id in no_visibility:
            if label_id in mock_labels:
                label = mock_labels[label_id]
                assert "messageListVisibility" not in label, \
                    f"{label_id} should not have messageListVisibility"
                assert "labelListVisibility" not in label, \
                    f"{label_id} should not have labelListVisibility"

        for label_id in hidden:
            if label_id in mock_labels:
                label = mock_labels[label_id]
                assert label.get("messageListVisibility") == "hide", \
                    f"{label_id} should have messageListVisibility=hide"
                assert label.get("labelListVisibility") == "labelHide", \
                    f"{label_id} should have labelListVisibility=labelHide"

    def test_labels_list_omits_counts(self, client):
        """labels.list omits count fields (messagesTotal, etc.) for system labels."""
        resp = client.get("/gmail/v1/users/me/labels")
        for label in resp.json()["labels"]:
            if label["type"] == "system":
                assert "messagesTotal" not in label
                assert "messagesUnread" not in label
                assert "threadsTotal" not in label
                assert "threadsUnread" not in label

    def test_label_get_inbox_shape(self, client):
        """labels.get for INBOX returns counts and correct key set."""
        real = load_fixture("label_get_inbox.json")
        resp = client.get("/gmail/v1/users/me/labels/INBOX")
        mock = resp.json()

        assert set(mock.keys()) == set(real.keys())
        assert mock["id"] == "INBOX"
        assert mock["type"] == "system"
        assert "messagesTotal" in mock
        assert "threadsTotal" in mock

    def test_label_create_response_shape(self, client):
        """labels.create returns sparse {id, name, messageListVisibility, labelListVisibility}."""
        real = load_fixture("label_create_response.json")
        resp = client.post("/gmail/v1/users/me/labels", json={
            "name": "ConformanceTestLabel",
        })
        assert resp.status_code == 201
        mock = resp.json()

        assert set(mock.keys()) == set(real.keys())
        assert "id" in mock
        assert "name" in mock

    def test_label_update_response_shape(self, client):
        """labels.update (PUT) returns sparse shape matching real Gmail."""
        real = load_fixture("label_update_response.json")
        # Create a label first, then update it
        create_resp = client.post("/gmail/v1/users/me/labels", json={
            "name": "UpdateTestLabel",
        })
        label_id = create_resp.json()["id"]

        resp = client.put(f"/gmail/v1/users/me/labels/{label_id}", json={
            "name": "UpdateTestLabelRenamed",
        })
        mock = resp.json()

        assert set(mock.keys()) == set(real.keys())

    def test_label_patch_response_shape(self, client):
        """labels.patch returns full label with counts."""
        real = load_fixture("label_patch_response.json")
        # Create a label first, then patch it
        create_resp = client.post("/gmail/v1/users/me/labels", json={
            "name": "PatchTestLabel",
        })
        label_id = create_resp.json()["id"]

        resp = client.patch(f"/gmail/v1/users/me/labels/{label_id}", json={
            "name": "PatchTestLabelPatched",
        })
        mock = resp.json()

        # Real patch response has these keys; mock may include extra like 'color'
        assert set(real.keys()).issubset(set(mock.keys()))
        assert "type" in mock
        assert "messagesTotal" in mock
        assert "threadsTotal" in mock


class TestMessagesConformance:
    def test_send_returns_minimal(self, client):
        """messages.send returns only {id, threadId, labelIds}."""
        real = load_fixture("message_send_response.json")
        resp = client.post("/gmail/v1/users/me/messages/send", json={
            "raw": _raw(subject="Conformance Test", body="Test body"),
        })
        mock = resp.json()

        # Same key set as real
        assert set(mock.keys()) == set(real.keys())
        # Specifically: only these 3
        assert set(mock.keys()) == {"id", "threadId", "labelIds"}

    def test_modify_returns_minimal(self, client):
        """messages.modify returns only {id, threadId, labelIds}."""
        real = load_fixture("message_modify_response.json")
        msgs = client.get("/gmail/v1/users/me/messages").json()["messages"]
        msg_id = msgs[0]["id"]

        resp = client.post(f"/gmail/v1/users/me/messages/{msg_id}/modify", json={
            "addLabelIds": ["STARRED"],
        })
        mock = resp.json()
        assert set(mock.keys()) == set(real.keys())

    def test_trash_returns_minimal(self, client):
        """messages.trash returns only {id, threadId, labelIds}."""
        real = load_fixture("message_trash_response.json")
        msgs = client.get("/gmail/v1/users/me/messages").json()["messages"]
        msg_id = msgs[0]["id"]

        resp = client.post(f"/gmail/v1/users/me/messages/{msg_id}/trash")
        mock = resp.json()
        assert set(mock.keys()) == set(real.keys())

    def test_get_full_has_payload(self, client):
        """messages.get format=full includes payload with proper structure."""
        real = load_fixture("message_get_full.json")
        msgs = client.get("/gmail/v1/users/me/messages").json()["messages"]
        msg_id = msgs[0]["id"]

        resp = client.get(f"/gmail/v1/users/me/messages/{msg_id}?format=full")
        mock = resp.json()

        # Must have payload
        assert "payload" in mock
        assert mock["payload"] is not None

        # Payload must have core fields
        payload = mock["payload"]
        assert "mimeType" in payload
        assert "headers" in payload

        # Must have these top-level keys
        for key in ("id", "threadId", "labelIds", "snippet", "historyId", "internalDate", "sizeEstimate"):
            assert key in mock, f"Missing key: {key}"

    def test_get_raw_omits_payload(self, client):
        """messages.get format=raw has 'raw' but no 'payload' key."""
        real = load_fixture("message_get_raw.json")
        msgs = client.get("/gmail/v1/users/me/messages").json()["messages"]
        msg_id = msgs[0]["id"]

        resp = client.get(f"/gmail/v1/users/me/messages/{msg_id}?format=raw")
        mock = resp.json()

        assert "raw" in mock
        assert mock["raw"] is not None
        # Real Gmail omits payload key entirely for format=raw
        assert "payload" not in mock

        # Same key set as real fixture
        assert set(real.keys()) == set(mock.keys())

    def test_get_minimal_keys(self, client):
        """messages.get format=minimal has exact same keys as real Gmail."""
        real = load_fixture("message_get_minimal.json")
        msgs = client.get("/gmail/v1/users/me/messages").json()["messages"]
        msg_id = msgs[0]["id"]

        resp = client.get(f"/gmail/v1/users/me/messages/{msg_id}?format=minimal")
        mock = resp.json()

        # Real minimal has: id, threadId, labelIds, snippet, sizeEstimate, historyId, internalDate
        assert set(real.keys()) == set(mock.keys())
        assert "payload" not in mock
        assert "raw" not in mock

    def test_get_metadata_payload_keys(self, client):
        """messages.get format=metadata payload has only {mimeType, headers}."""
        real = load_fixture("message_get_metadata.json")
        msgs = client.get("/gmail/v1/users/me/messages").json()["messages"]
        msg_id = msgs[0]["id"]

        resp = client.get(f"/gmail/v1/users/me/messages/{msg_id}?format=metadata")
        mock = resp.json()

        assert "payload" in mock
        real_payload_keys = set(real["payload"].keys())
        mock_payload_keys = set(mock["payload"].keys())
        assert mock_payload_keys == real_payload_keys

    def test_messages_list_structure(self, client):
        """messages.list has correct top-level structure."""
        resp = client.get("/gmail/v1/users/me/messages")
        mock = resp.json()

        assert "messages" in mock
        assert "resultSizeEstimate" in mock
        if mock["messages"]:
            msg = mock["messages"][0]
            assert set(msg.keys()) == {"id", "threadId"}

    def test_messages_list_default_shape(self, client):
        """messages.list default matches real fixture top-level keys."""
        real = load_fixture("messages_list.json")
        resp = client.get("/gmail/v1/users/me/messages")
        mock = resp.json()

        assert "messages" in mock
        assert "resultSizeEstimate" in mock
        # Each item is {id, threadId}
        for item in real["messages"]:
            assert set(item.keys()) == {"id", "threadId"}
        for item in mock["messages"]:
            assert set(item.keys()) == {"id", "threadId"}

    def test_messages_list_with_label_filter(self, client):
        """messages.list with labelIds filter returns same structure."""
        real = load_fixture("messages_list_inbox.json")
        resp = client.get("/gmail/v1/users/me/messages?labelIds=INBOX")
        mock = resp.json()

        assert "messages" in mock
        assert "resultSizeEstimate" in mock
        for item in real["messages"]:
            assert set(item.keys()) == {"id", "threadId"}
        for item in mock["messages"]:
            assert set(item.keys()) == {"id", "threadId"}

    def test_messages_list_with_search_query(self, client):
        """messages.list with q= search returns same structure."""
        real = load_fixture("messages_list_search.json")
        resp = client.get("/gmail/v1/users/me/messages?q=test")
        mock = resp.json()

        assert "resultSizeEstimate" in mock
        # Structure is the same regardless of results
        for item in real["messages"]:
            assert set(item.keys()) == {"id", "threadId"}
        if "messages" in mock:
            for item in mock["messages"]:
                assert set(item.keys()) == {"id", "threadId"}

    def test_sent_message_get_full_shape(self, client):
        """messages.get for a sent message has same keys as real fixture."""
        real = load_fixture("message_sent_get_full.json")
        # Send a message first
        send_resp = client.post("/gmail/v1/users/me/messages/send", json={
            "raw": _raw(subject="Sent Get Full Test", body="Body for sent get full conformance."),
        })
        msg_id = send_resp.json()["id"]

        resp = client.get(f"/gmail/v1/users/me/messages/{msg_id}?format=full")
        mock = resp.json()

        assert set(mock.keys()) == set(real.keys())
        assert "payload" in mock
        assert "SENT" in mock["labelIds"]

    def test_untrash_returns_minimal(self, client):
        """messages.untrash returns only {id, threadId, labelIds}."""
        real = load_fixture("message_untrash_response.json")
        msgs = client.get("/gmail/v1/users/me/messages").json()["messages"]
        msg_id = msgs[0]["id"]

        # Trash first, then untrash
        client.post(f"/gmail/v1/users/me/messages/{msg_id}/trash")
        resp = client.post(f"/gmail/v1/users/me/messages/{msg_id}/untrash")
        mock = resp.json()

        assert set(mock.keys()) == set(real.keys())
        assert "TRASH" not in mock["labelIds"]


class TestDraftsConformance:
    def test_draft_create_returns_minimal_message(self, client):
        """drafts.create response message has only {id, threadId, labelIds}."""
        real = load_fixture("draft_create_response.json")
        resp = client.post("/gmail/v1/users/me/drafts", json={
            "message": {
                "raw": _raw(subject="Draft Conformance", body="Test"),
            }
        })
        mock = resp.json()

        assert "id" in mock
        assert "message" in mock
        # Real draft create message is minimal
        assert set(real["message"].keys()) == set(mock["message"].keys())

    def test_draft_get_shape(self, client):
        """drafts.get returns {id, message} with full message inside."""
        real = load_fixture("draft_get_response.json")
        # Create a draft first
        create_resp = client.post("/gmail/v1/users/me/drafts", json={
            "message": {
                "raw": _raw(subject="Draft Get Test", body="Test body for draft get."),
            }
        })
        draft_id = create_resp.json()["id"]

        resp = client.get(f"/gmail/v1/users/me/drafts/{draft_id}")
        mock = resp.json()

        assert set(mock.keys()) == set(real.keys())
        assert "id" in mock
        assert "message" in mock
        # The inner message in drafts.get is full format
        real_msg_keys = set(real["message"].keys())
        mock_msg_keys = set(mock["message"].keys())
        assert mock_msg_keys == real_msg_keys

    def test_drafts_list_structure(self, client):
        """drafts.list has resultSizeEstimate; when empty, omits drafts key."""
        real = load_fixture("drafts_list.json")
        resp = client.get("/gmail/v1/users/me/drafts")
        mock = resp.json()

        # Both real and mock must have resultSizeEstimate
        assert "resultSizeEstimate" in mock
        assert "resultSizeEstimate" in real

        # Real fixture captured an empty list (no drafts key)
        assert "drafts" not in real

        # If mock has drafts, each item should have {id, message}
        if "drafts" in mock:
            for item in mock["drafts"]:
                assert "id" in item
                assert "message" in item
                assert set(item["message"].keys()) == {"id", "threadId"}


class TestHistoryConformance:
    def test_history_list_structure(self, client):
        """history.list has correct structure with history entries."""
        real = load_fixture("history_list.json")
        # Trigger some history by modifying a message
        msgs = client.get("/gmail/v1/users/me/messages").json()["messages"]
        msg_id = msgs[0]["id"]
        client.post(f"/gmail/v1/users/me/messages/{msg_id}/modify", json={
            "addLabelIds": ["STARRED"],
        })

        resp = client.get("/gmail/v1/users/me/history?startHistoryId=1")
        mock = resp.json()

        assert "historyId" in mock
        assert "history" in mock
        # Each history entry has at least {id, messages}
        for entry in real["history"]:
            assert "id" in entry
            assert "messages" in entry
        for entry in mock["history"]:
            assert "id" in entry
            assert "messages" in entry


class TestThreadsConformance:
    def test_thread_get_structure(self, client):
        """threads.get has correct structure with messages array."""
        resp = client.get("/gmail/v1/users/me/threads")
        threads = resp.json()["threads"]
        if not threads:
            pytest.skip("No threads")
        thread_id = threads[0]["id"]

        resp = client.get(f"/gmail/v1/users/me/threads/{thread_id}?format=full")
        mock = resp.json()

        # Real threads.get returns {id, historyId, messages} — no snippet
        real = load_fixture("thread_get_full.json")
        assert set(mock.keys()) == set(real.keys())
        assert isinstance(mock["id"], str)
        assert isinstance(mock["historyId"], str)
        assert "messages" in mock
        assert len(mock["messages"]) > 0

        real_message_keys = set(real["messages"][0])
        # Each message in thread should match the real full-format top-level shape.
        for msg in mock["messages"]:
            assert set(msg) == real_message_keys
            _assert_thread_message_core_types(msg)
            assert "payload" in msg
            assert "raw" not in msg
            assert isinstance(msg["payload"], dict)
            assert "id" in msg
            assert "threadId" in msg
            for header in msg["payload"]["headers"]:
                assert set(header) == {"name", "value"}
                assert all(isinstance(value, str) for value in header.values())

    def test_thread_get_metadata_format(self, client):
        """threads.get format=metadata messages have only {mimeType, headers} in payload."""
        real = load_fixture("thread_get_metadata.json")
        resp = client.get("/gmail/v1/users/me/threads")
        threads = resp.json()["threads"]
        if not threads:
            pytest.skip("No threads")
        thread_id = threads[0]["id"]

        resp = client.get(f"/gmail/v1/users/me/threads/{thread_id}?format=metadata")
        mock = resp.json()

        assert set(mock.keys()) == set(real.keys())
        assert isinstance(mock["id"], str)
        assert isinstance(mock["historyId"], str)
        assert "messages" in mock
        # Every message and payload should match metadata format, not only the first.
        real_msg = real["messages"][0]
        for mock_msg in mock["messages"]:
            assert set(mock_msg) == set(real_msg)
            _assert_thread_message_core_types(mock_msg)
            assert set(real_msg["payload"]) == set(mock_msg["payload"])
            assert "raw" not in mock_msg
            for header in mock_msg["payload"]["headers"]:
                assert set(header) == {"name", "value"}
                assert all(isinstance(value, str) for value in header.values())

    def test_thread_get_minimal_format(self, client):
        """threads.get format=minimal omits payload and raw from every message."""
        real = load_fixture("thread_get_minimal.json")
        resp = client.get("/gmail/v1/users/me/threads")
        threads = resp.json()["threads"]
        if not threads:
            pytest.skip("No threads")
        thread_id = threads[0]["id"]

        resp = client.get(f"/gmail/v1/users/me/threads/{thread_id}?format=minimal")
        mock = resp.json()

        assert set(mock) == set(real)
        assert isinstance(mock["id"], str)
        assert isinstance(mock["historyId"], str)
        assert "messages" in mock

        # The provider fixture contains two messages and records their API order.
        assert len(real["messages"]) >= 2
        real_dates = [int(message["internalDate"]) for message in real["messages"]]
        assert real_dates == sorted(real_dates)

        real_message_keys = set(real["messages"][0])
        for real_msg in real["messages"]:
            assert set(real_msg) == real_message_keys
            _assert_thread_message_core_types(real_msg)
            assert "payload" not in real_msg
            assert "raw" not in real_msg
        for mock_msg in mock["messages"]:
            assert set(mock_msg) == real_message_keys
            _assert_thread_message_core_types(mock_msg)
            assert "payload" not in mock_msg
            assert "raw" not in mock_msg

    def test_threads_list_structure(self, client):
        """threads.list returns items with {id, snippet, historyId}."""
        real = load_fixture("threads_list.json")
        # The real fixture was captured with maxResults=10.
        resp = client.get("/gmail/v1/users/me/threads?maxResults=10")
        mock = resp.json()

        assert set(mock) == set(real)
        assert isinstance(mock["resultSizeEstimate"], int)
        assert isinstance(mock["nextPageToken"], str)
        assert len(mock["threads"]) == len(real["threads"])
        # Each real thread item has {id, snippet, historyId}
        for item in real["threads"]:
            assert set(item.keys()) == {"id", "snippet", "historyId"}
        for item in mock["threads"]:
            assert set(item.keys()) == {"id", "snippet", "historyId"}
            assert all(isinstance(value, str) for value in item.values())

    def test_threads_list_mixed_trash_order_fixture(self):
        """Provider capture orders a mixed Trash thread by its visible message."""
        default = load_fixture("threads_list_mixed_trash_default.json")
        included = load_fixture("threads_list_mixed_trash_included.json")
        thread_a = load_fixture("thread_get_metadata_mixed_trash_a.json")
        thread_b = load_fixture("thread_get_metadata_mixed_trash_b.json")

        assert len(thread_a["messages"]) == 2
        assert len(thread_b["messages"]) == 1
        a_visible, a_trashed = thread_a["messages"]
        (b_visible,) = thread_b["messages"]
        assert int(a_visible["internalDate"]) < int(b_visible["internalDate"])
        assert int(b_visible["internalDate"]) < int(a_trashed["internalDate"])
        assert "TRASH" not in a_visible["labelIds"]
        assert "TRASH" not in b_visible["labelIds"]
        assert "TRASH" in a_trashed["labelIds"]

        expected_order = [thread_b["id"], thread_a["id"]]
        assert [thread["id"] for thread in default["threads"]] == expected_order
        assert [thread["id"] for thread in included["threads"]] == expected_order
        assert default["resultSizeEstimate"] == 2
        assert included["resultSizeEstimate"] == 2

    def test_threads_list_mixed_spam_order_fixture(self):
        """Provider capture orders a mixed Spam thread by its visible message."""
        default = load_fixture("threads_list_mixed_spam_default.json")
        included = load_fixture("threads_list_mixed_spam_included.json")
        thread_c = load_fixture("thread_get_metadata_mixed_spam_c.json")
        thread_d = load_fixture("thread_get_metadata_mixed_spam_d.json")

        assert len(thread_c["messages"]) == 2
        assert len(thread_d["messages"]) == 1
        c_visible, c_spam = thread_c["messages"]
        (d_visible,) = thread_d["messages"]
        assert int(c_visible["internalDate"]) < int(d_visible["internalDate"])
        assert int(d_visible["internalDate"]) < int(c_spam["internalDate"])
        assert "SPAM" not in c_visible["labelIds"]
        assert "SPAM" not in d_visible["labelIds"]
        assert "SPAM" in c_spam["labelIds"]

        expected_order = [thread_d["id"], thread_c["id"]]
        assert [thread["id"] for thread in default["threads"]] == expected_order
        assert [thread["id"] for thread in included["threads"]] == expected_order
        assert default["resultSizeEstimate"] == 2
        assert included["resultSizeEstimate"] == 2


class TestSettingsConformance:
    def test_filters_list_empty_returns_empty_object(self, client):
        """settings.filters.list returns {} when no filters exist."""
        real = load_fixture("settings_filters_list.json")
        resp = client.get("/gmail/v1/users/me/settings/filters")
        mock = resp.json()
        assert mock == real  # both should be {}

    def test_forwarding_list_empty_returns_empty_object(self, client):
        """settings.forwardingAddresses.list returns {} when empty."""
        real = load_fixture("settings_forwarding_list.json")
        resp = client.get("/gmail/v1/users/me/settings/forwardingAddresses")
        mock = resp.json()
        assert mock == real  # both should be {}

    def test_vacation_default_structure(self, client):
        """settings.vacation default has exact same keys as real Gmail."""
        real = load_fixture("settings_vacation.json")
        resp = client.get("/gmail/v1/users/me/settings/vacation")
        mock = resp.json()
        assert mock["enableAutoReply"] is False
        assert set(mock.keys()) == set(real.keys())

    def test_autoforwarding_default_structure(self, client):
        """settings.autoForwarding default has exact same keys as real Gmail."""
        real = load_fixture("settings_autoforwarding.json")
        resp = client.get("/gmail/v1/users/me/settings/autoForwarding")
        mock = resp.json()
        assert mock["enabled"] is False
        assert set(mock.keys()) == set(real.keys())

    def test_imap_default_matches_real(self, client):
        """settings.imap default matches real Gmail response shape and values."""
        real = load_fixture("settings_imap.json")
        resp = client.get("/gmail/v1/users/me/settings/imap")
        mock = resp.json()
        assert set(real.keys()) == set(mock.keys())
        assert mock["enabled"] == real["enabled"]
        assert mock["autoExpunge"] == real["autoExpunge"]
        assert mock["expungeBehavior"] == real["expungeBehavior"]
        assert mock["maxFolderSize"] == real["maxFolderSize"]

    def test_pop_default_matches_real(self, client):
        """settings.pop default matches real Gmail response shape and values."""
        real = load_fixture("settings_pop.json")
        resp = client.get("/gmail/v1/users/me/settings/pop")
        mock = resp.json()
        assert set(real.keys()) == set(mock.keys())
        assert mock["accessWindow"] == real["accessWindow"]
        assert mock["disposition"] == real["disposition"]

    def test_language_default_matches_real(self, client):
        """settings.language default matches real Gmail response shape and values."""
        real = load_fixture("settings_language.json")
        resp = client.get("/gmail/v1/users/me/settings/language")
        mock = resp.json()
        assert set(real.keys()) == set(mock.keys())
        assert mock["displayLanguage"] == real["displayLanguage"]

    def test_sendas_list_has_primary(self, client):
        """settings.sendAs.list has at least one primary entry with correct keys."""
        real = load_fixture("settings_sendas_list.json")
        resp = client.get("/gmail/v1/users/me/settings/sendAs")
        mock = resp.json()
        assert "sendAs" in mock
        primary = [sa for sa in mock["sendAs"] if sa.get("isPrimary")]
        assert len(primary) == 1
        # Primary sendAs should match real Gmail key set (no treatAsAlias/verificationStatus)
        real_primary = [sa for sa in real["sendAs"] if sa.get("isPrimary")][0]
        assert set(primary[0].keys()) == set(real_primary.keys())
