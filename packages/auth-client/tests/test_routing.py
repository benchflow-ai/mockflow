"""match_route(app, scope) against parameterized FastAPI routes."""

from conftest import build_app

from env_0_auth_client import match_route


def http_scope(method: str, path: str) -> dict:
    return {
        "type": "http",
        "method": method,
        "path": path,
        "root_path": "",
        "headers": [],
        "query_string": b"",
    }


class TestMatchRoute:
    def test_parameterized_route(self, jwks):
        app = build_app(jwks_static=jwks)
        scope = http_scope("GET", "/gmail/v1/users/user_001/messages")
        assert match_route(app, scope) == ("GET", "/gmail/v1/users/{userId}/messages")

    def test_two_params(self, jwks):
        app = build_app(jwks_static=jwks)
        scope = http_scope("GET", "/gmail/v1/users/me/messages/abc123")
        assert match_route(app, scope) == (
            "GET",
            "/gmail/v1/users/{userId}/messages/{messageId}",
        )

    def test_post_route(self, jwks):
        app = build_app(jwks_static=jwks)
        scope = http_scope("POST", "/gmail/v1/users/me/messages/send")
        assert match_route(app, scope) == ("POST", "/gmail/v1/users/{userId}/messages/send")

    def test_unknown_path_returns_none(self, jwks):
        app = build_app(jwks_static=jwks)
        assert match_route(app, http_scope("GET", "/nope/nothing/here")) is None

    def test_method_not_allowed_returns_none(self, jwks):
        app = build_app(jwks_static=jwks)
        scope = http_scope("PATCH", "/gmail/v1/users/me/messages/send")
        assert match_route(app, scope) is None

    def test_non_http_scope_returns_none(self, jwks):
        app = build_app(jwks_static=jwks)
        assert match_route(app, {"type": "websocket", "path": "/x"}) is None
