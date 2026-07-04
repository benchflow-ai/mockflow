# Validated Workflows

This page lists commands that are expected to run from the repo root and what
they validate. Keep it current when contracts change.

## Local Control And Devhub

```bash
python3 -m unittest tests/test_env0_control.py
python3 devhub/app.py --render-once
scripts/smoke_dev.sh
```

These commands validate service metadata loading, launcher dry-runs, task-shaped
seeding, and devhub rendering.

## Docker Base And Example Tasks

```bash
docker/build-base.sh
PULL_BASE=0 scripts/smoke_docker_examples.sh
```

`PULL_BASE=0` is intentional for local validation: it uses the base image built
by `docker/build-base.sh`. Use the default pull behavior only after a maintainer
has pushed `ghcr.io/benchflow-ai/env0:<VERSION>`.

Maintainers can publish the release image with the `Publish Base Image` GitHub
Actions workflow. The workflow uses the repository `GITHUB_TOKEN` with
`packages: write`, pushes `ghcr.io/benchflow-ai/env0:<VERSION>` and `latest`,
and verifies a remote pull before completing.

## One Environment Package

```bash
cd packages/environments/mock-gdrive
uv run --extra dev pytest tests/test_conformance.py -q
uv run --extra dev pytest tests -q
```

Use these when changing mock-gdrive API behavior. Substitute another
`packages/environments/mock-*` directory for that service.

## Imported BenchFlow Tasks

```bash
for task in tasks/*; do
  [ -d "$task" ] || continue
  [ "$(basename "$task")" = "_manifests" ] && continue
  bench tasks check "$task" --level structural
done
```

This validates copied BenchFlow task packages structurally. Running them
end-to-end also requires a usable `env-0-base` image and the BenchFlow CLI.
