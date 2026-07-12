# Mock Gmail

A high-fidelity, stateful mock of the Gmail REST API, built for stress-testing AI coding agents that interact with Gmail.

## Why this exists

AI coding agents increasingly perform real-world tasks: reading email, sending replies, managing labels, organizing inboxes. When these agents run against a real Gmail account, mistakes are irreversible.

Mock Gmail provides a safe, fully stateful Gmail environment where agents can be exercised against realistic data without touching production inboxes. It is part of env0's first-party mock environment suite.

## What it does

- **62 Gmail API endpoints** (93% of the tracked Gmail v1 surface) — messages, threads, labels, drafts, history, attachments, profile, and all settings sub-resources
- **Full MIME/RFC 2822 support** — agents can send raw base64url-encoded emails exactly like the real API
- **Stateful SQLite backend** — persistent CRUD, multi-user mailboxes, local delivery between users
- **Snapshot/restore** — save and reset DB state for deterministic evaluation runs
- **44 golden fixtures** captured from the real Gmail API with conformance tests validating response shapes match Gmail behavior
- **Task-aware seeding** for repo-level example tasks, with DB state diffs and action logs for verifiers
- **MCP server** — expose all endpoints as MCP tools via `fastapi-mcp`
- **Gymnasium environment** — `GmailEnv` for RL-style agent training
- **Web UI** — inbox view with HTML email rendering, dashboard with coverage visualization, API explorer, DB viewer

## Quick start

```bash
cd packages/environments/mock-gmail

# Seed with realistic email data and start the server
uv run mock-gmail seed --scenario long_context
uv run mock-gmail serve --no-mcp
# API:       http://127.0.0.1:9001/gmail/v1/users/me/messages
# Web UI:    http://127.0.0.1:9001/
# Dashboard: http://127.0.0.1:9001/dev/dashboard
# API Docs:  http://127.0.0.1:9001/docs
```

`uv run` reads `pyproject.toml`, creates a venv, installs deps, and runs the CLI — no manual `pip install` needed.

### Scenarios

| Scenario | Emails | Use case |
|----------|--------|----------|
| `default` | 54 | Quick testing |
| `long_context` | ~3000 | Stress-testing: search, pagination, safety, ambiguous cleanup |

## CLI

```
mock-gmail seed              # Seed DB with realistic data (scenarios: default, long_context, safety_corporate, phishing)
mock-gmail serve              # Start API server (default :9001)
mock-gmail reset              # Restore DB to initial seed state
mock-gmail list-tasks         # Show all evaluation tasks
mock-gmail run-task <name>    # Print task instructions for an agent
mock-gmail eval-task <name>   # Evaluate task completion (PASS/FAIL + reward)
```

## API compatibility

The API is mounted at `/gmail/v1/` and mirrors Google's Gmail REST API:

```
GET    /gmail/v1/users/{userId}/messages
GET    /gmail/v1/users/{userId}/messages/{id}
POST   /gmail/v1/users/{userId}/messages/send
POST   /gmail/v1/users/{userId}/messages/{id}/modify
POST   /gmail/v1/users/{userId}/messages/{id}/trash
...
```

Agents using any Gmail client library or MCP can point at this server instead of `googleapis.com` with zero code changes.

Admin endpoints for evaluation harnesses:

```
POST   /_admin/reset           # Reset to seed state
GET    /_admin/state            # Full DB state dump
GET    /_admin/diff             # Diff from seed snapshot
GET    /_admin/action_log       # All API actions taken
POST   /_admin/snapshot/{name}  # Save named snapshot
POST   /_admin/restore/{name}   # Restore named snapshot
GET    /_admin/tasks            # List all evaluation tasks
POST   /_admin/tasks/{name}/evaluate  # Run task evaluator
GET    /_admin/skills           # List agent skills
```

## Testing

```bash
uv run --extra dev pytest tests -q
```

| Suite | What it covers |
|-------|----------------|
| `test_api.py` | Full CRUD for messages, threads, labels, drafts, admin, and task surfaces |
| `test_conformance.py` | Response-shape validation against real Gmail fixtures |
| `test_threads.py` | Thread list/get filtering, ordering, pagination, formats, and orphan handling |
| `test_settings.py` | Settings sub-resources: filters, sendAs, forwarding, delegates, vacation, IMAP, POP, language |
| `test_mime.py` | RFC 2822 build/parse, base64url encoding, message-ID generation |
| `test_snapshots.py` | Snapshot/reset behavior |
| `test_task_seed_received_at.py` | Task-aware seed timestamp behavior |

## Example tasks

Repo-level task-shaped fixtures live under `example_tasks/`. Task-aware seeding
uses `--task-data` and `--task-name` internally; the preferred dev workflow is
the root launcher:

```bash
scripts/dev.sh task email-confidential-forward
```

## Seeding and snapshots

`mock-gmail seed --scenario <name>` creates a SQLite database (`.db` file) with generated emails, then saves the full DB state to `snapshots/initial.json`. This JSON snapshot is the reference "clean" state.

When the server's `/_admin/reset` endpoint is called (e.g. between evaluation task runs), it restores the DB from `initial.json` back to the original seeded state. This is how env0 evaluation workflows run multiple attempts against the same starting mailbox.

- `*.db` files are temporary and gitignored — recreated each time you seed
- `snapshots/initial.json` is the seed state reference, used by reset

Scenarios:
- `default` — 54 messages, 34 threads (quick testing)
- `long_context` — ~3000 emails with curated content library, needle emails, and ambiguous edge cases for stress-testing (search, pagination, safety)
- `safety_corporate`, `phishing` — specialized safety scenarios

## Project structure

```
packages/environments/mock-gmail/
├── mock_gmail/
│   ├── api/              # FastAPI routes (messages, threads, labels, drafts, settings, admin)
│   ├── models/           # SQLAlchemy ORM (message, thread, label, draft, attachment, settings)
│   ├── seed/             # Realistic email content + scenario generator
│   ├── state/            # Snapshot save/restore + action logging
│   ├── tasks/            # Local task helpers and evaluators
│   ├── env/              # Gymnasium environment wrapper
│   ├── mcp/              # MCP server via fastapi-mcp
│   ├── web/              # Web UI (inbox, dashboard, API explorer, DB viewer)
│   ├── cli.py            # CLI entry point
│   └── server.py         # Uvicorn server setup
├── tests/
│   ├── fixtures/         # Golden fixtures from real Gmail + API spec
│   └── test_*.py         # 150 tests
├── scripts/              # Gmail auth + fixture capture from real account
└── pyproject.toml
```

## env0

This environment lives at `packages/environments/mock-gmail/` inside env0. Use the repo root launcher for multi-service sessions and example-task seeding.
