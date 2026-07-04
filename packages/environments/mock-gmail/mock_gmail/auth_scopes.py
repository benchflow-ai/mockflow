"""Per-route OAuth scope requirements for auth (used when AUTH_ENABLED=1).

``SCOPE_MAP`` keys are ``(HTTP_METHOD, route_path_template)`` tuples EXACTLY as
the routes are registered on the FastAPI app (see ``mock_gmail/api/app.py``).
Values are OR-logic scope lists: ANY one listed scope grants access. Routes
absent from the map (and exempt prefixes like /_admin, /health, /dev, /web)
require a valid token but no particular scope.

Scope names are the bare auth names (``gmail.readonly``, not full Google
URLs); semantics mirror the real Gmail API scopes:

- reads                  -> gmail.readonly | gmail.modify | gmail.full
  (+ gmail.metadata for routes that never expose message bodies)
- send                   -> gmail.send | gmail.full
- drafts                 -> gmail.compose | gmail.full (reads also accept
  gmail.readonly / gmail.modify, like real Gmail)
- label mutations        -> gmail.labels | gmail.modify | gmail.full
- settings / filters     -> gmail.settings.basic | gmail.full (reads also
  accept gmail.readonly / gmail.modify, like real Gmail)
- trash/untrash/modify   -> gmail.modify | gmail.full
- permanent delete       -> gmail.full only (real Gmail requires
  https://mail.google.com/ for messages.delete / threads.delete / batchDelete)

This module deliberately has NO env_0_auth_client import so that gmail
works unchanged when the optional ``auth`` extra is not installed.

Coverage of every registered /gmail/v1 route is enforced by
``tests/test_auth_integration.py::TestScopeMapCoverage``.
"""

from __future__ import annotations

# Mirrors env_0_auth_client.ScopeMap (kept local: auth-client is optional).
ScopeMap = dict[tuple[str, str], list[str]]

GMAIL_PREFIX = "/gmail/v1"
_U = f"{GMAIL_PREFIX}/users/{{userId}}"

FULL = "gmail.full"  # equivalent of https://mail.google.com/
READONLY = "gmail.readonly"
MODIFY = "gmail.modify"
METADATA = "gmail.metadata"
SEND = "gmail.send"
COMPOSE = "gmail.compose"
LABELS = "gmail.labels"
SETTINGS_BASIC = "gmail.settings.basic"

# Reads that can expose full message bodies (messages.get, threads.get,
# attachments) -- gmail.metadata is NOT sufficient.
READ = [READONLY, MODIFY, FULL]
# Metadata-safe reads (lists, history, profile, labels): real Gmail also
# accepts gmail.metadata here because no message body is returned.
METADATA_READ = [METADATA, READONLY, MODIFY, FULL]
# Real Gmail additionally allows gmail.compose on users.getProfile.
PROFILE_READ = [METADATA, READONLY, MODIFY, COMPOSE, FULL]
WRITE = [MODIFY, FULL]
SEND_SCOPES = [SEND, FULL]
DRAFT_READ = [COMPOSE, READONLY, MODIFY, FULL]
DRAFT_WRITE = [COMPOSE, FULL]
LABEL_READ = [LABELS, METADATA, READONLY, MODIFY, FULL]
LABEL_WRITE = [LABELS, MODIFY, FULL]
SETTINGS_READ = [SETTINGS_BASIC, READONLY, MODIFY, FULL]
SETTINGS_WRITE = [SETTINGS_BASIC, FULL]
PERMANENT_DELETE = [FULL]
# users.watch / users.stop (push notification config): metadata is enough.
WATCH = [METADATA, READONLY, MODIFY, FULL]

