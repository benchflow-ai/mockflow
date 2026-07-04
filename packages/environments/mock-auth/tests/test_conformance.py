"""Conformance tests — mock response SHAPES vs golden Google OAuth fixtures.

Fixtures live in tests/fixtures/real_googleoauth/. Live-captured fixtures came
from Google's public (unauthenticated) endpoints; success-path fixtures are
AUTHORED from Google's documented response shapes — see _capture_metadata.json
`method_per_file` for per-file provenance.

Value-level divergences are intentional and documented in API_NOTES.md
(bare scope names, rotation on refresh, RFC 7662 introspection instead of
tokeninfo, contract-pinned structured userinfo errors).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from .conftest import full_auth_code_flow

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "real_googleoauth"


def load_fixture(name: str) -> dict:
    path = FIXTURES_DIR / name
    if not path.exists():
        pytest.skip(f"Golden fixture {name} not found")
    data = json.loads(path.read_text())
    data.pop("_captured_at", None)
    return data


def _assert_shape(real, mock, path="", strict=True):
    """Recursively assert mock response shape matches the real fixture."""
    if isinstance(real, dict) and isinstance(mock, dict):
        missing = set(real) - set(mock)
        assert not missing, f"Mock MISSING keys at {path or 'root'}: {missing}"
        if strict:
            extra = set(mock) - set(real)
            assert not extra, f"Mock has EXTRA keys at {path or 'root'}: {extra}"
        for key in set(real) & set(mock):
            _assert_shape(real[key], mock[key], f"{path}.{key}" if path else key, strict)
    elif isinstance(real, list) and isinstance(mock, list):
        if real and mock:
            _assert_shape(real[0], mock[0], f"{path}[0]", strict)
    else:
        if real is not None and mock is not None:
            assert type(real).__name__ == type(mock).__name__, (
                f"TYPE MISMATCH at {path}: real={type(real).__name__} "
                f"mock={type(mock).__name__}"
            )


# ---------------------------------------------------------------------------
class TestDiscoveryConformance:
    def test_discovery_required_keys(self, client):
        """Mock discovery must carry every key real Google publishes."""
        real = load_fixture("openid_configuration.json")
        mock = client.get("/.well-known/openid-configuration").json()
        missing = set(real.keys()) - set(mock.keys())
        assert not missing, f"Mock discovery missing keys: {missing}"

    def test_discovery_documented_extras_only(self, client):
        """Extras beyond Google's doc are limited to the pinned auth extensions."""
        real = load_fixture("openid_configuration.json")
        mock = client.get("/.well-known/openid-configuration").json()
        extras = set(mock.keys()) - set(real.keys())
        assert extras == {"introspection_endpoint"}, extras

    def test_discovery_value_types(self, client):
        real = load_fixture("openid_configuration.json")
        mock = client.get("/.well-known/openid-configuration").json()
        for key in set(real) & set(mock):
            _assert_shape(real[key], mock[key], path=key, strict=False)

    def test_grant_types_superset_of_google_minus_jwt_bearer(self, client):
        real = load_fixture("openid_configuration.json")
        mock = client.get("/.well-known/openid-configuration").json()
        google_grants = set(real["grant_types_supported"])
        google_grants.discard("urn:ietf:params:oauth:grant-type:jwt-bearer")  # not mocked
        assert google_grants <= set(mock["grant_types_supported"])


class TestJWKSConformance:
    def test_jwk_entry_keys(self, client):
        real = load_fixture("jwks.json")
        mock = client.get("/oauth2/v3/certs").json()
        assert set(mock.keys()) == set(real.keys()) == {"keys"}
        assert set(mock["keys"][0].keys()) == set(real["keys"][0].keys())

    def test_jwk_entry_value_types(self, client):
        real = load_fixture("jwks.json")
        mock = client.get("/oauth2/v3/certs").json()
        _assert_shape(real["keys"][0], mock["keys"][0], path="keys[0]")

    def test_jwk_alg_and_kty_values(self, client):
        real = load_fixture("jwks.json")
        mock = client.get("/oauth2/v3/certs").json()
        assert mock["keys"][0]["kty"] == real["keys"][0]["kty"] == "RSA"
        assert mock["keys"][0]["alg"] == "RS256"
        assert mock["keys"][0]["use"] == real["keys"][0]["use"] == "sig"


class TestTokenConformance:
    def test_token_response_keys(self, client):
        """Authorization-code exchange (openid scope) vs authored Google shape."""
        real = load_fixture("token_response.json")
        mock = full_auth_code_flow(client, scope="openid email gmail.readonly")
        assert set(mock.keys()) == set(real.keys())
        _assert_shape(real, mock)

    def test_refresh_response_keys(self, client):
        """Refresh response: Google omits refresh_token; auth ROTATES and
        returns a new one (intentional safety divergence, see API_NOTES.md)."""
        real = load_fixture("token_refresh_response.json")
        tok = full_auth_code_flow(client, scope="gmail.readonly")
        mock = client.post("/oauth2/token", data={
            "grant_type": "refresh_token", "refresh_token": tok["refresh_token"],
            "client_id": "gws-cli"}).json()
        missing = set(real.keys()) - set(mock.keys())
        assert not missing
        assert set(mock.keys()) - set(real.keys()) == {"refresh_token"}

    def test_invalid_grant_error_keys(self, client):
        """Bad code -> invalid_grant; mock adds the contract-pinned `hint` key."""
        real = load_fixture("token_error_invalid_grant.json")
        mock = client.post("/oauth2/token", data={
            "grant_type": "authorization_code", "code": "bogus",
            "redirect_uri": "http://localhost:8085/callback", "client_id": "gws-cli"})
        assert mock.status_code == 400
        body = mock.json()
        missing = set(real.keys()) - set(body.keys())
        assert not missing
        assert set(body.keys()) - set(real.keys()) == {"hint"}
        assert body["error"] == real["error"] == "invalid_grant"

    def test_no_client_error_keys(self, client):
        """No client_id -> Google says invalid_request/could-not-determine-client;
        auth pins invalid_client (401) with the same flat RFC 6749 shape."""
        real = load_fixture("token_error_no_client.json")
        mock = client.post("/oauth2/token", data={"grant_type": "authorization_code"})
        body = mock.json()
        assert set(real.keys()) <= set(body.keys())
        assert isinstance(body["error"], str)
        assert isinstance(body["error_description"], str)


