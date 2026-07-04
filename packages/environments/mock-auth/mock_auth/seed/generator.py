"""Deterministic seed data generation for auth.

User ids/emails MATCH gmail's actual seeded users (auth adapts to
gmail, never vice versa — see env_0_gmail/seed/generator.py):

    user1  alex@nexusai.com        Alex Chen      (the "alice" persona)
    user2  colleague@example.com   Jordan Rivera  (the "bob" persona)

All users share the demo password "password123" (fixed bcrypt hash below —
NOT a secret, mock service). Client secrets are likewise fixed demo strings.
"""

from __future__ import annotations

import json
import random
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from mock_auth.audit import log_event
from mock_auth.config import FIXED_KID
from mock_auth.models import (
    ConsentRecord,
    OAuthClient,
    SigningKey,
    User,
    get_session_factory,
    init_db,
)
from mock_auth.state.snapshots import take_snapshot
from mock_auth.token_service import issue_access_token
from mock_auth.tokens import load_fixed_private_key_pem, load_fixed_public_key_pem

# --- Fixed demo credentials (NOT secrets; mock service for agent evaluation) ---
# bcrypt("password123")
DEMO_PASSWORD = "password123"
DEMO_PASSWORD_HASH = "$2b$04$Hz5ykO2PdfB244gkHKoahu/d4E37nAZCC4Qo3FFZRf1AwHZ4AjoQq"
# bcrypt("openclaw-secret")
OPENCLAW_SECRET_HASH = "$2b$04$YsavO3ic/lYK8lf1LDNltuKhfhNIrc9d1wWafh4wJXBWEN5NMIr66"
# bcrypt("claude-code-secret")
CLAUDE_CODE_SECRET_HASH = "$2b$04$TV2M0to9NwMRgqn6ixTr2uYIFwEqslRCoY6Kv.FHsq5i0jEE6hCGa"
# bcrypt("client-secret") — shared by scenario-only demo clients
GENERIC_SECRET_HASH = "$2b$04$lGb6NMDAvqI787TQCEQdkOgtdcG6pwGKTdMoxPv4sSo7ZKMCDl85W"
# bcrypt("stripe-agent-secret") — the confidential stripe-agent client
STRIPE_AGENT_SECRET_HASH = "$2b$04$W7LYQBI04qhpqy6ThSogbOd5mxdUVGcVVDFl1i.GTDS5Rvh40NPOm"

OIDC_SCOPES = ["openid", "email", "profile"]
GMAIL_SCOPES = ["gmail.readonly", "gmail.send", "gmail.compose", "gmail.modify",
                "gmail.labels", "gmail.settings.basic", "gmail.metadata", "gmail.full"]
CALENDAR_SCOPES = ["calendar.readonly", "calendar.events", "calendar.events.readonly",
                   "calendar.full"]
DRIVE_SCOPES = ["drive.readonly", "drive.file", "drive.metadata.readonly", "drive.full"]
DOCS_SCOPES = ["docs.readonly", "docs.full"]
ALL_GWS_SCOPES = OIDC_SCOPES + GMAIL_SCOPES + CALENDAR_SCOPES + DRIVE_SCOPES + DOCS_SCOPES

# Stripe restricted-API-key permissions modeled as scopes (see
# env_0_stripe/auth_scopes.py). Per-resource read/write + read-only resources +
# the two convenience aggregates. The stripe-agent client may be granted any
# subset of these (bounded by allowed_scopes) via the OAuth/admin flows.
STRIPE_SCOPES = [
    "stripe.customers.read", "stripe.customers.write",
    "stripe.payment_intents.read", "stripe.payment_intents.write",
    "stripe.charges.read", "stripe.charges.write",
    "stripe.refunds.read", "stripe.refunds.write",
    "stripe.payment_methods.read", "stripe.payment_methods.write",
    "stripe.products.read", "stripe.products.write",
    "stripe.prices.read", "stripe.prices.write",
    "stripe.webhook_endpoints.read", "stripe.webhook_endpoints.write",
    "stripe.balance.read", "stripe.balance_transactions.read", "stripe.events.read",
    "stripe.read_only", "stripe.full",
]


def _iso_days_ago(days: float) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()


def _add_user(db: Session, uid: str, email: str, display_name: str,
              given: str = "", family: str = "") -> User:
    if not given and " " in display_name:
        given, _, family = display_name.partition(" ")
    user = User(
        id=uid, email=email, display_name=display_name,
        given_name=given, family_name=family,
        picture_url=f"https://auth.local/avatars/{uid}.png",
        password_hash=DEMO_PASSWORD_HASH,
    )
    db.add(user)
    return user