SCOPE_MAP: ScopeMap = {
    # --- messages ---
    ("GET", f"{_U}/messages"): METADATA_READ,
    ("GET", f"{_U}/messages/{{messageId}}"): READ,
    ("GET", f"{_U}/messages/{{messageId}}/attachments/{{attachmentId}}"): READ,
    ("POST", f"{_U}/messages/send"): SEND_SCOPES,
    ("POST", f"{_U}/messages"): WRITE,  # messages.insert
    ("POST", f"{_U}/messages/import"): WRITE,
    ("POST", f"{_U}/messages/batchModify"): WRITE,
    ("POST", f"{_U}/messages/batchDelete"): PERMANENT_DELETE,
    ("POST", f"{_U}/messages/{{messageId}}/modify"): WRITE,
    ("POST", f"{_U}/messages/{{messageId}}/trash"): WRITE,
    ("POST", f"{_U}/messages/{{messageId}}/untrash"): WRITE,
    ("DELETE", f"{_U}/messages/{{messageId}}"): PERMANENT_DELETE,
    # --- threads ---
    ("GET", f"{_U}/threads"): METADATA_READ,
    ("GET", f"{_U}/threads/{{threadId}}"): READ,
    ("POST", f"{_U}/threads/{{threadId}}/modify"): WRITE,
    ("POST", f"{_U}/threads/{{threadId}}/trash"): WRITE,
    ("POST", f"{_U}/threads/{{threadId}}/untrash"): WRITE,
    ("DELETE", f"{_U}/threads/{{threadId}}"): PERMANENT_DELETE,
    # --- labels ---
    ("GET", f"{_U}/labels"): LABEL_READ,
    ("GET", f"{_U}/labels/{{labelId}}"): LABEL_READ,
    ("POST", f"{_U}/labels"): LABEL_WRITE,
    ("PUT", f"{_U}/labels/{{labelId}}"): LABEL_WRITE,
    ("PATCH", f"{_U}/labels/{{labelId}}"): LABEL_WRITE,
    ("DELETE", f"{_U}/labels/{{labelId}}"): LABEL_WRITE,
    # --- drafts ---
    ("GET", f"{_U}/drafts"): DRAFT_READ,
    ("GET", f"{_U}/drafts/{{draftId}}"): DRAFT_READ,
    ("POST", f"{_U}/drafts"): DRAFT_WRITE,
    ("POST", f"{_U}/drafts/send"): DRAFT_WRITE,  # gmail.send does NOT cover drafts.send
    ("PUT", f"{_U}/drafts/{{draftId}}"): DRAFT_WRITE,
    ("DELETE", f"{_U}/drafts/{{draftId}}"): DRAFT_WRITE,
    # --- history / profile / push ---
    ("GET", f"{_U}/history"): METADATA_READ,
    ("GET", f"{_U}/profile"): PROFILE_READ,
    ("POST", f"{_U}/watch"): WATCH,
    ("POST", f"{_U}/stop"): WATCH,
    # --- settings: imap / pop / vacation / language / autoForwarding ---
    ("GET", f"{_U}/settings/imap"): SETTINGS_READ,
    ("PUT", f"{_U}/settings/imap"): SETTINGS_WRITE,
    ("GET", f"{_U}/settings/pop"): SETTINGS_READ,
    ("PUT", f"{_U}/settings/pop"): SETTINGS_WRITE,
    ("GET", f"{_U}/settings/vacation"): SETTINGS_READ,
    ("PUT", f"{_U}/settings/vacation"): SETTINGS_WRITE,
    ("GET", f"{_U}/settings/language"): SETTINGS_READ,
    ("PUT", f"{_U}/settings/language"): SETTINGS_WRITE,
    ("GET", f"{_U}/settings/autoForwarding"): SETTINGS_READ,
    ("PUT", f"{_U}/settings/autoForwarding"): SETTINGS_WRITE,
    # --- settings: filters ---
    ("GET", f"{_U}/settings/filters"): SETTINGS_READ,
    ("GET", f"{_U}/settings/filters/{{filterId}}"): SETTINGS_READ,
    ("POST", f"{_U}/settings/filters"): SETTINGS_WRITE,
    ("DELETE", f"{_U}/settings/filters/{{filterId}}"): SETTINGS_WRITE,
    # --- settings: sendAs ---
    ("GET", f"{_U}/settings/sendAs"): SETTINGS_READ,
    ("GET", f"{_U}/settings/sendAs/{{sendAsEmail}}"): SETTINGS_READ,
    ("POST", f"{_U}/settings/sendAs"): SETTINGS_WRITE,
    ("PUT", f"{_U}/settings/sendAs/{{sendAsEmail}}"): SETTINGS_WRITE,
    ("DELETE", f"{_U}/settings/sendAs/{{sendAsEmail}}"): SETTINGS_WRITE,
    ("POST", f"{_U}/settings/sendAs/{{sendAsEmail}}/verify"): SETTINGS_WRITE,
    # --- settings: forwardingAddresses ---
    ("GET", f"{_U}/settings/forwardingAddresses"): SETTINGS_READ,
    ("GET", f"{_U}/settings/forwardingAddresses/{{forwardingEmail}}"): SETTINGS_READ,
    ("POST", f"{_U}/settings/forwardingAddresses"): SETTINGS_WRITE,
    ("DELETE", f"{_U}/settings/forwardingAddresses/{{forwardingEmail}}"): SETTINGS_WRITE,
    # --- settings: delegates ---
    ("GET", f"{_U}/settings/delegates"): SETTINGS_READ,
    ("GET", f"{_U}/settings/delegates/{{delegateEmail}}"): SETTINGS_READ,
    ("POST", f"{_U}/settings/delegates"): SETTINGS_WRITE,
    ("DELETE", f"{_U}/settings/delegates/{{delegateEmail}}"): SETTINGS_WRITE,
}
