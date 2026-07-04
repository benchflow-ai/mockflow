# Adding a New Environment

Idea to merged mock service. An env0 environment is a deterministic,
high-fidelity mock of a real service API plus local dev surfaces. Agents should
be able to point tools at localhost instead of a production provider without
changing their normal workflow.

Existing services:

- `mock-gmail`
- `mock-gcal`
- `mock-gdoc`
- `mock-gdrive`
- `mock-slack`

Adding an environment is larger than adding an example task because the service
package is installed into the shared Docker base image. Keep the change narrow:
environment code, fixtures, conformance tests, config registration, and docs.

## Package Layout

Create a package under `packages/environments/<mock-service>/`:

```text
packages/environments/mock-new/
├── pyproject.toml
├── mock_new/
│   ├── cli.py
│   ├── server.py
│   ├── api/
│   ├── models/
│   ├── seed/
│   ├── state/
│   ├── web/
│   └── tasks/
├── scripts/
│   ├── auth.py
│   ├── capture_fixtures.py
│   └── validate_seed.py
├── tests/
│   ├── conftest.py
│   ├── test_api.py
│   ├── test_conformance.py
│   └── fixtures/
│       ├── mock_coverage.json
│       └── real_new/
├── API_NOTES.md
└── README.md
```

`tasks/` inside an env package is optional and only for env-local development.
Repo-level task-shaped fixtures live in `env0/example_tasks`. Canonical
benchmark task authoring lives downstream.

## CLI Contract

The CLI name should match the service id:

```toml
[project.scripts]
mock-new = "mock_new.cli:cli"
```

Required commands:

```bash
mock-new --db /path/to/new.db seed --scenario default
mock-new --db /path/to/new.db serve --host 0.0.0.0 --port 9006 --no-mcp
mock-new --db /path/to/new.db reset
```

`seed` must save an initial snapshot. `reset`, `/_admin/reset`, and
`/_admin/diff` depend on that baseline.

If the env supports task-aware seeding, also support:

```bash
mock-new --db /path/to/new.db seed \
  --task-data /var/lib/task/data \
  --task-name <task-name>
```

`--task-data` is internal plumbing for Docker/control scripts. User-facing dev
UX stays task-name based through `scripts/dev.sh task <name>`.

## Server Contract

Every service should expose:

- `/health`
- `/_admin/reset`
- `/_admin/state`
- `/_admin/diff`
- `/_admin/action_log`
- `/_admin/snapshot/{name}`
- `/_admin/restore/{name}`
- `/_admin/seed`
- `/dev/dashboard`
- `/dev/api-explorer`
- `/dev/db-viewer`

The mock API should mirror the real provider's paths, response shapes, error
bodies, pagination, and mutation side effects closely enough that agent
failures are meaningful. Toy shapes are worse than missing endpoints because
they teach agents the wrong contract.

Admin task seeding should validate `task_name` before destructive DB reset:

- require `TASKS_DIR`
- resolve under `TASKS_DIR`
- reject path traversal
- require `data/needles.py`
- drop/reseed only after validation passes

Two design rules make verifiers and debugging much more reliable:

- Stamp a stable role marker into object metadata when the real API has a place
  for metadata. Evaluators should resolve ids from roles, emails, titles, or
  other seeded facts instead of hardcoding generated ids.
- Record meaningful `action_log` entries for mutations and important reads.
  Verifiers often need to distinguish a correct final state from a lucky or
  unsafe path.

## Register In Config

Add a section to `config.toml`:

```toml
[mock-new]
port = 9006
db_path = "/data/new.db"
env_var = "MOCK_NEW_URL"
gws_service = "new"  # optional, only if gws wrapper supports it
```

`config.toml` is the runtime source of truth. Do not add a hand-maintained
service manifest. If another artifact is needed later, generate it from
`config.toml`.

Port allocation:

- use the next available `900x` service port
- avoid existing `9001`-`9005`
- keep devhub on `9060`

After adding a service, update current service-map exceptions:

- `scripts/smoke_docker_examples.sh`
- `docker/gws-wrapper.sh`, if the service has a `gws_service`

## Docker Base Image

`docker/generate_dockerfile.py` reads `config.toml` and the environment package
dirs to generate `docker/Dockerfile.base`.

Build locally:

```bash
docker/build-base.sh
```

Push release tags only if the GHCR package exists and your account has package
write permission:

```bash
docker/build-base.sh --push
```

`VERSION` controls the canonical semver tag.

Validate the generated Dockerfile without building:

```bash
python3 docker/generate_dockerfile.py --dry-run >/tmp/env0-Dockerfile.base
```

## Example Task Dockerfile

Use thin task images. Do not copy env source code into task images.

```dockerfile
FROM ghcr.io/benchflow-ai/env0:<VERSION>

WORKDIR /app
ENV TASK_ROOT=/var/lib/task

COPY example_tasks/my-task/data /var/lib/task/data
COPY example_tasks/my-task/oracle /var/lib/task/oracle

RUN chmod 700 /var/lib/task && \
    mock-new --db /data/new.db seed \
      --task-data /var/lib/task/data \
      --task-name my-task

RUN mkdir -p /logs/verifier /logs/agent /logs/artifacts
RUN chown agent:agent /logs/agent /logs/artifacts
```

Replace `<VERSION>` with the contents of repo `VERSION`, for example:

```bash
cat VERSION
```

For dependent envs, seed the source-of-truth env first. Example: GDrive owns
file metadata/content; GDoc mirrors from GDrive with `--from-gdrive`.

## Validation

Minimum checks for a new env:

```bash
cd packages/environments/mock-new
uv run --extra dev pytest tests/ -q
```

Then from repo root:

```bash
scripts/smoke_dev.sh
docker/build-base.sh
PULL_BASE=0 scripts/smoke_docker_examples.sh
```

Also check:

- `uv.lock` is updated if dependencies changed
- `tests/test_conformance.py` covers every committed real fixture
- `tests/fixtures/mock_coverage.json` is updated for route/fixture coverage
- `API_NOTES.md` documents real API quirks and intentional divergences
- dependent env seed ordering is covered if the env derives state from another
  service

If adding an example task, ensure:

- Dockerfile builds from `ghcr.io/benchflow-ai/env0:<VERSION>` after
  `docker/build-base.sh` has created that tag locally.
- expected DB files are seeded
- services start and pass `/health`
- hidden payload is unreadable by `agent`

## API Fidelity

Follow [API validation playbook](api-validation-playbook.md). Each env should
keep:

- `API_NOTES.md`
- `scripts/capture_fixtures.py`
- `tests/test_conformance.py`
- `tests/fixtures/mock_coverage.json`
- `tests/fixtures/real_<service>/*.json`
