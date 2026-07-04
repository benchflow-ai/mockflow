# env0 Agent Instructions

env0 owns mock environment development, local env tooling, seeding
contracts, API parity, and the shared Docker base image.

## Boundaries

- Do not turn env0 into benchmark dashboard, verifier UI, or task-authoring
  source of truth.
- `example_tasks/` are fixtures/templates for env runtime testing, not canonical
  benchmark tasks.
- Real benchmark tasks and scoring semantics belong in downstream benchmark
  packages or consumers.
- Prefer current `mock-*` / `MOCK_*` names. Do not add legacy service-name contracts.

## Core Contracts

- Read service metadata from `config.toml`.
- Use `task.md` frontmatter `benchflow.env0.services: [...]` for task service
  selection.
- Do not infer services from Dockerfile text.
- Keep public launcher UX task-name based: `scripts/dev.sh task <name>`.
- Keep raw `--task-data` / task-data-path plumbing internal to env CLIs,
  control scripts, and Dockerfiles.
- Thin task images must use `FROM ghcr.io/benchflow-ai/env0:<VERSION>` and hidden payload
  under `/var/lib/task`.
- `VERSION` is the base-image semver source of truth.

## Commands

No manual virtualenv setup is needed for normal env0 workflows. The repo
control/devhub scripts use stdlib Python, and env package commands are invoked
through `uv run` when available. Install `uv`; let it create/sync per-package
`.venv` state as needed.

Run before/after launcher or devhub changes:

```bash
scripts/smoke_dev.sh
```

Run before/after Dockerfile or base-image changes:

```bash
scripts/smoke_docker_examples.sh
```

Build/push base image:

```bash
docker/build-base.sh --push
```

Testing matrix:

- Launcher/control/devhub: `scripts/smoke_dev.sh`
- Docker/base/example tasks: `scripts/smoke_docker_examples.sh`
- One env package: `cd packages/environments/mock-gdrive && uv run --extra dev pytest tests -q`
- API conformance: `cd packages/environments/mock-gdrive && uv run --extra dev pytest tests/test_conformance.py -q`
- Devhub render only: `python3 devhub/app.py --render-once`

## Editing Guidance

- Keep `config.toml` as runtime metadata SSOT.
- Current exceptions: `scripts/smoke_docker_examples.sh` and
  `docker/gws-wrapper.sh` have service maps that must be kept in sync when
  adding or changing services.
- If an external manifest is needed later, generate it from `config.toml`; do
  not hand-maintain a second service registry.
- Preserve `example_tasks/*/environment/Dockerfile` as minimal templates.
- Do not copy env source code into task images.
- Keep hidden task data unreadable by normal `agent` user.
- Update docs when changing seed, Docker, or devhub contracts.
