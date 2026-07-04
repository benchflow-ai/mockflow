"""Scope catalog — bare names (NOT full Google URLs), per the pinned contract."""

from __future__ import annotations

# scope -> human-readable description (shown on the consent screen)
SCOPE_DESCRIPTIONS: dict[str, str] = {
    # OIDC
    "openid": "Associate you with your personal info",
    "email": "See your primary email address",
    "profile": "See your personal info (name, picture)",
    # Gmail
    "gmail.readonly": "Read your email messages and settings",
    "gmail.send": "Send email on your behalf",
    "gmail.compose": "Create, update, and delete drafts",
    "gmail.modify": "Modify labels and move messages (not send)",
    "gmail.labels": "Manage your email labels",
    "gmail.settings.basic": "Manage basic mail settings (filters, forwarding)",
    "gmail.metadata": "View email message metadata (headers only)",
    "gmail.full": "Read, compose, send, and permanently delete all your email",
    # Calendar
    "calendar.readonly": "See all your calendars and events",
    "calendar.events": "View and edit events on all your calendars",
    "calendar.events.readonly": "View events on all your calendars",
    "calendar.full": "See, edit, share, and permanently delete all your calendars",
    # Drive
    "drive.readonly": "See and download all your files",
    "drive.file": "See and manage files created with this app",
    "drive.metadata.readonly": "View metadata for files",
    "drive.full": "See, edit, create, and delete all your files",
    # Docs
    "docs.readonly": "View your documents",
    "docs.full": "View and manage your documents",
    # Slack-style
    "channels:read": "View basic channel information",
    "channels:history": "View messages in channels",
    "channels:write": "Manage channels (create, archive, rename)",
    "chat:write": "Post messages on your behalf",
    "users:read": "View people in the workspace",
    "users:read.email": "View email addresses of people in the workspace",
    "reactions:read": "View emoji reactions",
    "reactions:write": "Add and remove emoji reactions",
    "files:read": "View files",
    "files:write": "Upload and delete files",
    # Stripe (restricted-API-key permissions modeled as scopes; write implies
    # read for a resource, read_only satisfies any .read, full satisfies all).
    "stripe.customers.read": "Read your customers",
    "stripe.customers.write": "Create, update, and delete customers",
    "stripe.payment_intents.read": "Read your payment intents",
    "stripe.payment_intents.write": "Create, confirm, capture, and cancel payment intents",
    "stripe.charges.read": "Read your charges",
    "stripe.charges.write": "Create and update charges",
    "stripe.refunds.read": "Read your refunds",
    "stripe.refunds.write": "Issue and manage refunds",
    "stripe.payment_methods.read": "Read your payment methods",
    "stripe.payment_methods.write": "Create, attach, and detach payment methods",
    "stripe.products.read": "Read your products",
    "stripe.products.write": "Create, update, and delete products",
    "stripe.prices.read": "Read your prices",
    "stripe.prices.write": "Create and update prices",
    "stripe.webhook_endpoints.read": "Read your webhook endpoints",
    "stripe.webhook_endpoints.write": "Create, update, and delete webhook endpoints",
    "stripe.balance.read": "Read your account balance",
    "stripe.balance_transactions.read": "Read your balance transactions",
    "stripe.events.read": "Read your account events",
    "stripe.read_only": "Read-only access to all Stripe resources",
    "stripe.full": "Full access to all Stripe operations",
}

SCOPES_SUPPORTED: list[str] = list(SCOPE_DESCRIPTIONS.keys())


def parse_scope(scope: str | None) -> list[str]:
    """Split a space-separated scope string into a list (order-preserving, deduped)."""
    if not scope:
        return []
    seen: list[str] = []
    for s in scope.split():
        if s and s not in seen:
            seen.append(s)
    return seen


def describe(scope_name: str) -> str:
    return SCOPE_DESCRIPTIONS.get(scope_name, scope_name)
