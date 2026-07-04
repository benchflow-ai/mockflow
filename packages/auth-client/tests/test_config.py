"""Env parsing: is_auth_enabled, URLs, issuer, report/introspect toggles, JWKS TTL."""

import pytest

from env_0_auth_client import config, is_auth_enabled


class TestIsAuthEnabled:
    @pytest.mark.parametrize("value", ["1", "true", "True", "TRUE", "yes", "YES", "Yes"])
    def test_truthy_values(self, monkeypatch, value):
        monkeypatch.setenv("AUTH_ENABLED", value)
        assert is_auth_enabled() is True

    @pytest.mark.parametrize("value", ["0", "false", "no", "", "on", "enabled", "2"])
    def test_falsy_values(self, monkeypatch, value):
        monkeypatch.setenv("AUTH_ENABLED", value)
        assert is_auth_enabled() is False

    def test_unset_is_disabled(self, monkeypatch):
        monkeypatch.delenv("AUTH_ENABLED", raising=False)
        assert is_auth_enabled() is False


class TestAuthUrlAndIssuer:
    def test_default_auth_url(self):
        assert config.get_auth_url() == "http://localhost:9000"

    def test_auth_url_from_env_strips_trailing_slash(self, monkeypatch):
        monkeypatch.setenv("AUTH_URL", "http://auth.example:9000/")
        assert config.get_auth_url() == "http://auth.example:9000"

    def test_issuer_defaults_to_auth_url(self, monkeypatch):
        monkeypatch.setenv("AUTH_URL", "http://auth.example:9000")
        assert config.get_issuer() == "http://auth.example:9000"

    def test_issuer_env_override(self, monkeypatch):
        monkeypatch.setenv("AUTH_URL", "http://auth.example:9000")
        monkeypatch.setenv("AUTH_ISSUER", "http://issuer.example")
        assert config.get_issuer() == "http://issuer.example"


class TestToggles:
    def test_report_default_on(self, monkeypatch):
        monkeypatch.delenv("AUTH_REPORT", raising=False)
        assert config.is_report_enabled() is True

    @pytest.mark.parametrize("value", ["0", "false", "no", "FALSE"])
    def test_report_disabled(self, monkeypatch, value):
        monkeypatch.setenv("AUTH_REPORT", value)
        assert config.is_report_enabled() is False

    def test_introspect_default_off(self, monkeypatch):
        monkeypatch.delenv("AUTH_INTROSPECT", raising=False)
        assert config.is_introspect_enabled() is False

    def test_introspect_enabled(self, monkeypatch):
        monkeypatch.setenv("AUTH_INTROSPECT", "1")
        assert config.is_introspect_enabled() is True


class TestJwksTtl:
    def test_default(self, monkeypatch):
        monkeypatch.delenv("AUTH_JWKS_TTL", raising=False)
        assert config.get_jwks_ttl() == 300

    def test_custom(self, monkeypatch):
        monkeypatch.setenv("AUTH_JWKS_TTL", "120")
        assert config.get_jwks_ttl() == 120

    def test_garbage_falls_back_to_default(self, monkeypatch):
        monkeypatch.setenv("AUTH_JWKS_TTL", "not-a-number")
        assert config.get_jwks_ttl() == 300
