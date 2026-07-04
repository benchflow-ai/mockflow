"""Per-route OAuth scope requirements for auth (used when AUTH_ENABLED=1).

``SCOPE_MAP`` keys are ``(HTTP_METHOD, route_path_template)`` tuples EXACTLY as
the routes are registered on the FastAPI app (see ``mock_slack/api/app.py``;
all Slack RPC methods live under the ``/api`` prefix). Values are OR-logic
scope lists: ANY one listed scope grants access. An EMPTY list means the route
requires a valid token but no particular scope (contract: "missing route key
=> only auth required" -- we keep the key present so the coverage test proves
every route was considered).

Scope names are Slack-style colon names per the auth contract
(``chat:write``, ``channels:read``, ...); semantics mirror real Slack scopes:

- conversations/channel info reads     -> channels:read
- history (history / replies)          -> channels:history
- channel mutations (create / archive
  / rename / invite / kick / join /
  leave / setTopic / setPurpose)       -> channels:write
- opening DMs (conversations.open)     -> im:write (real Slack im:write/mpim:write)
- chat.* message writes + scheduled
  message management                   -> chat:write
- users reads                          -> users:read (presence only) /
  users:read.email (any endpoint whose response contains profile.email --
  this mock cannot redact fields per-scope and the contract scope lists are
  OR-logic, so the email-bearing endpoints list users:read.email as the SOLE
  sufficient scope; in real Slack a client holding users:read.email always
  also holds users:read)
- users.profile.set                    -> users.profile:write (real Slack name)
- users.setPresence                    -> users:write (real Slack name)
- reactions read / write               -> reactions:read / reactions:write
- files read / write                   -> files:read / files:write
- pins read / write                    -> pins:read / pins:write
- search.messages                      -> search:read (user-token method)
- team.info                            -> team:read
- reminders.list                       -> reminders:read
- auth.test                            -> no scope (real Slack: auth.test has
  no required scopes; any valid token may introspect itself)

This module deliberately has NO env_0_auth_client import so that slack
works unchanged when auth-client is not installed.

Coverage of every registered /api route is enforced by
``tests/test_auth_integration.py::TestScopeMapCoverage``.
"""

from __future__ import annotations

# Mirrors env_0_auth_client.ScopeMap (kept local: auth-client is optional).
ScopeMap = dict[tuple[str, str], list[str]]

SLACK_PREFIX = "/api"

CHANNELS_READ = ["channels:read"]
CHANNELS_HISTORY = ["channels:history"]
CHANNELS_WRITE = ["channels:write"]
IM_WRITE = ["im:write"]
CHAT_WRITE = ["chat:write"]
USERS_READ = ["users:read"]
USERS_READ_EMAIL = ["users:read.email"]
USERS_WRITE = ["users:write"]
USERS_PROFILE_WRITE = ["users.profile:write"]
REACTIONS_READ = ["reactions:read"]
REACTIONS_WRITE = ["reactions:write"]
FILES_READ = ["files:read"]
FILES_WRITE = ["files:write"]
PINS_READ = ["pins:read"]
PINS_WRITE = ["pins:write"]
SEARCH_READ = ["search:read"]
TEAM_READ = ["team:read"]
REMINDERS_READ = ["reminders:read"]
#: Valid token required, but no particular scope (real Slack: auth.test).
NO_SCOPE: list[str] = []

