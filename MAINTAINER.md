# Maintainer Guide

This guide covers release and publication work. Contributor-facing setup remains
in [`CONTRIBUTING.md`](CONTRIBUTING.md).

## Repository Boundaries

- `config.toml` is the source of truth for public mock-service metadata.
- `example_tasks/` contains small runtime fixtures and templates.
- `tasks/` publishes the exact Standard60 snapshot listed in
  `tasks/STANDARD60_MANIFEST.txt`.
- Task authoring and benchmark policy remain downstream concerns.

## Pull Request Gate

Before merging a release-affecting pull request:

```bash
scripts/smoke_dev.sh
python3 -m unittest \
  tests/test_standard60_tasks.py \
  tests/test_public_data_hygiene.py
```

Run the relevant package conformance suite when service behavior changes:

```bash
cd packages/environments/mock-gdrive
uv run --extra dev pytest tests/test_conformance.py -q
```

CI additionally:

- builds the current `VERSION` image;
- smokes every example-task image;
- runs one oracle task for each of the eight public mock environments;
- verifies all 68 task packages use native `task.md` layout.

## Standard60 Updates

When refreshing `tasks/`:

1. Keep exactly the names in `tasks/STANDARD60_MANIFEST.txt`.
2. Use only `task.md`, `oracle/`, and `verifier/`; do not add `task.toml`,
   `instruction.md`, `solution/`, or task-level `tests/`.
3. Use public `mock-*` CLIs and the current
   `ghcr.io/benchflow-ai/env0:<VERSION>`.
4. Lock copied seed payloads after image build-time seeding.
5. Replace real-person identifiers and credential-shaped values with reserved
   synthetic fixtures before publication.

## Base Image Release

`VERSION` is the base-image semver source of truth.

After the release PR is squash-merged and `main` CI is green:

1. Dispatch the `Publish Base Image` workflow on `main`.
2. Confirm it pushes both `ghcr.io/benchflow-ai/env0:<VERSION>` and `latest`.
3. Confirm its remote verification step finds all eight `mock-*` CLIs.
4. Tag the merged commit using the repository release line, for example
   `v0.2` for `VERSION=0.2.0`.
5. Publish a GitHub release from that tag and verify it is marked latest.

Do not publish the GitHub release before the GHCR workflow succeeds.

## Public Data Review

Before release, verify:

- no `.env`, auth, token, credential, database, or local runtime files are
  tracked;
- no real API keys, JWTs, assignable SSNs, local workstation paths, or private
  repository links are present;
- live-capture fixtures contain only sanitized test-account data;
- intentional mock credentials and test cards are clearly documented and have
  no authority outside localhost services.

Report actual vulnerabilities privately according to [`SECURITY.md`](SECURITY.md).
