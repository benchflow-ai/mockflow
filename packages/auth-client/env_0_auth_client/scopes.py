"""Canonical auth scope names, human descriptions, and scope helpers.

Scope names are bare identifiers exactly as in docs/ideas/auth.md
(e.g. ``gmail.readonly``, ``chat:write``) -- NOT full Google URLs.
"""

from collections.abc import Iterable

# Type alias pinned by the interface contract:
#   key   = (HTTP_METHOD, route_path_template_as_registered_in_FastAPI)
#   value = list of scopes, ANY ONE of which grants access (OR logic).
# A route absent from the map requires authentication only (no scope check).
ScopeMap = dict[tuple[str, str], list[str]]

# --- OIDC ---
OPENID = "openid"
EMAIL = "email"
PROFILE = "profile"

# --- Gmail ---
GMAIL_READONLY = "gmail.readonly"
GMAIL_SEND = "gmail.send"
GMAIL_COMPOSE = "gmail.compose"
GMAIL_MODIFY = "gmail.modify"
GMAIL_LABELS = "gmail.labels"
GMAIL_SETTINGS_BASIC = "gmail.settings.basic"
GMAIL_METADATA = "gmail.metadata"
GMAIL_FULL = "gmail.full"

# --- Calendar ---
CALENDAR_READONLY = "calendar.readonly"
CALENDAR_EVENTS = "calendar.events"
CALENDAR_EVENTS_READONLY = "calendar.events.readonly"
CALENDAR_FULL = "calendar.full"

# --- Drive ---
DRIVE_READONLY = "drive.readonly"
DRIVE_FILE = "drive.file"
DRIVE_METADATA_READONLY = "drive.metadata.readonly"
DRIVE_FULL = "drive.full"

# --- Docs ---
DOCS_READONLY = "docs.readonly"
DOCS_FULL = "docs.full"

# --- Slack ---
CHANNELS_READ = "channels:read"
CHANNELS_HISTORY = "channels:history"
CHANNELS_WRITE = "channels:write"
CHAT_WRITE = "chat:write"
USERS_READ = "users:read"
USERS_READ_EMAIL = "users:read.email"
REACTIONS_READ = "reactions:read"
REACTIONS_WRITE = "reactions:write"
FILES_READ = "files:read"
FILES_WRITE = "files:write"

# --- Stripe (restricted-API-key permissions modeled as OAuth scopes) ---
# Each Stripe resource exposes a none/read/write permission exactly like a
# restricted API key. ``stripe.<res>.write`` IMPLIES read for that resource;
# ``stripe.read_only`` satisfies any ``.read``; ``stripe.full`` satisfies
# everything. Those implications are enforced by the OR-logic scope lists in
# ``env_0_stripe/auth_scopes.py`` (e.g. a read route lists both ``.read`` and
# ``.write``), NOT by has_any_scope -- these constants are just the vocabulary.
STRIPE_CUSTOMERS_READ = "stripe.customers.read"
STRIPE_CUSTOMERS_WRITE = "stripe.customers.write"
STRIPE_PAYMENT_INTENTS_READ = "stripe.payment_intents.read"
STRIPE_PAYMENT_INTENTS_WRITE = "stripe.payment_intents.write"
STRIPE_CHARGES_READ = "stripe.charges.read"
STRIPE_CHARGES_WRITE = "stripe.charges.write"
STRIPE_REFUNDS_READ = "stripe.refunds.read"
STRIPE_REFUNDS_WRITE = "stripe.refunds.write"
STRIPE_PAYMENT_METHODS_READ = "stripe.payment_methods.read"
STRIPE_PAYMENT_METHODS_WRITE = "stripe.payment_methods.write"
STRIPE_PRODUCTS_READ = "stripe.products.read"
STRIPE_PRODUCTS_WRITE = "stripe.products.write"
STRIPE_PRICES_READ = "stripe.prices.read"
STRIPE_PRICES_WRITE = "stripe.prices.write"
STRIPE_WEBHOOK_ENDPOINTS_READ = "stripe.webhook_endpoints.read"
STRIPE_WEBHOOK_ENDPOINTS_WRITE = "stripe.webhook_endpoints.write"
# Read-only resources (Stripe exposes no write operations for these).
STRIPE_BALANCE_READ = "stripe.balance.read"
STRIPE_BALANCE_TRANSACTIONS_READ = "stripe.balance_transactions.read"
STRIPE_EVENTS_READ = "stripe.events.read"
# Convenience aggregate scopes.
STRIPE_READ_ONLY = "stripe.read_only"
STRIPE_FULL = "stripe.full"

