# env0 Dev Launcher

Phase 1 provides a repo-local launcher, control contract, and small devhub. It
does not add verifier UI, eval UI, or benchmark dashboards.

## User UX

Start every configured mock service with default seed data:

```bash
scripts/dev.sh
```

Start only the services declared by a task:

```bash
scripts/dev.sh task email-confidential-forward
```

Tasks are resolved from `example_tasks/<name>`. The launcher reads
`task.md` frontmatter `benchflow.env0.services`, then internally resolves
`example_tasks/<name>/data/needles.py` for task-aware seeding. Raw
`--task-data` remains an internal env CLI detail, not the primary launcher UX.

## Control Contract

`scripts/env0_control.py` is the stable repo-local control path used by the
launcher and devhub:

```bash
scripts/env0_control.py start-default
scripts/env0_control.py start-task <task-name>
scripts/env0_control.py seed-default [service...]
scripts/env0_control.py seed-task <task-name> [service...]
scripts/env0_control.py reset [service...]
scripts/env0_control.py snapshot <name> [service...]
scripts/env0_control.py restore <name> [service...]
```

Use `--dry-run` to prove the contract without starting processes or sending
admin requests.

Run the repo smoke check before changing launcher/control behavior:

```bash
scripts/smoke_dev.sh
```

The smoke check runs unit tests, proves dry-run contracts, performs one real
task-aware GDrive seed, and verifies a known seeded needle exists in the DB.

## Devhub

`scripts/dev.sh` starts services and devhub together:

```bash
scripts/dev.sh
```

Default devhub URL:

```text
http://127.0.0.1:9060
```

Devhub app code lives in `devhub/`. It is intentionally repo-local and
stdlib-only in this phase. The server logic is in `devhub/app.py`, with HTML in
`devhub/templates/` and CSS in `devhub/static/`. It reads service cards from
`config.toml`, checks health live, links service docs/dev surfaces, and uses the
same admin/control contract for seed/reset/snapshot and restore actions.

The task panel reads only `example_tasks/*`. Its seed button posts
`task_name=<name>` to the running services declared by
`task.md` frontmatter `benchflow.env0.services`. This prepares env state only; it does not
run verifiers or evals.

Env-local `/dev/tasks` menus/routes are intentionally not part of the dev
surface. Repo task browsing and task-shaped seeding live in devhub; evaluator
execution stays out of env0 devhub scope.

Empty stale task admin/docs surfaces are also hidden where no env-local task
registry exists. Gmail/GDoc/GCal keep env-local task admin APIs temporarily for
CLI/Gym/test compatibility, but GDrive and Slack do not advertise or expose
`/_admin/tasks` task evaluation endpoints.

You can still run devhub by itself when services are already running:

```bash
python3 devhub/app.py
```

## Metadata Source

`config.toml` is the source of truth for service ids, ports, DB paths,
canonical `MOCK_*_URL` env vars, and `gws_service` mapping. The launcher reads
service metadata from `config.toml` and never scans Dockerfile text for service
inference.

For each service the launcher prints root URL, docs URL, advertised dev URLs,
DB path, seed mode, canonical env export, and gws mapping where configured.
All first-party mock services advertise `/dev/dashboard`, `/dev/db-viewer`, and
`/dev/api-explorer`.

## Seed Modes

Default sessions seed all configured mock services with `--scenario default`.

Task sessions seed only task-declared services. Gmail, GCal, GDrive, GDoc, and Slack
receive task-aware data when `example_tasks/<name>/data/needles.py` exists.
Gmail also writes its oracle manifest under `.data/oracle/<task>/manifest.json`.
