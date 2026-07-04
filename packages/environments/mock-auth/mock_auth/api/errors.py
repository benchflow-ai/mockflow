"""Error types for auth.

Two distinct error surfaces (per the pinned interface contract):

1. OAuth protocol endpoints (authorize/token/introspect/revoke/device) return
   RFC 6749 bodies: {"error": "...", "error_description": "...", "hint": "..."}
   with 400/401 status codes. These must NOT be wrapped in any generic envelope.

2. Bearer-protected resource endpoints (userinfo) return the structured
   resource-server envelope:
   {"error": {"code": 401, "status": "UNAUTHENTICATED", "message": ..., "hint": ...}}
   plus a WWW-Authenticate header.
"""

from __future__ import annotations


class OAuthError(Exception):
    """RFC 6749-style error. Handled by an app-level exception handler."""

    def __init__(
        self,
        error: str,
        error_description: str,
        hint: str | None = None,
        status_code: int = 400,
        headers: dict | None = None,
    ):
        super().__init__(error_description)
        self.error = error
        self.error_description = error_description
        self.hint = hint
        self.status_code = status_code
        self.headers = headers or {}

    def body(self) -> dict:
        return {
            "error": self.error,
            "error_description": self.error_description,
            "hint": self.hint,
        }


class BearerError(Exception):
    """Resource-server style error for Bearer-protected endpoints (userinfo)."""

    def __init__(
        self,
        status_code: int,
        status: str,
        message: str,
        hint: str | None = None,
        extra: dict | None = None,
        www_authenticate: str | None = None,
    ):
        super().__init__(message)
        self.status_code = status_code
        self.status = status
        self.message = message
        self.hint = hint
        self.extra = extra or {}
        self.www_authenticate = www_authenticate

    def body(self) -> dict:
        err = {"code": self.status_code, "status": self.status, "message": self.message}
        if self.hint is not None:
            err["hint"] = self.hint
        err.update(self.extra)
        return {"error": err}
