# Mock Discord — Web UI

Discord-themed web interface for browsing and interacting with the mock Discord API.

## UI Routes

| Route | API Endpoints Used | Description |
|-------|-------------------|-------------|
| `GET /` | Guilds, Members, Roles, Channels | Server overview dashboard |
| `GET /channel/{id}` | Messages, Reactions, Users | Channel message view with reactions |
| `POST /channel/{id}/send` | Messages.create | Send a message via form |
| `POST /channel/{id}/message/{id}/react` | Reactions.add/remove | Toggle emoji reaction on a message |
| `POST /channel/{id}/message/{id}/delete` | Messages.delete | Delete a message |
| `GET /user/{id}` | Users.get, Members.get | User profile with roles, join date, nickname |
| `GET /members` | Members.list, Roles.list | All members grouped by highest role |
| `GET /roles` | Roles.list, Members.list | All roles with member counts |
| `GET /dev/dashboard` | (internal) | Stats cards, test runner, endpoint summary |
| `GET /dev/api-explorer` | (reads mock_coverage_discord.json) | Browseable endpoint list |
| `GET /dev/db-viewer` | (reads SQLite directly) | Paginated database table browser |

## API Coverage in UI

### Reflected in UI (interactive)

| API Resource | What the UI shows |
|---|---|
| **Messages** | View, send, delete messages in channel view |
| **Reactions** | Click to toggle reactions (thumbsup, heart, laugh, eyes); click existing reactions to toggle |
| **Channels** | Browse all channels in sidebar grouped by category |
| **Guilds** | Server name, description, feature flags, stats on dashboard |
| **Members** | Member list grouped by role, click to view profile |
| **Roles** | Role list with colors, position, member counts, hoisted/managed badges |
| **Users** | Profile page with avatar, username, ID, email, join date, nickname, roles |

### NOT reflected in UI (API-only)

These endpoints work via the REST API (`/api/v10/...`) and Swagger UI (`/docs`) but have no dedicated web UI page:

| API Resource | Why not in UI |
|---|---|
| **Webhooks** (15 endpoints) | Webhooks are programmatic; no natural UI representation in Discord's web client either |
| **Emoji** (5 endpoints) | Custom emoji CRUD is a server settings operation; visible as reaction options but no management UI |
| **Threads** (11 endpoints) | Thread creation/management is an advanced feature; threads display as channels in sidebar when created |
| **Invites** (2 endpoints) | Invite creation/listing is a modal in real Discord; low priority for mock UI |
| **Bans** (4 endpoints) | Ban management is a server settings operation |
| **Permission Overwrites** (2 endpoints) | Channel permission editing is deeply nested in real Discord |
| **Channel CRUD** (create/modify/delete) | Channel management is a server settings operation |
| **Role CRUD** (create/modify/delete) | Role management shown read-only; mutation via API |
| **Member modification** (kick, modify, role assign) | Member management via API only |
| **Guild modification** | Server settings modification via API only |

### Dev Tools

All 82 API endpoints are browseable in `/dev/api-explorer` with method, path, fixture status, and test count. The `/dev/db-viewer` lets you inspect any of the 14 database tables directly.
