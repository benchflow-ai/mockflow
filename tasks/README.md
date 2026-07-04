# Imported env-0 Tasks

This directory contains a small selected set of BenchFlow-native task packages
copied from `benchflow-ai/env-0`.

These tasks are wired to the public env0 runtime contract:

- `task.md` uses BenchFlow `schema_version: '1.3'`.
- `environment/Dockerfile` uses `ghcr.io/benchflow-ai/env0:0.1.0`.
- `tasks/_manifests/env-0.toml` declares the public `mock-*` service plane.

They are not wired into `example_tasks/`, which remain env0's local runtime
fixtures for mock service development.

This directory stays small so the public env0 task reference surface remains
easy to inspect.

## Validation

Structural validation uses BenchFlow:

```bash
for task in tasks/*; do
  [ -d "$task" ] || continue
  [ "$(basename "$task")" = "_manifests" ] && continue
  bench tasks check "$task" --level structural
done
```

End-to-end evaluation requires the BenchFlow CLI, Docker, and a pullable public
env0 base image. The reference task Dockerfiles inherit from
`ghcr.io/benchflow-ai/env0:0.1.0`.
