# Mock Discord — API Notes

## Ground Truth

- **Official API reference**: https://discord.com/developers/docs/reference
- **REST resources**: https://docs.discord.com/developers/resources/channel
- **Opcodes & error codes**: https://discord.com/developers/docs/topics/opcodes-and-status-codes
- **Rate limits**: https://discord.com/developers/docs/topics/rate-limits
- **Permissions**: https://discord.com/developers/docs/topics/permissions
- **Snowflake IDs**: https://discord.com/developers/docs/reference#snowflakes
- **Fixture capture**: optional local-only capture against a throwaway Discord bot and guild
- **Fixture capture**: `scripts/capture_discord_fixtures.py` → `tests/fixtures/real_discord/`
- **Coverage map**: `tests/fixtures/mock_coverage_discord.json`

---

## Implemented Endpoints (82)

### Channels (3)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/channels/{channel_id}` | Get channel |
| PATCH | `/channels/{channel_id}` | Modify channel |
| DELETE | `/channels/{channel_id}` | Delete/close channel |

### Channel Permissions (2)

| Method | Path | Description |
|--------|------|-------------|
| PUT | `/channels/{channel_id}/permissions/{overwrite_id}` | Edit channel permission overwrite |
| DELETE | `/channels/{channel_id}/permissions/{overwrite_id}` | Delete channel permission overwrite |

### Channel Invites (2)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/channels/{channel_id}/invites` | List channel invites |
| POST | `/channels/{channel_id}/invites` | Create channel invite |

### Channel Misc (4)

| Method | Path | Description |
|--------|------|-------------|
| POST | `/channels/{channel_id}/followers` | Follow announcement channel |
| POST | `/channels/{channel_id}/typing` | Trigger typing indicator |
| PUT | `/channels/{channel_id}/recipients/{user_id}` | Add group DM recipient |
| DELETE | `/channels/{channel_id}/recipients/{user_id}` | Remove group DM recipient |

### Messages (7)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/channels/{channel_id}/messages` | List messages (cursor: `before`/`after`/`around`, max `limit`=100) |
| GET | `/channels/{channel_id}/messages/{message_id}` | Get message |
| POST | `/channels/{channel_id}/messages` | Create message |
| PATCH | `/channels/{channel_id}/messages/{message_id}` | Edit message |
| DELETE | `/channels/{channel_id}/messages/{message_id}` | Delete message |
| POST | `/channels/{channel_id}/messages/bulk-delete` | Bulk delete (2-100 messages) |
| POST | `/channels/{channel_id}/messages/{message_id}/crosspost` | Crosspost message to followers |

### Reactions (6)

| Method | Path | Description |
|--------|------|-------------|
| PUT | `/channels/{channel_id}/messages/{message_id}/reactions/{emoji}/@me` | Add own reaction |
| DELETE | `/channels/{channel_id}/messages/{message_id}/reactions/{emoji}/@me` | Remove own reaction |
| DELETE | `/channels/{channel_id}/messages/{message_id}/reactions/{emoji}/{user_id}` | Remove user's reaction |
| GET | `/channels/{channel_id}/messages/{message_id}/reactions/{emoji}` | Get users who reacted |
| DELETE | `/channels/{channel_id}/messages/{message_id}/reactions` | Delete all reactions |
| DELETE | `/channels/{channel_id}/messages/{message_id}/reactions/{emoji}` | Delete all of one emoji |

### Threads (11)

| Method | Path | Description |
|--------|------|-------------|
| POST | `/channels/{channel_id}/messages/{message_id}/threads` | Create thread from message |
| POST | `/channels/{channel_id}/threads` | Create thread without message |
| PUT | `/channels/{channel_id}/thread-members/@me` | Join thread |
| DELETE | `/channels/{channel_id}/thread-members/@me` | Leave thread |
| PUT | `/channels/{channel_id}/thread-members/{user_id}` | Add user to thread |
| DELETE | `/channels/{channel_id}/thread-members/{user_id}` | Remove user from thread |
| GET | `/channels/{channel_id}/thread-members/{user_id}` | Get thread member |
| GET | `/channels/{channel_id}/thread-members` | List thread members |
| GET | `/channels/{channel_id}/threads/archived/public` | List public archived threads |
| GET | `/channels/{channel_id}/threads/archived/private` | List private archived threads |
| GET | `/channels/{channel_id}/users/@me/threads/archived/private` | List joined private archived threads |

### Guilds (5)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/guilds/{guild_id}` | Get guild |
| PATCH | `/guilds/{guild_id}` | Modify guild |
| GET | `/guilds/{guild_id}/preview` | Get guild preview |
| GET | `/guilds/{guild_id}/channels` | List guild channels |
| POST | `/guilds/{guild_id}/channels` | Create guild channel |

### Guild Channel Positions (1)

| Method | Path | Description |
|--------|------|-------------|
| PATCH | `/guilds/{guild_id}/channels` | Modify channel positions |

### Guild Threads (1)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/guilds/{guild_id}/threads/active` | List active threads |

