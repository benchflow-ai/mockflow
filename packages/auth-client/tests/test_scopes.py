"""Scope constants, descriptions, and has_any_scope OR logic."""

from env_0_auth_client import scopes
from env_0_auth_client.scopes import SCOPE_DESCRIPTIONS, has_any_scope


class TestScopeConstants:
    def test_gmail_scope_names(self):
        assert scopes.GMAIL_READONLY == "gmail.readonly"
        assert scopes.GMAIL_SEND == "gmail.send"
        assert scopes.GMAIL_SETTINGS_BASIC == "gmail.settings.basic"
        assert scopes.GMAIL_FULL == "gmail.full"

    def test_slack_scope_names_are_colon_style(self):
        assert scopes.CHAT_WRITE == "chat:write"
        assert scopes.USERS_READ_EMAIL == "users:read.email"

    def test_every_constant_has_a_description(self):
        constants = [
            value
            for name, value in vars(scopes).items()
            if name.isupper() and isinstance(value, str)
        ]
        for scope in constants:
            assert scope in SCOPE_DESCRIPTIONS, f"missing description for {scope}"

    def test_descriptions_match_spec(self):
        assert SCOPE_DESCRIPTIONS["gmail.send"] == "Send email"
        assert SCOPE_DESCRIPTIONS["gmail.full"] == "All Gmail operations"
        assert SCOPE_DESCRIPTIONS["chat:write"] == "Post messages"


class TestHasAnyScope:
    def test_or_logic_one_match_grants(self):
        assert has_any_scope(["gmail.readonly"], ["gmail.readonly", "gmail.full"]) is True
        assert has_any_scope(["gmail.full"], ["gmail.readonly", "gmail.full"]) is True

    def test_no_match_denies(self):
        assert has_any_scope(["gmail.send"], ["gmail.readonly", "gmail.full"]) is False
        assert has_any_scope([], ["gmail.readonly"]) is False

    def test_accepts_space_separated_string(self):
        assert has_any_scope("openid email gmail.readonly", ["gmail.readonly"]) is True
        assert has_any_scope("openid email", ["gmail.readonly"]) is False
        assert has_any_scope("", ["gmail.readonly"]) is False

    def test_empty_required_means_no_requirement(self):
        assert has_any_scope([], []) is True
        assert has_any_scope("openid", []) is True