SCOPE_MAP: ScopeMap = {
    # --- auth ---
    ("POST", f"{SLACK_PREFIX}/auth.test"): NO_SCOPE,
    # --- conversations: reads ---
    ("GET", f"{SLACK_PREFIX}/conversations.list"): CHANNELS_READ,
    ("GET", f"{SLACK_PREFIX}/conversations.info"): CHANNELS_READ,
    ("GET", f"{SLACK_PREFIX}/conversations.members"): CHANNELS_READ,
    # --- conversations: history ---
    ("GET", f"{SLACK_PREFIX}/conversations.history"): CHANNELS_HISTORY,
    ("GET", f"{SLACK_PREFIX}/conversations.replies"): CHANNELS_HISTORY,
    # --- conversations: mutations ---
    ("POST", f"{SLACK_PREFIX}/conversations.create"): CHANNELS_WRITE,
    ("POST", f"{SLACK_PREFIX}/conversations.archive"): CHANNELS_WRITE,
    ("POST", f"{SLACK_PREFIX}/conversations.unarchive"): CHANNELS_WRITE,
    ("POST", f"{SLACK_PREFIX}/conversations.rename"): CHANNELS_WRITE,
    ("POST", f"{SLACK_PREFIX}/conversations.invite"): CHANNELS_WRITE,
    ("POST", f"{SLACK_PREFIX}/conversations.kick"): CHANNELS_WRITE,
    ("POST", f"{SLACK_PREFIX}/conversations.join"): CHANNELS_WRITE,
    ("POST", f"{SLACK_PREFIX}/conversations.leave"): CHANNELS_WRITE,
    ("POST", f"{SLACK_PREFIX}/conversations.setPurpose"): CHANNELS_WRITE,
    ("POST", f"{SLACK_PREFIX}/conversations.setTopic"): CHANNELS_WRITE,
    ("POST", f"{SLACK_PREFIX}/conversations.open"): IM_WRITE,
    # --- chat ---
    ("POST", f"{SLACK_PREFIX}/chat.postMessage"): CHAT_WRITE,
    ("POST", f"{SLACK_PREFIX}/chat.postEphemeral"): CHAT_WRITE,
    ("POST", f"{SLACK_PREFIX}/chat.update"): CHAT_WRITE,
    ("POST", f"{SLACK_PREFIX}/chat.delete"): CHAT_WRITE,
    # Permalink lookup exposes only channel/message location -> a read scope.
    ("GET", f"{SLACK_PREFIX}/chat.getPermalink"): CHANNELS_READ,
    ("POST", f"{SLACK_PREFIX}/chat.scheduleMessage"): CHAT_WRITE,
    ("POST", f"{SLACK_PREFIX}/chat.deleteScheduledMessage"): CHAT_WRITE,
    # Lists only the caller's own pending sends, created via chat:write.
    ("GET", f"{SLACK_PREFIX}/chat.scheduledMessages.list"): CHAT_WRITE,
    # --- reactions ---
    ("POST", f"{SLACK_PREFIX}/reactions.add"): REACTIONS_WRITE,
    ("POST", f"{SLACK_PREFIX}/reactions.remove"): REACTIONS_WRITE,
    ("GET", f"{SLACK_PREFIX}/reactions.get"): REACTIONS_READ,
    # --- users (responses including profile.email require users:read.email) ---
    ("GET", f"{SLACK_PREFIX}/users.list"): USERS_READ_EMAIL,
    ("GET", f"{SLACK_PREFIX}/users.info"): USERS_READ_EMAIL,
    ("GET", f"{SLACK_PREFIX}/users.lookupByEmail"): USERS_READ_EMAIL,
    ("GET", f"{SLACK_PREFIX}/users.profile.get"): USERS_READ_EMAIL,
    ("POST", f"{SLACK_PREFIX}/users.profile.set"): USERS_PROFILE_WRITE,
    ("POST", f"{SLACK_PREFIX}/users.setPresence"): USERS_WRITE,
    ("GET", f"{SLACK_PREFIX}/users.getPresence"): USERS_READ,
    # --- search ---
    ("GET", f"{SLACK_PREFIX}/search.messages"): SEARCH_READ,
    # --- files ---
    ("GET", f"{SLACK_PREFIX}/files.list"): FILES_READ,
    ("GET", f"{SLACK_PREFIX}/files.info"): FILES_READ,
    ("POST", f"{SLACK_PREFIX}/files.upload"): FILES_WRITE,
    ("POST", f"{SLACK_PREFIX}/files.delete"): FILES_WRITE,
    # --- pins ---
    ("POST", f"{SLACK_PREFIX}/pins.add"): PINS_WRITE,
    ("POST", f"{SLACK_PREFIX}/pins.remove"): PINS_WRITE,
    ("GET", f"{SLACK_PREFIX}/pins.list"): PINS_READ,
    # --- team ---
    ("GET", f"{SLACK_PREFIX}/team.info"): TEAM_READ,
    # --- reminders ---
    ("GET", f"{SLACK_PREFIX}/reminders.list"): REMINDERS_READ,
}