### Guild Members (8)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/guilds/{guild_id}/members` | List members (cursor: `after`, max `limit`=1000) |
| GET | `/guilds/{guild_id}/members/search` | Search members by username/nick |
| PATCH | `/guilds/{guild_id}/members/@me` | Modify current member (nick) |
| GET | `/guilds/{guild_id}/members/{user_id}` | Get member |
| PUT | `/guilds/{guild_id}/members/{user_id}` | Add member |
| PATCH | `/guilds/{guild_id}/members/{user_id}` | Modify member |
| DELETE | `/guilds/{guild_id}/members/{user_id}` | Kick member |
| PUT | `/guilds/{guild_id}/members/{user_id}/roles/{role_id}` | Add role to member |

### Guild Member Roles (1)

| Method | Path | Description |
|--------|------|-------------|
| DELETE | `/guilds/{guild_id}/members/{user_id}/roles/{role_id}` | Remove role from member |

### Guild Bans (4)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/guilds/{guild_id}/bans` | List bans |
| GET | `/guilds/{guild_id}/bans/{user_id}` | Get ban |
| PUT | `/guilds/{guild_id}/bans/{user_id}` | Create ban (also removes from members) |
| DELETE | `/guilds/{guild_id}/bans/{user_id}` | Remove ban |

### Guild Roles (5)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/guilds/{guild_id}/roles` | List roles |
| POST | `/guilds/{guild_id}/roles` | Create role |
| PATCH | `/guilds/{guild_id}/roles` | Modify role positions |
| PATCH | `/guilds/{guild_id}/roles/{role_id}` | Modify role |
| DELETE | `/guilds/{guild_id}/roles/{role_id}` | Delete role |

### Users (7)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/users/@me` | Get current user (includes `email`, `premium_type`) |
| GET | `/users/{user_id}` | Get user |
| PATCH | `/users/@me` | Modify current user |
| GET | `/users/@me/guilds` | List current user's guilds |
| GET | `/users/@me/guilds/{guild_id}/member` | Get current user's guild member |
| DELETE | `/users/@me/guilds/{guild_id}` | Leave guild |
| POST | `/users/@me/channels` | Create DM channel |

### Webhooks (15)

| Method | Path | Description |
|--------|------|-------------|
| POST | `/channels/{channel_id}/webhooks` | Create webhook |
| GET | `/channels/{channel_id}/webhooks` | List channel webhooks |
| GET | `/guilds/{guild_id}/webhooks` | List guild webhooks |
| GET | `/webhooks/{webhook_id}` | Get webhook (includes token) |
| PATCH | `/webhooks/{webhook_id}` | Modify webhook |
| DELETE | `/webhooks/{webhook_id}` | Delete webhook |
| GET | `/webhooks/{webhook_id}/{webhook_token}` | Get webhook via token (omits token in response) |
| PATCH | `/webhooks/{webhook_id}/{webhook_token}` | Modify webhook via token |
| DELETE | `/webhooks/{webhook_id}/{webhook_token}` | Delete webhook via token |
| POST | `/webhooks/{webhook_id}/{webhook_token}` | Execute webhook (`?wait=true` returns message) |
| POST | `/webhooks/{webhook_id}/{webhook_token}/slack` | Execute Slack-compatible webhook |
| POST | `/webhooks/{webhook_id}/{webhook_token}/github` | Execute GitHub-compatible webhook |
| GET | `/webhooks/{webhook_id}/{webhook_token}/messages/{message_id}` | Get webhook message |
| PATCH | `/webhooks/{webhook_id}/{webhook_token}/messages/{message_id}` | Edit webhook message |
| DELETE | `/webhooks/{webhook_id}/{webhook_token}/messages/{message_id}` | Delete webhook message |

### Guild Emoji (5)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/guilds/{guild_id}/emojis` | List guild emojis |
| GET | `/guilds/{guild_id}/emojis/{emoji_id}` | Get guild emoji |
| POST | `/guilds/{guild_id}/emojis` | Create guild emoji |
| PATCH | `/guilds/{guild_id}/emojis/{emoji_id}` | Modify guild emoji |
| DELETE | `/guilds/{guild_id}/emojis/{emoji_id}` | Delete guild emoji |

---

## API Quirks (append-only, dated)

Discovered during golden fixture analysis on 2026-03-15 and error code verification on 2026-03-26.

- **2026-03-15: Error responses are minimal.** Simple errors return only `{"code": <int>, "message": "<string>"}`. No `errors` key, no `status` field, no `domain`/`reason` nesting. See `error_unknown_channel.json`, `error_unknown_message.json`.

- **2026-03-15: Error codes are resource-specific.** Each resource type has its own error code for "not found": 10003 (channel), 10004 (guild), 10008 (message), 10011 (role), 10013 (user), 10014 (emoji), 10015 (webhook), 10026 (ban). See `error_codes_all.json`.

- **2026-03-26: "Unknown Member" returns code 10013 ("Unknown User").** Discord does not distinguish between "user not found" and "member not found" — both return code 10013 with message "Unknown User". Our mock returns code 10013 but keeps message "Unknown Member" for clarity. Verified against real API.

