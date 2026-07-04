"""Token generation, hashing, and JWT signing/verification helpers.

Token randomness uses `secrets.token_hex` by default; when the env var
`AUTH_DETERMINISTIC_SEED` is set, a module-level `random.Random(seed)`
produces the hex instead (deterministic replay).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import random
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path

import jwt as pyjwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from mock_auth.config import FIXED_KID

KEYS_DIR = Path(__file__).resolve().parent / "seed" / "keys"

_rng: random.Random | None = None
_rng_initialized = False


def reset_token_rng():
    """Re-read AUTH_DETERMINISTIC_SEED on next token generation (tests/reseed)."""
    global _rng, _rng_initialized
    _rng = None
    _rng_initialized = False


def _get_rng() -> random.Random | None:
    global _rng, _rng_initialized
    if not _rng_initialized:
        seed = os.environ.get("AUTH_DETERMINISTIC_SEED")
        _rng = random.Random(seed) if seed is not None else None
        _rng_initialized = True
    return _rng


def token_hex(nbytes: int, rng: random.Random | None = None) -> str:
    """Random hex string — seeded rng > deterministic env rng > secrets."""
    rng = rng or _get_rng()
    if rng is not None:
        return "".join(rng.choice("0123456789abcdef") for _ in range(nbytes * 2))
    return secrets.token_hex(nbytes)


def new_jti(rng: random.Random | None = None) -> str:
    return "tok_" + token_hex(12, rng)  # 24 hex chars


def new_refresh_token(rng: random.Random | None = None) -> str:
    return "rt_" + token_hex(24, rng)  # 48 hex chars


def new_auth_code(rng: random.Random | None = None) -> str:
    return token_hex(24, rng)


def new_device_code(rng: random.Random | None = None) -> str:
    return "dev_" + token_hex(24, rng)


def new_user_code(rng: random.Random | None = None) -> str:
    alphabet = "BCDFGHJKLMNPQRSTVWXZ"
    r = rng or _get_rng()
    if r is not None:
        chars = [r.choice(alphabet) for _ in range(8)]
    else:
        chars = [secrets.choice(alphabet) for _ in range(8)]
    return "".join(chars[:4]) + "-" + "".join(chars[4:])


def new_family_id(rng: random.Random | None = None) -> str:
    return "fam_" + token_hex(8, rng)


def sha256_hex(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def utc_ts(dt: datetime | None = None) -> int:
    return int((dt or datetime.now(timezone.utc)).timestamp())


def iso_in(seconds: int) -> str:
    """ISO-8601 UTC timestamp `seconds` from now."""
    return (datetime.now(timezone.utc) + timedelta(seconds=seconds)).isoformat()


def is_expired(iso_timestamp: str) -> bool:
    try:
        dt = datetime.fromisoformat(iso_timestamp)
    except (ValueError, TypeError):
        return True
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt <= datetime.now(timezone.utc)


# --- Fixed checked-in keypair (NOT a secret; mock service) ---

def _strip_comment_header(pem_text: str) -> bytes:
    """The checked-in PEM files carry a loud not-a-secret comment header; strip it."""
    idx = pem_text.find("-----BEGIN")
    return pem_text[idx:].encode("ascii")


def load_fixed_private_key_pem() -> str:
    text = (KEYS_DIR / f"{FIXED_KID}.pem").read_text()
    return _strip_comment_header(text).decode("ascii")


def load_fixed_public_key_pem() -> str:
    text = (KEYS_DIR / f"{FIXED_KID}.pub.pem").read_text()
    return _strip_comment_header(text).decode("ascii")


def generate_keypair_pem() -> tuple[str, str]:
    """Fresh random RSA-2048 keypair (used by /_admin/rotate_key; non-deterministic OK)."""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    priv = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("ascii")
    pub = key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("ascii")
    return priv, pub


def public_pem_to_jwk(public_key_pem: str, kid: str, alg: str = "RS256") -> dict:
    """Build a JWK dict from a public key PEM (Google-style JWKS entry)."""
    pub = serialization.load_pem_public_key(public_key_pem.encode("ascii"))
    numbers = pub.public_numbers()
    n_bytes = numbers.n.to_bytes((numbers.n.bit_length() + 7) // 8, "big")
    e_bytes = numbers.e.to_bytes((numbers.e.bit_length() + 7) // 8, "big")
    return {
        "kid": kid,
        "kty": "RSA",
        "alg": alg,
        "use": "sig",
        "n": b64url(n_bytes),
        "e": b64url(e_bytes),
    }


def sign_jwt(claims: dict, private_key_pem: str, kid: str) -> str:
    return pyjwt.encode(
        claims,
        private_key_pem,
        algorithm="RS256",
        headers={"kid": kid, "typ": "JWT"},
    )


def decode_jwt_unverified(token: str) -> tuple[dict, dict]:
    """Return (header, claims) without signature verification."""
    header = pyjwt.get_unverified_header(token)
    claims = pyjwt.decode(token, options={"verify_signature": False, "verify_exp": False})
    return header, claims


def verify_jwt(token: str, public_key_pem: str, verify_exp: bool = True) -> dict:
    """Verify signature (+exp) and return claims. Raises pyjwt exceptions on failure."""
    return pyjwt.decode(
        token,
        public_key_pem,
        algorithms=["RS256"],
        options={"verify_exp": verify_exp, "verify_aud": False},
    )


def pkce_verify(verifier: str, challenge: str, method: str | None) -> bool:
    """RFC 7636 verification: S256 (sha256+base64url) or plain.

    Comparisons are constant-time (hmac.compare_digest) and a non-ASCII
    verifier is rejected (never raises — a malformed verifier must yield
    invalid_grant, not a 500).
    """
    if not isinstance(verifier, str) or not isinstance(challenge, str):
        return False
    try:
        verifier_bytes = verifier.encode("ascii")
    except UnicodeEncodeError:
        return False  # RFC 7636 verifiers are unreserved ASCII only
    if method == "S256":
        computed = b64url(hashlib.sha256(verifier_bytes).digest())
        return hmac.compare_digest(computed.encode("ascii"), challenge.encode("utf-8"))
    # 'plain' or unspecified-with-challenge defaults to plain per RFC 7636
    return hmac.compare_digest(verifier_bytes, challenge.encode("utf-8"))


def details_json(details: dict | None) -> str | None:
    return json.dumps(details) if details else None
