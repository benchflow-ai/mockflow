# env0 Docs

env0 is a mock-environment runtime. These docs stay focused on service
development, API parity, seed contracts, local tooling, and Docker runtime
validation.

## Start Here

- [Local dev and devhub](dev.md) — run configured services, task-shaped seeds,
  and the repo-local devhub.
- [Good first contributions](good-first-contributions.md) — high-value ways to
  improve env0 without touching benchmark scoring policy.
- [Adding a new environment](adding-new-environment.md) — package layout, CLI
  contract, admin endpoints, config registration, Docker base-image wiring, and
  validation.
- [API validation playbook](api-validation-playbook.md) — capture and compare
  real API fixtures.
- [Parity audit](parity-audit/README.md) — cross-environment fixture and
  conformance status.
- [Validated workflows](validated-workflows.md) — commands that have been run
  against this checkout and the intended preconditions for heavier commands.
- [Run public tasks with BenchFlow](guides/run-tasks-with-benchflow.md) —
  self-contained setup and subscription-agent task runs for public tasks.
- [Contributing](../CONTRIBUTING.md) — repo boundaries, validation matrix, and
  pull request expectations.
- [Maintainer guide](../MAINTAINER.md) — Standard60 sync, image publication,
  versioning, and GitHub release workflow.
- [Security policy](../SECURITY.md) — private vulnerability reporting and
  credential hygiene.

## Boundaries

- `example_tasks/` are env0 runtime fixtures.
- `tasks/` publishes the current 60-package Standard60 snapshot for public
  downstream evaluation.
- Canonical benchmark task authoring and scoring semantics live outside this
  repo.