- **2026-03-15: Messages list returns a bare array.** `GET /channels/{id}/messages` returns `[{...}, {...}]` directly, not `{"messages": [...]}`. This differs from Gmail/GCal which use wrapper objects. See `messages_list.json`.

- **2026-03-15: Cursor-based pagination, not offset-based.** Messages use `before`/`after`/`around` snowflake ID params with `limit` (default 50, max 100). Members use `after` + `limit` (max 1000). No `pageToken` or `nextPageToken`.

- **2026-03-15: Snowflake IDs are large integers as strings.** All entity IDs (guilds, channels, messages, users, roles) are snowflake IDs — 64-bit integers encoding timestamp + worker + sequence. Returned as strings in JSON. See any fixture.

- **2026-03-15: Timestamps are ISO 8601 with timezone.** Format: `"2026-03-15T16:45:13.693000+00:00"`. Not epoch milliseconds (Gmail) or epoch seconds (Slack). See `message_get.json`.

- **2026-03-15: `@me` routes share path with `{user_id}` routes.** FastAPI route ordering matters — static paths (`@me`, `search`) must be registered before parameterized paths (`{user_id}`) to avoid `@me` being captured as a user ID.

- **2026-03-15: Reaction objects include burst fields.** Real reaction counts include `count_details` (burst vs normal), `burst_colors`, `me_burst`, `burst_me`, `burst_count`. These are Nitro "super reaction" features. Our mock omits them — agents don't need them. See `message_get_with_reactions.json`.

- **2026-03-15: User objects vary by context.** `GET /users/@me` returns extra fields (`email`, `mfa_enabled`, `verified`, `locale`, `bio`, `premium_type`) that are absent from user objects embedded in messages or members. See `user_get_me.json` vs `message_get.json` author field.

- **2026-03-15: Channel objects include cosmetic fields.** Real channels have `icon_emoji`, `theme_color`, `flags` that our mock omits. These are UI-only fields that don't affect agent behavior. See `channel_get.json`.

- **2026-03-15: Guild objects are massive.** Real guilds return 40+ fields including `region`, `afk_channel_id`, `verification_level`, `mfa_level`, `premium_tier`, etc. Our mock returns the core fields agents need: `id`, `name`, `icon`, `owner_id`, `features`, `roles`, `emojis`. See `guild_get.json`.

- **2026-03-15: Thread metadata is a nested object.** Thread channels include `thread_metadata: {"archived": bool, "auto_archive_duration": int, "locked": bool, "archive_timestamp": str, "create_timestamp": str}`. Our mock includes the first three; timestamps are omitted. See `thread_create_from_message.json`.

- **2026-03-15: Webhook token-based GET omits `token` from response.** `GET /webhooks/{id}/{token}` returns the webhook object but without the `token` field. Authenticated `GET /webhooks/{id}` includes `token`. See `webhook_get_with_token.json` vs `webhook_get.json`.

- **2026-03-15: Create operations return inconsistent status codes.** Channel create → 201, thread create → 201. But message create → 200, role create → 200, webhook create → 200, invite create → 200. Verified against real API.

- **2026-03-15: Role `colors` is a new nested object.** Real roles now include `colors: {"primary_color": int, "secondary_color": null, "tertiary_color": null}` in addition to the flat `color` field. Our mock uses only the flat `color` field. See `role_create_response.json`.

---

## Intentionally Skipped

| Feature | Reason |
|---------|--------|
| Application Commands (14 endpoints) | Bot registration, not runtime agent behavior |
| Interactions (8 endpoints) | Webhook-based, not REST |
| S/MIME Info, CSE (11 endpoints) | Enterprise encryption, not relevant for agents |
| Scheduled Events (6 endpoints) | Niche community feature |
| Stage Instances (4 endpoints) | Live audio events |
| Soundboard (7 endpoints) | Voice feature |
| SKUs/Entitlements/Subscriptions (8 endpoints) | Monetization |
| Auto Moderation (5 endpoints) | Admin setup, not agent runtime |
| Guild Templates (6 endpoints) | Rarely used |
| Voice state endpoints | Requires gateway connection |
| Audit Log | Read-only, captured as fixture only |
| `fields` query parameter | Partial response not relevant |
| Rate limiting enforcement | Headers present but no actual limiting |
| Gateway/WebSocket | Only REST API is mocked |

---

## Key Design Choices

- **Stateful mock, not replay**: Full CRUD with persistent SQLite, enabling multi-step agent workflows
- **Snowflake IDs**: Generated deterministically from a seed counter for reproducible seeding, but time-based for runtime operations
- **Bot-centric**: Auth accepts any `Authorization: Bot <token>` header (or none). Resolves to first bot user in DB.
- **Permission-accepting, not enforcing**: Permission bitfields are stored but never checked. Agents can perform any operation regardless of roles.
- **JSON columns for complex fields**: Embeds, attachments, mentions, member roles stored as JSON text columns — deserialized in the Pydantic response layer
- **Thread as Channel**: Threads are implemented as Channel rows with `type` in (10, 11, 12) and thread-specific fields (archived, locked, owner_id, message_count)
- **Webhook users**: When a webhook executes, a synthetic user (`webhook-{id}`) is created as the message author
