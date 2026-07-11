# Standard60 Tasks

This directory publishes the current 60-task Standard60 snapshot as
BenchFlow-native task packages. The exact package list is tracked in
[`STANDARD60_MANIFEST.txt`](STANDARD60_MANIFEST.txt).

The public packages use the env0 runtime contract:

- `task.md` uses BenchFlow `schema_version: '1.3'`.
- `benchflow.env0.services` declares the required public `mock-*` services.
- `environment/Dockerfile` pins `ghcr.io/benchflow-ai/env0:0.2.0`.
- `oracle/` and `verifier/` use the native BenchFlow package layout.
- Seed payloads under `/tasks` are locked after build-time seeding.

The snapshot contains 11 auth, 8 email, 3 calendar, 10 document, 3 Drive,
12 multi-service, 8 Slack, and 5 Stripe tasks. Discord is not part of
Standard60; its runtime fixture remains under
[`example_tasks/discord-incident-followup`](../example_tasks/discord-incident-followup).

`tasks/` is a runnable public snapshot, not the task-authoring source of truth.
`example_tasks/` remains the smaller fixture/template surface for env0 runtime
development.

## Validation

Verify the exact snapshot and public-runtime invariants:

```bash
python3 -m unittest tests/test_standard60_tasks.py
```

Run BenchFlow structural checks:

```bash
while IFS= read -r task; do
  bench tasks check "tasks/${task}" --level structural
done < tasks/STANDARD60_MANIFEST.txt
```

Run the full oracle baseline:

```bash
BENCHFLOW_REWARD_LENIENT=1 bench eval run \
  --tasks-dir tasks \
  --agent oracle \
  --sandbox docker \
  --context-root . \
  --concurrency 1 \
  --build-concurrency 1 \
  --jobs-dir .local/bf-oracle-standard60
```

End-to-end evaluation requires Docker, the BenchFlow CLI, and either a locally
built or remotely published `ghcr.io/benchflow-ai/env0:0.2.0` image.
