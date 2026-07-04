"""Structured error body builders match the pinned contract shapes exactly."""

from env_0_auth_client import errors


class TestUnauthenticatedBody:
    def test_shape(self):
        body = errors.unauthenticated_body("Bad token.", "Get a new one.")
        assert body == {
            "error": {
                "code": 401,
                "status": "UNAUTHENTICATED",
                "message": "Bad token.",
                "hint": "Get a new one.",
            }
        }

    def test_www_authenticate_header_value(self):
        value = errors.www_authenticate("token is bad")
        assert value == 'Bearer error="invalid_token", error_description="token is bad"'

    def test_www_authenticate_escapes_double_quotes(self):
        value = errors.www_authenticate('issuer "evil" rejected')
        assert '"evil"' not in value.split("error_description=")[1]


class TestExpiredTokenBody:
    def test_message_includes_expiry_and_hint_includes_refresh(self):
        body = errors.expired_token_body("2026-06-10T12:00:00Z", "http://localhost:9000")
        err = body["error"]
        assert err["code"] == 401
        assert err["status"] == "UNAUTHENTICATED"
        assert "2026-06-10T12:00:00Z" in err["message"]
        assert "POST http://localhost:9000/oauth2/token" in err["hint"]
        assert "grant_type=refresh_token" in err["hint"]


class TestInsufficientScopeBody:
    def test_shape(self):
        body = errors.insufficient_scope_body(
            ["gmail.send", "gmail.full"], ["gmail.readonly"]
        )
        err = body["error"]
        assert err["code"] == 403
        assert err["status"] == "PERMISSION_DENIED"
        assert err["required_scopes"] == ["gmail.send", "gmail.full"]
        assert err["token_scopes"] == ["gmail.readonly"]
        assert "gmail.send" in err["message"]
        assert isinstance(err["hint"], str) and err["hint"]


class TestImpersonationBody:
    def test_shape(self):
        body = errors.impersonation_body("user_001", "user_002")
        assert body == {
            "error": {
                "code": 403,
                "status": "PERMISSION_DENIED",
                "message": "Cannot access another user's resources",
                "authenticated_user": "user_001",
                "requested_user": "user_002",
            }
        }
