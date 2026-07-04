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
BENCHFLOW_REWARD_LENIENT=1 bench eval run \
  --tasks-dir example_tasks --agent oracle --sandbox docker \
  --context-root . --jobs-dir .local/bf-jobs-public-examples
```

`PULL_BASE=0` is intentional for local validation: it uses the base image built
by `docker/build-base.sh`. Use the default pull behavior only after a maintainer
has pushed `ghcr.io/benchflow-ai/env0:<VERSION>`.

The `bench eval run` command is the end-to-end task validation path. It verifies
that BenchFlow can build public task images, start the manifest-declared
`mock-*` services, run oracle solutions, and score verifiers.

For the public `tasks/` reference set and local Codex/Claude agent setup, use
the self-contained guide in
[`docs/guides/run-tasks-with-benchflow.md`](guides/run-tasks-with-benchflow.md).
The all-task oracle baseline for the current public task set is:

```bash
BENCHFLOW_REWARD_LENIENT=1 bench eval run \
  --tasks-dir tasks \
  --include auth-least-privilege-summary \
  --include discord-incident-followup \
  --include email-confidential-forward \
  --include email-no-wrong-recipients \
  --include email-vendor-report-organize \
  --include gcal-federal-register-meeting-amendments \
  --include gdoc-search-keyword-index \
  --include gdrive-sensitive-file-lockdown \
  --include multi-doc-slack-spec-drift \
  --include multi-mail-cal-sync \
  --include slack-channel-reorg \
  --include slack-search-channel-history \
  --include stripe-refund-correct-customer \
  --agent oracle \
  --sandbox docker \
  --context-root . \
  --concurrency 1 \
  --build-concurrency 1 \
  --jobs-dir .local/bf-oracle-all-public
```

That command should complete with `13/13`, `errors=0`, and `idle_timeouts=0`.

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
end-to-end also requires Docker, the BenchFlow CLI, and a pullable public env0
base image.
