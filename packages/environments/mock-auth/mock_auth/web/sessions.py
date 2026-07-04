"""In-memory web session store for the consent/login UI.

Cookie `mock_auth_session` holds an opaque session id mapping to a user id.
Purely in-memory (mock service); cleared by reset_engine() and /_admin/reset.
"""

from __future__ import annotations

SESSION_COOKIE = "mock_auth_session"

_SESSIONS: dict[str, str] = {}


def create_session(user_id: str) -> str:
    from mock_auth.tokens import token_hex

    sid = "sess_" + token_hex(16)
    _SESSIONS[sid] = user_id
    return sid


def get_session_user_id(sid: str | None) -> str | None:
    if not sid:
        return None
    return _SESSIONS.get(sid)


def delete_session(sid: str | None):
    if sid:
        _SESSIONS.pop(sid, None)


def reset_sessions():
    _SESSIONS.clear()
