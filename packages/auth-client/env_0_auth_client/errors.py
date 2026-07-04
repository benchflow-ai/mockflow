"""Builders for the structured resource-server error bodies (pinned by contract).

Three shapes:
- 401 UNAUTHENTICATED (missing/invalid/expired token) + WWW-Authenticate header
- 403 PERMISSION_DENIED insufficient scope (required_scopes / token_scopes lists)
- 403 PERMISSION_DENIED impersonation (path userId != token sub)
"""


def www_authenticate(error_description: str, error: str = "invalid_token") -> str:
    """Value for the WWW-Authenticate header on 401 responses."""
    description = error_description.replace('"', "'")
    return f'Bearer error="{error}", error_description="{description}"'


def unauthenticated_body(message: str, hint: str) -> dict:
    """401 body: {"error": {"code": 401, "status": "UNAUTHENTICATED", ...}}."""
    return {
        "error": {
            "code": 401,
            "status": "UNAUTHENTICATED",
            "message": message,
            "hint": hint,
        }
    }


def expired_token_body(expired_at_iso: str, auth_url: str) -> dict:
    """401 body for an expired token.

    The message includes the token expiry time; the hint explains how to
    refresh (POST {AUTH_URL}/oauth2/token with grant_type=refresh_token).
    """
    return unauthenticated_body(
        message=f"Access token expired at {expired_at_iso}.",
        hint=(
            f"Use your refresh token to obtain a new access token: "
            f"POST {auth_url}/oauth2/token with grant_type=refresh_token "
            f"and refresh_token=<your refresh token>."
        ),
    )


def insufficient_scope_body(
    required_scopes: list[str],
    token_scopes: list[str],
    message: str | None = None,
    hint: str | None = None,
) -> dict:
    """403 body for a scope miss, listing required vs granted scopes."""
    required = list(required_scopes)
    granted = list(token_scopes)
    if message is None:
        message = (
            "Request had insufficient authentication scopes. "
            f"Requires one of: {', '.join(required)}."
        )
    if hint is None:
        hint = (
            "Request a new token that includes one of the required scopes "
            "(re-run the consent flow with the missing scope)."
        )
    return {
        "error": {
            "code": 403,
            "status": "PERMISSION_DENIED",
            "message": message,
            "required_scopes": required,
            "token_scopes": granted,
            "hint": hint,
        }
    }


def impersonation_body(authenticated_user: str, requested_user: str) -> dict:
    """403 body when the path userId does not match the token's sub."""
    return {
        "error": {
            "code": 403,
            "status": "PERMISSION_DENIED",
            "message": "Cannot access another user's resources",
            "authenticated_user": authenticated_user,
            "requested_user": requested_user,
        }
    }
