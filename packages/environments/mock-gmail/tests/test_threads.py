"""Focused behavior tests for the Gmail Threads read API."""

from __future__ import annotations

from datetime import datetime

import pytest

from mock_gmail.models import (
    Message,
    MessageLabel,
    Thread,
    User,
    get_session_factory,
)


@pytest.fixture
def db_session(client):
    """Open a session against the database initialized by the API client."""
    db = get_session_factory()()
    try:
        yield db
    finally:
        db.close()


def _user_id(db_session) -> str:
    return (
        db_session.query(User.id)
        .filter(User.email_address == "alex@nexusai.com")
        .scalar()
    )


def _add_thread(
    db_session,
    user_id: str,
    thread_id: str,
    messages: list[dict],
    *,
    subject: str = "Threads API regression",
) -> None:
    db_session.add(
        Thread(
            id=thread_id,
            user_id=user_id,
            snippet=messages[-1].get("body", "")[:200] if messages else "",
            history_id=9001,
        )
    )
    for spec in messages:
        labels = set(spec.get("labels", ["INBOX"]))
        message = Message(
            id=spec["id"],
            thread_id=thread_id,
            user_id=user_id,
            sender="threads-regression@example.com",
            to="alex@nexusai.com",
            subject=spec.get("subject", subject),
            snippet=spec.get("body", "")[:200],
            body_plain=spec.get("body", ""),
            internal_date=spec["date"],
            is_read="UNREAD" not in labels,
            is_starred="STARRED" in labels,
            is_trash="TRASH" in labels,
            is_spam="SPAM" in labels,
            is_draft="DRAFT" in labels,
            is_sent="SENT" in labels,
        )
        db_session.add(message)
        for label_id in labels - {
            "UNREAD",
            "STARRED",
            "TRASH",
            "SPAM",
            "DRAFT",
            "SENT",
        }:
            db_session.add(MessageLabel(message_id=message.id, label_id=label_id))
    db_session.commit()


def _listed_thread_ids(response) -> list[str]:
    assert response.status_code == 200
    return [thread["id"] for thread in response.json().get("threads", [])]


def _at(month: int, day: int, hour: int = 8, minute: int = 0) -> datetime:
    return datetime(2099, month, day, hour, minute)


def _message_spec(
    message_id: str,
    internal_date: datetime,
    body: str,
    labels: list[str] | None = None,
) -> dict:
    spec = {"id": message_id, "date": internal_date, "body": body}
    if labels is not None:
        spec["labels"] = labels
    return spec


class TestThreadsListBehavior:
    def test_q_matches_any_older_message_and_returns_thread_once(
        self, client, db_session
    ):
        user_id = _user_id(db_session)
        marker = "older-message-thread-match-7f19"
        _add_thread(
            db_session,
            user_id,
            "thread-q-old-message",
            [
                _message_spec("message-q-old-a", _at(1, 1), marker),
                _message_spec("message-q-old-b", _at(1, 2), marker),
                _message_spec(
                    "message-q-newest",
                    _at(1, 3),
                    "The newest message does not contain the search marker.",
                ),
            ],
        )

        response = client.get("/gmail/v1/users/me/threads", params={"q": marker})

        assert _listed_thread_ids(response) == ["thread-q-old-message"]
        assert response.json()["resultSizeEstimate"] == 1

    def test_same_subject_different_thread_ids_remain_separate(
        self, client, db_session
    ):
        user_id = _user_id(db_session)
        subject = "Shared subject 4da36d"
        for suffix in ("a", "b"):
            _add_thread(
                db_session,
                user_id,
                f"thread-same-subject-{suffix}",
                [
                    _message_spec(
                        f"message-same-subject-{suffix}",
                        _at(2, 1, minute=ord(suffix) - ord("a")),
                        f"Message {suffix}",
                    )
                ],
                subject=subject,
            )

        response = client.get(
            "/gmail/v1/users/me/threads",
            params={"q": f'subject:"{subject}"'},
        )

        assert set(_listed_thread_ids(response)) == {
            "thread-same-subject-a",
            "thread-same-subject-b",
        }
        assert response.json()["resultSizeEstimate"] == 2

    def test_all_labels_may_be_on_different_messages(self, client, db_session):
        user_id = _user_id(db_session)
        marker = "thread-label-union-135b"
        scenarios = {
            "thread-label-both": (["INBOX"], ["STARRED"]),
            "thread-label-inbox-only": (["INBOX"], ["INBOX"]),
            "thread-label-starred-only": (["STARRED"], ["STARRED"]),
        }
        for thread_id, message_labels in scenarios.items():
            _add_thread(
                db_session,
                user_id,
                thread_id,
                [
                    _message_spec(
                        f"{thread_id}-message-{index}",
                        _at(3, index + 1),
                        marker,
                        labels,
                    )
                    for index, labels in enumerate(message_labels)
                ],
            )

        response = client.get(
            "/gmail/v1/users/me/threads",
            params=[
                ("q", marker),
                ("labelIds", "INBOX"),
                ("labelIds", "STARRED"),
            ],
        )

        assert _listed_thread_ids(response) == ["thread-label-both"]
        assert response.json()["resultSizeEstimate"] == 1

    def test_include_spam_trash_controls_hidden_threads(self, client, db_session):
        user_id = _user_id(db_session)
        marker = "thread-hidden-7f921"
        scenarios = {
            "thread-visible": [["INBOX"]],
            "thread-trash-only": [["TRASH"]],
            "thread-spam-only": [["SPAM"]],
        }
        for thread_number, (thread_id, message_labels) in enumerate(
            scenarios.items(), start=1
        ):
            _add_thread(
                db_session,
                user_id,
                thread_id,
                [
                    _message_spec(
                        f"{thread_id}-message-{message_number}",
                        _at(4, thread_number, hour=message_number),
                        marker,
                        labels,
                    )
                    for message_number, labels in enumerate(message_labels, start=1)
                ],
            )

        default_response = client.get(
            "/gmail/v1/users/me/threads",
            params={"q": marker},
        )
        included_response = client.get(
            "/gmail/v1/users/me/threads",
            params={"q": marker, "includeSpamTrash": "true"},
        )

        assert _listed_thread_ids(default_response) == ["thread-visible"]
        assert default_response.json()["resultSizeEstimate"] == 1
        assert set(_listed_thread_ids(included_response)) == set(scenarios)
        assert included_response.json()["resultSizeEstimate"] == 3