# Human descriptions, straight from the spec's scope tables.
SCOPE_DESCRIPTIONS: dict[str, str] = {
    OPENID: "Authenticate and receive an ID token",
    EMAIL: "View your email address",
    PROFILE: "View your basic profile info",
    GMAIL_READONLY: "Read messages, threads, labels, history",
    GMAIL_SEND: "Send email",
    GMAIL_COMPOSE: "Create/update/delete drafts",
    GMAIL_MODIFY: "Modify labels, trash/untrash (not send)",
    GMAIL_LABELS: "CRUD on labels",
    GMAIL_SETTINGS_BASIC: "Read/update filters, forwarding",
    GMAIL_METADATA: "Read metadata only (headers, no body)",
    GMAIL_FULL: "All Gmail operations",
    CALENDAR_READONLY: "Read calendars, events, freebusy",
    CALENDAR_EVENTS: "CRUD on events",
    CALENDAR_EVENTS_READONLY: "Read events only",
    CALENDAR_FULL: "All Calendar operations",
    DRIVE_READONLY: "Read file metadata and content",
    DRIVE_FILE: "Per-file access (files created by app)",
    DRIVE_METADATA_READONLY: "Read metadata only",
    DRIVE_FULL: "All Drive operations",
    DOCS_READONLY: "Read documents",
    DOCS_FULL: "Read + write documents",
    CHANNELS_READ: "View channel info",
    CHANNELS_HISTORY: "Read message history",
    CHANNELS_WRITE: "Create/archive/rename channels",
    CHAT_WRITE: "Post messages",
    USERS_READ: "View user info",
    USERS_READ_EMAIL: "View user emails",
    REACTIONS_READ: "Read reactions",
    REACTIONS_WRITE: "Add/remove reactions",
    FILES_READ: "Read files",
    FILES_WRITE: "Upload/delete files",
    STRIPE_CUSTOMERS_READ: "Read customers",
    STRIPE_CUSTOMERS_WRITE: "Create, update, and delete customers",
    STRIPE_PAYMENT_INTENTS_READ: "Read payment intents",
    STRIPE_PAYMENT_INTENTS_WRITE: "Create, update, confirm, capture, and cancel payment intents",
    STRIPE_CHARGES_READ: "Read charges",
    STRIPE_CHARGES_WRITE: "Create and update charges",
    STRIPE_REFUNDS_READ: "Read refunds",
    STRIPE_REFUNDS_WRITE: "Create, update, and cancel refunds",
    STRIPE_PAYMENT_METHODS_READ: "Read payment methods",
    STRIPE_PAYMENT_METHODS_WRITE: "Create, update, attach, and detach payment methods",
    STRIPE_PRODUCTS_READ: "Read products",
    STRIPE_PRODUCTS_WRITE: "Create, update, and delete products",
    STRIPE_PRICES_READ: "Read prices",
    STRIPE_PRICES_WRITE: "Create and update prices",
    STRIPE_WEBHOOK_ENDPOINTS_READ: "Read webhook endpoints",
    STRIPE_WEBHOOK_ENDPOINTS_WRITE: "Create, update, and delete webhook endpoints",
    STRIPE_BALANCE_READ: "Read your account balance",
    STRIPE_BALANCE_TRANSACTIONS_READ: "Read balance transactions",
    STRIPE_EVENTS_READ: "Read events",
    STRIPE_READ_ONLY: "Read-only access to all Stripe resources",
    STRIPE_FULL: "Full access to all Stripe operations",
}


def has_any_scope(token_scopes: str | Iterable[str], required_scopes: Iterable[str]) -> bool:
    """OR-logic scope check: any one required scope present in the token grants access.

    ``token_scopes`` may be a space-separated string (the raw ``scope`` claim)
    or an iterable of scope names. An empty ``required_scopes`` means no scope
    requirement, i.e. access is granted (auth-only route).
    """
    required = [s for s in required_scopes if s]
    if not required:
        return True
    if isinstance(token_scopes, str):
        token_set = set(token_scopes.split())
    else:
        token_set = set(token_scopes)
    return any(scope in token_set for scope in required)