class TestUserinfoConformance:
    def test_userinfo_keys(self, client):
        real = load_fixture("userinfo.json")
        tok = client.post("/_admin/issue_token", json={
            "client_id": "gws-cli", "user_id": "user1",
            "scopes": ["openid", "email", "profile"]}).json()
        mock = client.get("/oauth2/v2/userinfo",
                          headers={"Authorization": f"Bearer {tok['access_token']}"}).json()
        assert set(mock.keys()) == set(real.keys())
        _assert_shape(real, mock)

    def test_userinfo_error_shape_documented_divergence(self, client):
        """Real Google returns a flat 401 {error, error_description}
        (userinfo_error_invalid_credentials.json); auth returns the
        contract-PINNED structured envelope {"error": {code, status, message, hint}}
        plus WWW-Authenticate. Both are 401."""
        real = load_fixture("userinfo_error_invalid_credentials.json")
        assert set(real.keys()) == {"error", "error_description"}
        mock = client.get("/oauth2/v2/userinfo",
                          headers={"Authorization": "Bearer invalid"})
        assert mock.status_code == 401
        err = mock.json()["error"]
        assert {"code", "status", "message"} <= set(err.keys())
        assert err["status"] == "UNAUTHENTICATED"
        assert "WWW-Authenticate" in mock.headers


class TestDeviceConformance:
    def test_device_code_response_keys(self, client):
        real = load_fixture("device_code_response.json")
        mock = client.post("/oauth2/device/code", data={
            "client_id": "gws-cli", "scope": "email"}).json()
        missing = set(real.keys()) - set(mock.keys())
        assert not missing, f"Mock device response missing Google keys: {missing}"
        # extras are the RFC 8628 names Google omits
        assert set(mock.keys()) - set(real.keys()) == {
            "verification_uri", "verification_uri_complete"}
        for key in set(real) & set(mock):
            if key != "verification_url":
                _assert_shape(real[key], mock[key], path=key)

    def test_device_error_shape(self, client):
        real = load_fixture("device_code_error_invalid_client.json")
        mock = client.post("/oauth2/device/code", data={
            "client_id": "nonexistent", "scope": "email"})
        assert mock.status_code == 401
        body = mock.json()
        assert set(real.keys()) <= set(body.keys())
        assert body["error"] == real["error"] == "invalid_client"


class TestErrorConformance:
    def test_tokeninfo_error_shape_documented(self, client):
        """Google's tokeninfo returns 400 {error, error_description} for bad tokens
        (tokeninfo_error_invalid.json). auth replaces tokeninfo with RFC 7662
        introspection: unknown tokens are 200 {"active": false} (documented)."""
        real = load_fixture("tokeninfo_error_invalid.json")
        assert set(real.keys()) == {"error", "error_description"}
        mock = client.post("/oauth2/introspect", data={"token": "invalid"})
        assert mock.status_code == 200
        assert mock.json() == {"active": False}

    def test_revoke_always_200_documented_divergence(self, client):
        """Google's revoke returns 400 {"error": "invalid_token"} for unknown tokens
        (revoke_error_invalid_token.json). auth follows RFC 7009 strictly and
        always returns 200 (pinned by the interface contract)."""
        real = load_fixture("revoke_error_invalid_token.json")
        assert real["error"] == "invalid_token"
        mock = client.post("/oauth2/revoke", data={"token": "invalid"})
        assert mock.status_code == 200


class TestSpecCoverage:
    def test_every_spec_endpoint_in_coverage(self, client):
        spec = json.loads((Path(__file__).parent / "fixtures" /
                           "googleoauth_api_spec.json").read_text())
        coverage = json.loads((Path(__file__).parent / "fixtures" /
                               "mock_coverage.json").read_text())
        spec_ids = {e["id"] for r in spec["resources"].values() for e in r["endpoints"]}
        coverage_ids = {e["id"] for e in coverage["endpoints"]}
        assert spec_ids == coverage_ids

    def test_all_implemented_endpoints_respond(self, client):
        coverage = json.loads((Path(__file__).parent / "fixtures" /
                               "mock_coverage.json").read_text())
        for e in coverage["endpoints"]:
            assert e["implemented"] is True
            assert e["tests"], f"{e['id']} has no tests"

    def test_fixture_files_all_referenced(self, client):
        """Every fixture (except _capture_metadata.json) appears in a test file."""
        test_dir = Path(__file__).parent
        sources = "".join(p.read_text() for p in test_dir.glob("*.py"))
        for fixture in FIXTURES_DIR.glob("*.json"):
            if fixture.name.startswith("_"):
                continue
            assert fixture.name in sources, f"Fixture {fixture.name} not referenced"