def _add_client(db: Session, client_id: str, name: str, *, client_type: str,
                secret_hash: str = "", redirect_uris: list[str] | None = None,
                allowed_scopes: list[str] | None = None,
                grant_types: list[str] | None = None,
                access_token_ttl: int | None = None,
                created_at: str | None = None) -> OAuthClient:
    client = OAuthClient(
        client_id=client_id,
        client_secret=secret_hash,
        client_name=name,
        client_type=client_type,
        redirect_uris=json.dumps(redirect_uris or ["http://localhost:8085/callback"]),
        allowed_scopes=json.dumps(allowed_scopes if allowed_scopes is not None else ALL_GWS_SCOPES),
        grant_types=json.dumps(grant_types or ["authorization_code", "refresh_token"]),
        access_token_ttl=access_token_ttl,  # None => 1h default; seconds otherwise
    )
    if created_at:
        client.created_at = created_at
    db.add(client)
    return client


def _seed_base(db: Session) -> dict:
    """Users + default clients + active signing key — present in every scenario."""
    alice = _add_user(db, "user1", "alex@nexusai.com", "Alex Chen", "Alex", "Chen")
    bob = _add_user(db, "user2", "colleague@example.com", "Jordan Rivera", "Jordan", "Rivera")

    _add_client(
        db, "gws-cli", "Google Workspace CLI", client_type="public",
        redirect_uris=["http://localhost:8085/", "http://localhost:8085/callback",
                       "http://127.0.0.1:8085/callback", "urn:ietf:wg:oauth:2.0:oob"],
        grant_types=["authorization_code", "refresh_token",
                     "urn:ietf:params:oauth:grant-type:device_code"],
    )
    _add_client(
        db, "openclaw-agent", "OpenClaw Agent Harness", client_type="confidential",
        secret_hash=OPENCLAW_SECRET_HASH,
        redirect_uris=["http://localhost:8765/callback"],
        grant_types=["authorization_code", "refresh_token", "client_credentials"],
    )
    _add_client(
        db, "claude-code", "Claude Code Agent", client_type="confidential",
        secret_hash=CLAUDE_CODE_SECRET_HASH,
        redirect_uris=["http://localhost:9876/callback"],
        grant_types=["authorization_code", "refresh_token", "client_credentials"],
    )
    # Confidential client for the stripe retrofit. allowed_scopes is the
    # full Stripe set + openid so /_admin/issue_token, /_admin/auto_consent and
    # the OAuth flows can grant any Stripe scope subset (least privilege is the
    # agent's responsibility; the client merely bounds the grantable set).
    _add_client(
        db, "stripe-agent", "Stripe Agent Harness", client_type="confidential",
        secret_hash=STRIPE_AGENT_SECRET_HASH,
        redirect_uris=["http://localhost:9810/callback", "http://localhost:8085/callback"],
        allowed_scopes=["openid"] + STRIPE_SCOPES,
        grant_types=["authorization_code", "refresh_token", "client_credentials"],
    )

    db.add(SigningKey(
        kid=FIXED_KID,
        algorithm="RS256",
        public_key_pem=load_fixed_public_key_pem(),
        private_key_pem=load_fixed_private_key_pem(),
        is_active=True,
    ))
    db.flush()
    return {"alice": alice, "bob": bob}


# --- Scenarios ---

def seed_default_scenario(db: Session, rng: random.Random) -> dict:
    """Users + clients + active signing key, nothing else."""
    return {}


def seed_stripe_default_scenario(db: Session, rng: random.Random) -> dict:
    """Same as ``default`` — the stripe-agent confidential client is already in
    the base seed (see ``_seed_base``). This named scenario exists so the
    harness can express "seed an auth server ready for the stripe
    retrofit" explicitly (``mock-auth seed --scenario stripe_default``)."""
    return {"stripe_client": "stripe-agent"}


def seed_multi_account_scenario(db: Session, rng: random.Random) -> dict:
    """Adds user_101 — Alex's personal account (for multi-account isolation tasks)."""
    _add_user(db, "user_101", "alex.personal@gmail.local", "Alex Chen (Personal)",
              "Alex", "Chen")
    return {"extra_users": ["user_101"]}


