"""Stripe-style ID generation: prefix + '_' + 24 random alphanumeric characters."""

from __future__ import annotations

import random
import secrets
import string

_ALNUM = string.ascii_letters + string.digits


def generate_id(prefix: str, rng: random.Random | None = None, length: int = 24) -> str:
    """Generate a Stripe-style id.

    When `rng` (a seeded random.Random) is provided — e.g. by the seed
    generator — ids are deterministic; otherwise `secrets` is used.
    """
    if rng is not None:
        body = "".join(rng.choice(_ALNUM) for _ in range(length))
    else:
        body = "".join(secrets.choice(_ALNUM) for _ in range(length))
    return f"{prefix}_{body}"


def client_secret_for(pi_id: str, rng: random.Random | None = None) -> str:
    """PaymentIntent client secret: `pi_..._secret_<24 alnum>`."""
    if rng is not None:
        body = "".join(rng.choice(_ALNUM) for _ in range(24))
    else:
        body = "".join(secrets.choice(_ALNUM) for _ in range(24))
    return f"{pi_id}_secret_{body}"


def generate_webhook_secret(rng: random.Random | None = None) -> str:
    """Webhook endpoint signing secret: `whsec_<32 alnum>` (real Stripe shape)."""
    if rng is not None:
        body = "".join(rng.choice(_ALNUM) for _ in range(32))
    else:
        body = "".join(secrets.choice(_ALNUM) for _ in range(32))
    return f"whsec_{body}"
