"""The testing helpers themselves: keypairs, make_jwt claims, jwks_for shape."""

import time

import jwt as pyjwt

from env_0_auth_client.testing import generate_test_keypair, jwks_for, make_jwt


class TestGenerateTestKeypair:
    def test_returns_usable_rsa_pair(self, keypair):
        private_key, public_key = keypair
        token = pyjwt.encode({"a": 1}, private_key, algorithm="RS256")
        assert pyjwt.decode(token, public_key, algorithms=["RS256"]) == {"a": 1}

    def test_pairs_are_distinct(self, keypair, other_keypair):
        assert keypair[0].private_numbers() != other_keypair[0].private_numbers()


class TestJwksFor:
    def test_shape(self, public_key):
        jwks = jwks_for(public_key, kid="my-kid")
        assert list(jwks) == ["keys"]
        (jwk,) = jwks["keys"]
        assert jwk["kid"] == "my-kid"
        assert jwk["alg"] == "RS256"
        assert jwk["use"] == "sig"
        assert jwk["kty"] == "RSA"
        assert "n" in jwk and "e" in jwk

    def test_loadable_by_pyjwt(self, public_key):
        jwks = jwks_for(public_key, kid="k1")
        key = pyjwt.PyJWK.from_dict(jwks["keys"][0]).key
        assert key.public_numbers() == public_key.public_numbers()


class TestMakeJwt:
    def test_claims_match_env_0_auth_token_format(self, keypair):
        private_key, public_key = keypair
        token = make_jwt(
            private_key=private_key,
            kid="k1",
            sub="user_002",
            client_id="mail-merge-pro",
            scope="gmail.readonly gmail.send",
        )
        header = pyjwt.get_unverified_header(token)
        assert header["alg"] == "RS256"
        assert header["kid"] == "k1"

        claims = pyjwt.decode(token, public_key, algorithms=["RS256"], options={"verify_aud": False})
        assert claims["iss"] == "http://localhost:9000"
        assert claims["sub"] == "user_002"
        assert claims["aud"] == "mail-merge-pro"
        assert claims["client_id"] == "mail-merge-pro"
        assert claims["scope"] == "gmail.readonly gmail.send"
        assert claims["email"] == "user_002@clawsbench.local"
        assert claims["jti"].startswith("tok_") and len(claims["jti"]) == 4 + 24
        assert claims["exp"] - claims["iat"] == 3600
        assert claims["iat"] <= int(time.time())

    def test_negative_expires_in_makes_expired_token(self, keypair):
        token = make_jwt(private_key=keypair[0], expires_in=-100)
        claims = pyjwt.decode(token, options={"verify_signature": False})
        assert claims["exp"] < time.time()

    def test_issuer_and_extra_claims_overrides(self, keypair):
        token = make_jwt(
            private_key=keypair[0],
            issuer="http://custom-issuer:9000",
            extra_claims={"act": {"sub": "svc-backup"}},
        )
        claims = pyjwt.decode(token, options={"verify_signature": False})
        assert claims["iss"] == "http://custom-issuer:9000"
        assert claims["act"] == {"sub": "svc-backup"}

    def test_issuer_follows_env(self, monkeypatch, keypair):
        monkeypatch.setenv("AUTH_URL", "http://auth.docker:9000")
        token = make_jwt(private_key=keypair[0])
        claims = pyjwt.decode(token, options={"verify_signature": False})
        assert claims["iss"] == "http://auth.docker:9000"