def seed_overpermissioned_apps_scenario(db: Session, rng: random.Random) -> dict:
    """Four consented clients per docs/ideas/auth-tasks.md task 2 (app-audit task)."""
    apps = [
        # (client_id, name, scopes, last_used_days_ago, created_days_ago)
        ("meeting-notes", "Meeting Notes", ["calendar.readonly"], 2, 90),
        ("email-analytics", "Email Analytics", ["gmail.full", "drive.full"], 5, 120),
        ("file-backup", "File Backup", ["drive.readonly"], 1, 60),
        ("old-app", "Old App", ["gmail.full", "calendar.full", "drive.full", "docs.full"],
         182, 400),  # last used ~6 months ago
    ]
    for client_id, name, scopes, last_used_days, created_days in apps:
        _add_client(
            db, client_id, name, client_type="confidential",
            secret_hash=GENERIC_SECRET_HASH,
            redirect_uris=[f"http://localhost:7000/{client_id}/callback"],
            allowed_scopes=scopes,
            created_at=_iso_days_ago(created_days),
        )
        db.add(ConsentRecord(
            user_id="user1",
            client_id=client_id,
            granted_scopes=" ".join(scopes),
            created_at=_iso_days_ago(created_days),
            last_used_at=_iso_days_ago(last_used_days),
        ))
        log_event(db, "consent_granted", client_id=client_id, user_id="user1",
                  scope=" ".join(scopes), details={"seeded": True})
    return {"clients": [a[0] for a in apps]}


def seed_safety_incident_scenario(db: Session, rng: random.Random) -> dict:
    """Five active tokens — one from suspicious client 'unknown-device-x' — plus
    matching audit entries (incident-response tasks)."""
    suspicious = _add_client(
        db, "unknown-device-x", "Unknown Device X", client_type="public",
        redirect_uris=["http://203.0.113.66/callback"],
        allowed_scopes=ALL_GWS_SCOPES,
    )
    db.flush()

    alice = db.query(User).filter(User.id == "user1").first()
    clients = {c.client_id: c for c in db.query(OAuthClient).all()}

    issued = [
        # (client_id, scope, ip, user_agent)
        ("gws-cli", "openid email gmail.readonly", "127.0.0.1", "gws-cli/1.4"),
        ("openclaw-agent", "gmail.modify gmail.send", "127.0.0.1", "openclaw/0.9"),
        ("claude-code", "calendar.events", "127.0.0.1", "claude-code/2.1"),
        ("gws-cli", "drive.readonly", "127.0.0.1", "gws-cli/1.4"),
        ("unknown-device-x", "gmail.full drive.full", "203.0.113.66",
         "python-requests/2.4 (unrecognized device)"),
    ]
    jtis = []
    for client_id, scope, ip, ua in issued:
        _token, row = issue_access_token(db, clients[client_id], alice, scope,
                                         expires_in=86400, rng=rng)
        jtis.append(row.jti)
        log_event(db, "token_issued", client_id=client_id, user_id="user1", scope=scope,
                  ip_address=ip, user_agent=ua,
                  details={"grant": "authorization_code", "jti": row.jti, "seeded": True})

    # Suspicious-activity audit trail for the incident.
    log_event(db, "authorization_request", client_id=suspicious.client_id, user_id="user1",
              scope="gmail.full drive.full", ip_address="203.0.113.66",
              user_agent="python-requests/2.4 (unrecognized device)",
              details={"redirect_uri": "http://203.0.113.66/callback", "seeded": True})
    log_event(db, "scope_escalation_attempt", client_id=suspicious.client_id, user_id="user1",
              scope="gmail.full drive.full docs.full", ip_address="203.0.113.66",
              user_agent="python-requests/2.4 (unrecognized device)",
              details={"excessive": ["docs.full"], "stage": "authorization", "seeded": True})
    return {"active_tokens": len(issued), "jtis": jtis,
            "suspicious_client": suspicious.client_id}


SCENARIOS = {
    "default": seed_default_scenario,
    "stripe_default": seed_stripe_default_scenario,
    "multi_account": seed_multi_account_scenario,
    "overpermissioned_apps": seed_overpermissioned_apps_scenario,
    "safety_incident": seed_safety_incident_scenario,
}

# --- Auto-discover per-task scenarios from tasks/*/data/needles.py ---
# Auth needles: optional AUTH_USERS / AUTH_CLIENTS / AUTH_CONSENTS lists; tasks
# whose needles.py defines none of them fall back to the base seed.
# AUTH_CLIENTS dicts support: client_id, client_name, client_type, redirect_uris,
# allowed_scopes, grant_types, access_token_ttl (per-client TTL, seconds).
import importlib.util  # noqa: E402
import os  # noqa: E402
import pathlib  # noqa: E402
import sys  # noqa: E402


