# mock-gdoc

Mock Google Docs environment for AI agent evaluation. Provides a Google Docs API v1-compatible REST API backed by SQLite.

## Quick Start

```bash
uv run mock-gdoc seed --scenario default
uv run mock-gdoc serve --port 9004 --no-mcp
```

`uv run` reads `pyproject.toml`, creates/syncs the package environment, and
runs the CLI. No manual virtualenv or editable install is needed for normal
repo workflows.

Default endpoints:

- API: `http://127.0.0.1:9004/v1/documents`
- Docs: `http://127.0.0.1:9004/docs`
- Web UI: `http://127.0.0.1:9004/`

## CLI Reference

```
mock-gdoc [--db PATH] <command>

Commands:
  seed        Seed the database (--scenario default|long_context|task:*)
  serve       Start API server (--host, --port, --no-mcp)
  reset       Restore database to initial seed state
  run-task    Show a task's instructions
  eval-task   Evaluate task completion
  list-tasks  List all available tasks
```

## Seed Scenarios

| Scenario | Description |
|----------|-------------|
| `default` | 16 hand-written documents (5 meeting notes, 3 specs, 3 personal, 3 shared, 2 templates) with comments and permissions |
| `long_context` | 3000 documents (the 16 hand-written docs + generated filler) for search/pagination stress testing |
| `task:<name>` | Task-specific needle documents + filler |

## API Endpoints

### Documents (`/v1/documents`)

| Method | Path | Description |
|--------|------|-------------|
| POST | `/v1/documents` | Create new document |
| GET | `/v1/documents/{documentId}` | Get document |
| POST | `/v1/documents/{documentId}:batchUpdate` | Batch update (insertText, deleteContentRange, replaceAllText) |

### Comments (`/v1/documents/{documentId}/comments`)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/v1/documents/{documentId}/comments` | List comments on document |
| POST | `/v1/documents/{documentId}/comments` | Create comment |
| GET | `/v1/documents/{documentId}/comments/{commentId}` | Get comment |
| PATCH | `/v1/documents/{documentId}/comments/{commentId}` | Update comment (author only) |
| DELETE | `/v1/documents/{documentId}/comments/{commentId}` | Delete comment (author or owner) |
| POST | `/v1/documents/{documentId}/comments/{commentId}/resolve` | Resolve comment |
| POST | `/v1/documents/{documentId}/comments/{commentId}/reopen` | Reopen resolved comment |
| POST | `/v1/documents/{documentId}/comments/{commentId}/replies` | Create reply |
| DELETE | `/v1/documents/{documentId}/comments/{commentId}/replies/{replyId}` | Delete reply |

### Permissions (`/v1/documents/{documentId}/permissions`)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/v1/documents/{documentId}/permissions` | List permissions |
| POST | `/v1/documents/{documentId}/permissions` | Share document (add collaborator) |
| PATCH | `/v1/documents/{documentId}/permissions/{permissionId}` | Update permission role |
| DELETE | `/v1/documents/{documentId}/permissions/{permissionId}` | Remove permission |

### Admin Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Health check |
| POST | `/_admin/reset` | Restore to initial snapshot |
| POST | `/_admin/seed` | Re-seed with scenario |
| GET | `/_admin/state` | Full state dump |
| GET | `/_admin/diff` | Diff vs initial state |
| GET | `/_admin/action_log` | All API call history |
| POST | `/_admin/snapshot/{name}` | Save named snapshot |
| POST | `/_admin/restore/{name}` | Restore named snapshot |
| GET | `/_admin/tasks` | List registered tasks |
| POST | `/_admin/tasks/{name}/evaluate` | Run task evaluation |

## Testing

```bash
uv run --extra dev pytest tests -q
```

## Project Structure

```
mock_gdoc/
├── api/          # FastAPI routes and schemas
├── models/       # SQLAlchemy ORM models
├── seed/         # Scenario data generators
├── state/        # Snapshots, diffs, action log
├── tasks/        # Demo evaluation tasks
├── web/          # HTML document browser
├── mcp/          # Optional MCP server
├── cli.py        # CLI entry point
└── server.py     # Uvicorn launcher
```

## Contribution Notes

- Repo-level task-shaped fixtures live under `example_tasks/`; local demo/admin
  tasks are registered under `mock_gdoc/tasks/`.
- Development backlog lives in tracked issues and pull requests.
- For repo-wide workflow notes, see the root `README.md` and `AGENTS.md`.
