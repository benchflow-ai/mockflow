"""Multi-env seed data for multi-mail-slack-invite.

gmail reads: NEEDLES, NEEDLE_THREADS, GMAIL_FILL_CONFIG
slack reads: SEED_USERS, SEED_CHANNELS, SEED_MESSAGES, FILL_CONFIG
"""

from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_sibling(name: str):
    here = Path(__file__).parent
    spec = importlib.util.spec_from_file_location(name, here / f"{name}.py")
    mod  = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_sc = _load_sibling("scenarios")

CONTRIBUTORS = _sc.CONTRIBUTORS
EMAILS       = _sc.EMAILS

# ── Gmail ─────────────────────────────────────────────────────────────────────
# Each contributor email is a standalone inbox needle.

NEEDLES: list[dict] = EMAILS

NEEDLE_THREADS: list[dict] = []

GMAIL_FILL_CONFIG = {
    "target_count":      200,
    "include_ambiguous": False,
    "include_draft":     False,
}

# ── Slack ─────────────────────────────────────────────────────────────────────
# Contributors are pre-seeded as Slack users so the agent can invite them.
# The three task channels are NOT pre-seeded — the agent must create them.

SEED_USERS: list[dict] = [
    {
        "key":       c["slack_key"],
        "name":      c["slack_username"],
        "real_name": c["name"],
        "email":     c["canonical_email"],
        "title":     "Open-source contributor · SkillsBench",
    }
    for c in CONTRIBUTORS
]

SEED_CHANNELS: list[dict] = []   # agent creates the task channels

SEED_MESSAGES: dict = {}

FILL_CONFIG = {
    "base_scenario": "default",
}