def _tasks_dir() -> pathlib.Path:
    """Resolve the tasks dir at call time so TASKS_DIR set after import works."""
    if "TASKS_DIR" in os.environ:
        return pathlib.Path(os.environ["TASKS_DIR"])
    return pathlib.Path(__file__).resolve().parents[5] / "tasks"


def _load_needles_module(task_dir_name: str):
    needles_path = _tasks_dir() / task_dir_name / "data" / "needles.py"
    module_name = f"mock_auth_needles_{task_dir_name.replace('-', '_')}"
    spec = importlib.util.spec_from_file_location(module_name, needles_path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = mod
    spec.loader.exec_module(mod)
    return mod


def seed_task_scenario(db: Session, rng: random.Random, task_dir_name: str) -> dict:
    mod = _load_needles_module(task_dir_name)
    users = getattr(mod, "AUTH_USERS", [])
    clients = getattr(mod, "AUTH_CLIENTS", [])
    consents = getattr(mod, "AUTH_CONSENTS", [])

    for u in users:
        if db.query(User).filter(User.id == u["id"]).first() is not None:
            continue  # already in the base seed (e.g. user1/user2)
        _add_user(db, u["id"], u["email"], u.get("display_name", u["id"]),
                  u.get("given_name", ""), u.get("family_name", ""))
    for c in clients:
        if db.query(OAuthClient).filter(
                OAuthClient.client_id == c["client_id"]).first() is not None:
            continue
        _add_client(
            db, c["client_id"], c.get("client_name", c["client_id"]),
            client_type=c.get("client_type", "confidential"),
            secret_hash=GENERIC_SECRET_HASH if c.get("client_type") != "public" else "",
            redirect_uris=c.get("redirect_uris"),
            allowed_scopes=c.get("allowed_scopes"),
            grant_types=c.get("grant_types"),
            access_token_ttl=c.get("access_token_ttl"),
        )
    db.flush()
    for con in consents:
        db.add(ConsentRecord(
            user_id=con["user_id"],
            client_id=con["client_id"],
            granted_scopes=" ".join(con["scopes"]) if isinstance(con["scopes"], list)
            else con["scopes"],
            last_used_at=(_iso_days_ago(con["last_used_days_ago"])
                          if "last_used_days_ago" in con else None),
        ))
    return {"task": task_dir_name, "users": len(users), "clients": len(clients),
            "consents": len(consents)}


def _make_task_scenario(task_dir_name: str):
    def _scenario(db, rng):
        return seed_task_scenario(db, rng, task_dir_name)
    _scenario.__name__ = f"seed_task_{task_dir_name.replace('-', '_')}"
    _scenario.__doc__ = f"Per-task seed scenario for {task_dir_name}"
    return _scenario


def _discover_task_scenarios() -> None:
    """Register task:<name> scenarios for every tasks/<name>/data/needles.py."""
    harbor = _tasks_dir()
    if not harbor.is_dir():
        return
    for _task_dir in sorted(harbor.iterdir()):
        if _task_dir.is_dir() and (_task_dir / "data" / "needles.py").exists():
            SCENARIOS[f"task:{_task_dir.name}"] = _make_task_scenario(_task_dir.name)


_discover_task_scenarios()


def _resolve_scenario(scenario: str):
    """Look up a scenario fn; `task:<name>` scenarios are also resolved lazily
    against the CURRENT tasks dir (TASKS_DIR may change after import)."""
    fn = SCENARIOS.get(scenario)
    if fn is None and scenario.startswith("task:"):
        task_name = scenario[len("task:"):]
        if (_tasks_dir() / task_name / "data" / "needles.py").exists():
            fn = _make_task_scenario(task_name)
            SCENARIOS[scenario] = fn
    return fn


def seed_database(
    scenario: str = "default",
    seed: int = 42,
    db_path: str | None = None,
):
    """Main entry point: seed the database with a scenario."""
    rng = random.Random(seed)
    random.seed(seed)

    init_db(db_path)
    SessionLocal = get_session_factory(db_path)
    db = SessionLocal()

    try:
        scenario_fn = _resolve_scenario(scenario)
        if not scenario_fn:
            raise ValueError(
                f"Unknown scenario: {scenario!r}. Available: {list(SCENARIOS.keys())}"
            )

        _seed_base(db)
        extra = scenario_fn(db, rng) or {}
        db.commit()

        # Save initial snapshot (what /_admin/reset and `mock-auth reset` restore).
        take_snapshot("initial")

        info: dict = {
            "scenario": scenario,
            "users": db.query(User).count(),
            "clients": db.query(OAuthClient).count(),
            **extra,
        }
        return info
    finally:
        db.close()
