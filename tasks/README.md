# Imported env-0 Tasks

This directory contains a small selected set of BenchFlow-native task packages
copied from `benchflow-ai/env-0`.

These tasks intentionally keep their original `env-0` runtime contract:

- `task.md` uses BenchFlow `schema_version: '1.3'`.
- `environment/Dockerfile` uses `ghcr.io/benchflow-ai/env-0-base:latest`.
- `tasks/_manifests/env-0.toml` declares the env-0 service plane.

They are not wired into `example_tasks/`, which remain env0's local runtime
fixtures for mock service development.

The larger env-0 eval and training corpora live in the upstream (private)
`benchflow-ai/env-0` repo, not here. This directory stays small so the public
env0 task reference surface remains easy to inspect.

## Validation

Structural validation uses BenchFlow:

```bash
for task in tasks/*; do
  [ -d "$task" ] || continue
  [ "$(basename "$task")" = "_manifests" ] && continue
  bench tasks check "$task" --level structural
done
```

End-to-end evaluation requires `ghcr.io/benchflow-ai/env-0-base:latest` to be
pullable by the sandbox backend. If that image is private or missing, task image
builds will fail before any agent or verifier runs.
