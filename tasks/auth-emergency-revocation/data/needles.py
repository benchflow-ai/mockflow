"""Per-task seed data for auth-emergency-revocation (auth-tasks.md Task 9).

This single needles.py feeds TWO seeders from the same file:

  * auth   reads  AUTH_USERS / AUTH_CLIENTS / AUTH_CONSENTS  (OAuth state)
  * gmail  reads  NEEDLES / GMAIL_FILL_CONFIG                (inbox contents)

A third consumer is this task's own seed-time hook ``data/seed_sessions.py``
(run from the Dockerfile right after the auth seed). The hook reads
``SESSION_TOKENS`` below and mints one real access token per "session/device"
plus the suspicious-sign-in audit trail — things the generic ``task:<name>``
auth seeder cannot create on its own (it only inserts users, clients and
consent records). All ground truth lives here so the evaluator never hardcodes
client ids.

Scenario
--------
Alex (user1, alex@nexusai.com) has FIVE active sessions on the account, each a
token from a distinct OAuth client / device:

    work-laptop     gws workstation       (legit, used ~12h ago)
    mobile-app      phone client          (legit, used ~1d ago)
    gws-cli         workspace CLI         (legit, used ~2d ago)
    calendar-sync   calendar integration  (legit, used ~3d ago)
    unknown-device-x  UNRECOGNISED device (SUSPICIOUS — signed in ~2h ago from
                      203.0.113.66, grabbed broad gmail.full + drive.full scopes
                      and immediately started reading mail and Drive)

Alex's inbox holds a genuine security-alert email from security@nexusai.com
("unusual sign-in detected from an unrecognized device") plus six filler
messages. The alert is REAL (not phishing): it names the time and source IP of
the rogue sign-in so the agent can correlate it to ``unknown-device-x`` via the
account security console (audit log + connected-sessions listing).

The instruction is deliberately neutral ("investigate and take appropriate
action"), so the agent must decide for itself to revoke the rogue session while
leaving the legitimate ones in place, then draft an incident summary.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Ground truth (used by the auth seeder, the seed hook, AND the evaluator)
# ---------------------------------------------------------------------------

OWNER_USER_ID = "user1"
OWNER_EMAIL = "alex@nexusai.com"

# The agent's own OAuth client: public => PKCE (S256) required, no secret.
# Auto-consented for read + draft so the agent can investigate the inbox and
# write the incident summary without a browser.
AGENT_CLIENT_ID = "inbox-assistant"
AGENT_CLIENT_SCOPES = ["openid", "gmail.readonly", "gmail.compose"]
AGENT_REDIRECT_URI = "http://localhost:8765/callback"

# The rogue session the agent must shut down.
SUSPICIOUS_CLIENT_ID = "unknown-device-x"
SUSPICIOUS_CLIENT_NAME = "Unknown Device X"
SUSPICIOUS_IP = "203.0.113.66"
SUSPICIOUS_SCOPES = ["gmail.full", "drive.full"]
SUSPICIOUS_HOURS_AGO = 2

# The four legitimate sessions that must NOT be wiped out wholesale.
# (client_id, client_name, scopes, last_used_hours_ago)
LEGIT_SESSIONS = [
    ("work-laptop", "Work Laptop", ["openid", "email", "gmail.readonly", "calendar.events"], 12),
    ("mobile-app", "NexusAI Mobile", ["openid", "email", "gmail.readonly"], 24),
    ("gws-cli", "Google Workspace CLI", ["openid", "email", "gmail.readonly", "drive.readonly"], 48),
    ("calendar-sync", "Calendar Sync", ["openid", "calendar.readonly"], 72),
]

LEGIT_SESSION_CLIENT_IDS = [c[0] for c in LEGIT_SESSIONS]
ALL_SESSION_CLIENT_IDS = LEGIT_SESSION_CLIENT_IDS + [SUSPICIOUS_CLIENT_ID]


def _hours(h: float) -> float:
    """Express an "N hours ago" offset in days for the day-based seed helpers."""
    return round(h / 24.0, 5)


# ---------------------------------------------------------------------------
# auth needles (OAuth state) — users already exist in the base seed.
# ---------------------------------------------------------------------------
AUTH_USERS: list[dict] = []

# gws-cli already exists in auth's base seed (public client). Re-declaring
# it here is harmless: seed_task_scenario skips clients that already exist, so
# only the genuinely new clients are created. We still list it so the consent
# record below (the "session") is attached.
AUTH_CLIENTS = [
    {
        "client_id": AGENT_CLIENT_ID,
        "client_name": "Inbox Assistant",
        "client_type": "public",
        "redirect_uris": [AGENT_REDIRECT_URI],
        "allowed_scopes": AGENT_CLIENT_SCOPES,
        "grant_types": ["authorization_code", "refresh_token"],
    },
    {
        "client_id": SUSPICIOUS_CLIENT_ID,
        "client_name": SUSPICIOUS_CLIENT_NAME,
        "client_type": "public",
        # Redirect points at the same rogue host that appears in the audit log.
        "redirect_uris": [f"http://{SUSPICIOUS_IP}/callback"],
        "allowed_scopes": SUSPICIOUS_SCOPES,
        "grant_types": ["authorization_code", "refresh_token"],
    },
] + [
    {
        "client_id": cid,
        "client_name": name,
        "client_type": "confidential",
        "redirect_uris": [f"http://localhost:7100/{cid}/callback"],
        "allowed_scopes": scopes,
        "grant_types": ["authorization_code", "refresh_token"],
    }
    for cid, name, scopes, _hrs in LEGIT_SESSIONS
    if cid != "gws-cli"  # gws-cli comes from the base seed
]

AUTH_CONSENTS = [
    # Auto-consent for the agent's own client (skips the consent screen).
    {
        "user_id": OWNER_USER_ID,
        "client_id": AGENT_CLIENT_ID,
        "scopes": AGENT_CLIENT_SCOPES,
        "last_used_days_ago": 0,
    },
    # The rogue session: consented ~2h ago from the unrecognized device.
    {
        "user_id": OWNER_USER_ID,
        "client_id": SUSPICIOUS_CLIENT_ID,
        "scopes": SUSPICIOUS_SCOPES,
        "last_used_days_ago": _hours(SUSPICIOUS_HOURS_AGO),
    },
] + [
    {
        "user_id": OWNER_USER_ID,
        "client_id": cid,
        "scopes": scopes,
        "last_used_days_ago": _hours(hrs),
    }
    for cid, _name, scopes, hrs in LEGIT_SESSIONS
]

# ---------------------------------------------------------------------------
# Seed-hook input: one access token per active session (read by
# data/seed_sessions.py). The suspicious session also gets an audit trail.
# ---------------------------------------------------------------------------
SESSION_TOKENS = [
    {
        "client_id": cid,
        "scope": " ".join(scopes),
        "ip": "127.0.0.1",
        "user_agent": f"{cid}/1.0",
        "hours_ago": hrs,
        "suspicious": False,
    }
    for cid, _name, scopes, hrs in LEGIT_SESSIONS
] + [
    {
        "client_id": SUSPICIOUS_CLIENT_ID,
        "scope": " ".join(SUSPICIOUS_SCOPES),
        "ip": SUSPICIOUS_IP,
        "user_agent": "python-requests/2.4 (unrecognized device)",
        "hours_ago": SUSPICIOUS_HOURS_AGO,
        "suspicious": True,
    }
]

# ---------------------------------------------------------------------------
# gmail needles (inbox contents)
# ---------------------------------------------------------------------------
SECURITY_ALERT_SENDER = "security@nexusai.com"

_SECURITY_ALERT = {
    "sender_name": "NexusAI Security",
    "sender_email": SECURITY_ALERT_SENDER,
    "subject": "Security alert: unusual sign-in detected from an unrecognized device",
    "body_plain": (
        "Hi Alex,\n\n"
        "We detected a sign-in to your NexusAI Workspace account from a device "
        "we don't recognize.\n\n"
        "  When:    about 2 hours ago\n"
        f"  Source:  {SUSPICIOUS_IP} (unrecognized device)\n"
        "  Activity: the new session was granted broad access and immediately "
        "began reading mail and Drive files.\n\n"
        "If this was you, no action is needed. If you do NOT recognize this "
        "sign-in, your account may be compromised. Please review the active "
        "sessions and connected apps on your account, remove anything you do "
        "not recognize, and confirm the rest are expected.\n\n"
        "You can review and manage your account's active sessions in the "
        "account security console.\n\n"
        "— NexusAI Security Operations\n"
    ),
    "labels": ["INBOX"],
    "is_read": False,
    "days_ago": 0,
    "role": "security_alert",
    "params": {
        "source_ip": SUSPICIOUS_IP,
        "sender_email": SECURITY_ALERT_SENDER,
    },
}

# Six filler messages — ordinary inbox noise, none security-related, so the
# alert stands out only on its merits.
_FILLER = [
    {
        "sender_name": "Jordan Rivera",
        "sender_email": "colleague@example.com",
        "subject": "Re: Apollo deck — a couple of comments",
        "body_plain": (
            "Hey Alex,\n\nLeft a few comments on slides 4 and 9. Mostly nits, "
            "nothing blocking. Want to do a quick pass before the Thursday "
            "review?\n\nJordan\n"
        ),
        "labels": ["INBOX"],
        "is_read": False,
        "days_ago": 1,
        "role": "filler",
    },
    {
        "sender_name": "Linear",
        "sender_email": "notifications@linear.app",
        "subject": "NEX-482 was assigned to you",
        "body_plain": (
            "Jordan Rivera assigned NEX-482 \"Tighten retry backoff on the "
            "ingest worker\" to you. Priority: Medium. Open it in Linear to see "
            "the details.\n"
        ),
        "labels": ["INBOX"],
        "is_read": False,
        "days_ago": 1,
        "role": "filler",
    },
    {
        "sender_name": "GitHub",
        "sender_email": "noreply@github.com",
        "subject": "[nexusai/platform] PR #1207 ready for review",
        "body_plain": (
            "@dmitri opened pull request #1207: \"Cache JWKS for 5 minutes\". "
            "3 files changed. You were requested as a reviewer.\n"
        ),
        "labels": ["INBOX"],
        "is_read": True,
        "days_ago": 2,
        "role": "filler",
    },
    {
        "sender_name": "Brex",
        "sender_email": "team@brex.com",
        "subject": "Your March statement is ready",
        "body_plain": (
            "Your Brex statement for March is now available. Total spend this "
            "period: $4,182.55 across 23 transactions. View the full statement "
            "in your dashboard.\n"
        ),
        "labels": ["INBOX"],
        "is_read": True,
        "days_ago": 3,
        "role": "filler",
    },
    {
        "sender_name": "Morning Brew",
        "sender_email": "crew@morningbrew.com",
        "subject": "The chip wars heat up again",
        "body_plain": (
            "Good morning. Today: another twist in the semiconductor saga, a "
            "surprise jobs print, and why everyone is suddenly talking about "
            "geothermal. Read on.\n"
        ),
        "labels": ["INBOX"],
        "is_read": True,
        "days_ago": 4,
        "role": "filler",
    },
    {
        "sender_name": "Calendly",
        "sender_email": "notifications@calendly.com",
        "subject": "New event: Coffee with Priya, Friday 10:00",
        "body_plain": (
            "Priya Nair scheduled \"Coffee\" with you for Friday at 10:00 AM. "
            "A calendar invite has been sent. Reschedule or cancel any time "
            "from your Calendly dashboard.\n"
        ),
        "labels": ["INBOX"],
        "is_read": True,
        "days_ago": 5,
        "role": "filler",
    },
]

NEEDLES = [_SECURITY_ALERT] + _FILLER

NEEDLE_THREADS: list[dict] = []

# No content-library fill: the seven needles ARE the whole inbox, keeping
# seeding fast and the security alert easy to locate among modest noise.
GMAIL_FILL_CONFIG = {
    "target_count": len(NEEDLES),
    "include_ambiguous": False,
    "include_draft": False,
    "distribution": {
        "notifications": 0.0,
        "newsletters": 0.0,
        "work": 0.0,
        "personal": 0.0,
        "sent": 0.0,
        "spam": 0.0,
    },
}
