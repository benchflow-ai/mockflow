"""Action logging middleware backing store (in-memory singleton).

Same shape as gmail's, plus `token_type` ("test"/"live"/"") derived from
the API key prefix — Slack's precedent of recording auth identity in the log.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass
class ActionLogEntry:
    timestamp: str
    method: str
    path: str
    user_id: str
    request_body: dict | None = None
    response_status: int = 200
    token_type: str = ""


class ActionLog:
    """In-memory action log for tracking all API calls."""

    def __init__(self):
        self._entries: list[ActionLogEntry] = []

    def record(
        self,
        method: str,
        path: str,
        user_id: str = "",
        request_body: dict | None = None,
        response_status: int = 200,
        token_type: str = "",
    ):
        self._entries.append(ActionLogEntry(
            timestamp=datetime.now(timezone.utc).isoformat(),
            method=method,
            path=path,
            user_id=user_id,
            request_body=request_body,
            response_status=response_status,
            token_type=token_type,
        ))

    def get_entries(self) -> list[dict]:
        return [
            {
                "timestamp": e.timestamp,
                "method": e.method,
                "path": e.path,
                "user_id": e.user_id,
                "request_body": e.request_body,
                "response_status": e.response_status,
                "token_type": e.token_type,
            }
            for e in self._entries
        ]

    def clear(self):
        self._entries.clear()

    def __len__(self):
        return len(self._entries)


# Global singleton
action_log = ActionLog()
