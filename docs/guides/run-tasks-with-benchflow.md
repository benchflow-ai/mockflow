# Run Public Tasks With BenchFlow

This guide is the self-contained path for a new contributor to clone `env0`,
build the public mock environment image, and run real task packages end to end
with BenchFlow.

Validated on 2026-07-10 with:

- `benchflow==0.6.4`
- Docker Desktop 29.3.0
- Codex CLI 0.142.4 using local subscription auth
- Claude Code 2.1.185 host login preflight

The public task runtime uses `tasks/_manifests/env-0.toml` and these service
ports: auth `9000`, Gmail `9001`, Calendar `9002`, Drive `9003`, Docs `9004`,
Slack `9005`, Discord `9006`, and Stripe `9007`.

## 1. Fresh Checkout

Install Git, Docker, Python 3.12+, and `uv`. Then clone this repository:

```bash
git clone https://github.com/benchflow-ai/env0.git
cd env0
```

Use the pinned BenchFlow version validated by this guide:

```bash
export BENCHFLOW_VERSION=0.6.4
uvx --from "benchflow==${BENCHFLOW_VERSION}" bench --version
```

Expected output:

```text
benchflow 0.6.4
```

On Apple Silicon, build and run the Linux/amd64 task images:

```bash
export DOCKER_DEFAULT_PLATFORM=linux/amd64
```

## 2. Build The Public Base Image

```bash
docker/build-base.sh
```

This builds:

```text
ghcr.io/benchflow-ai/env0:0.2.0
ghcr.io/benchflow-ai/env0:latest
```

You can also run from a published base image after maintainers push it, but a
fresh contributor should be able to build locally with the command above.

## 3. Check Task Packages

Standard60 covers auth, Gmail, Calendar, Drive, Docs, Slack, and Stripe.
Discord is an env0 runtime fixture but is not part of the 60-task benchmark
snapshot.

| Package | Services covered |
|---|---|
| `tasks/auth-least-privilege-summary` | `mock-auth`, `mock-gmail` |
| `tasks/gcal-federal-register-meeting-amendments` | `mock-gcal` |
| `tasks/gdoc-search-keyword-index` | `mock-gdrive`, `mock-gdoc` |
| `tasks/slack-search-channel-history` | `mock-slack` |
| `tasks/stripe-refund-correct-customer` | `mock-stripe` |
| `example_tasks/discord-incident-followup` | `mock-discord` |

Run structural checks for all 60 benchmark packages:

```bash
python3 -m unittest tests/test_standard60_tasks.py

while IFS= read -r task; do
  uvx --from "benchflow==${BENCHFLOW_VERSION}" bench tasks check \
    "tasks/${task}" --level structural
done < tasks/STANDARD60_MANIFEST.txt
```

Run runtime-capability checks across every public mock service:

```bash
for task_dir in \
  tasks/auth-least-privilege-summary \
  tasks/gcal-federal-register-meeting-amendments \
  tasks/gdoc-search-keyword-index \
  tasks/slack-search-channel-history \
  tasks/stripe-refund-correct-customer \
  example_tasks/discord-incident-followup
do
  uvx --from "benchflow==${BENCHFLOW_VERSION}" bench tasks check \
    "${task_dir}" --level runtime-capability --sandbox docker
done
```

## 4. Run The Oracle Baseline

Run all public task packages with shipped oracle solutions:

```bash
export BENCHFLOW_REWARD_LENIENT=1

uvx --from "benchflow==${BENCHFLOW_VERSION}" bench eval run \
  --tasks-dir tasks \
  --agent oracle \
  --sandbox docker \
  --context-root . \
  --concurrency 1 \
  --build-concurrency 1 \
  --jobs-dir .local/bf-oracle-all-public
```

Expected result for this revision:

```text
Job complete: 60/60 (100.0%), errors=0, idle_timeouts=0
```

## 5. Run With Codex Subscription Auth

Log in locally first:

```bash
codex login
test -s "$HOME/.codex/auth.json"
```

Probe the local subscription auth:

```bash
CODEX_HOME="$(mktemp -d /tmp/codex-home.XXXXXX)"
mkdir -p "$CODEX_HOME"
cp "$HOME/.codex/auth.json" "$CODEX_HOME/auth.json"
printf 'model = "gpt-5.5"\nmodel_reasoning_effort = "xhigh"\n[features]\napps = false\n' > "$CODEX_HOME/config.toml"
env -u OPENAI_API_KEY -u OPENAI_BASE_URL CODEX_HOME="$CODEX_HOME" \
  codex exec --disable apps -m gpt-5.5 "Reply exactly ok"
```

Run a five-task Standard60 environment coverage matrix:

```bash
unset OPENAI_API_KEY OPENAI_BASE_URL
export CODEX_AUTH_JSON="$(tr -d '\n' < "$HOME/.codex/auth.json")"
export CODEX_CONFIG='{"model":"gpt-5.5","model_reasoning_effort":"xhigh","features":{"apps":false}}'

uvx --from "benchflow==${BENCHFLOW_VERSION}" bench eval run \
  --tasks-dir tasks \
  --include auth-least-privilege-summary \
  --include gcal-federal-register-meeting-amendments \
  --include gdoc-search-keyword-index \
  --include slack-search-channel-history \
  --include stripe-refund-correct-customer \
  --agent codex-acp \
  --model gpt-5.5 \
  --agent-env CODEX_AUTH_JSON="${CODEX_AUTH_JSON}" \
  --agent-env CODEX_CONFIG="${CODEX_CONFIG}" \
  --sandbox docker \
  --context-root . \
  --concurrency 1 \
  --build-concurrency 1 \
  --agent-idle-timeout 900 \
  --jobs-dir .local/bf-codex-gpt55-env-coverage
```

Do not pass `--reasoning-effort` to `codex-acp` on BenchFlow 0.6.4. Put Codex
reasoning settings in `CODEX_CONFIG` as shown above.
Keep Codex `apps` disabled for these runs. The task runtime should exercise only
the local Docker mock services, not hosted app connectors attached to the
operator's Codex account.

Model pass rate is not the same as environment health. Use the oracle baseline
as the release gate; this smaller model run is an optional agent-integration
smoke.

## 6. Claude Code Status

Host Claude Code subscription login can be checked with:

```bash
claude -p --model opus --effort max --max-budget-usd 1 "Reply with exactly: ok"
```

BenchFlow 0.6.4's `claude-agent-acp` path needs transferable credentials inside
the Docker sandbox. A host login that works through the local keychain is not
enough unless BenchFlow can see one of these:

- `~/.claude/.credentials.json`
- a valid `CLAUDE_CODE_OAUTH_TOKEN`
- a valid `CLAUDE_OAUTH_TOKEN`

Before running a Claude task, check for one of those credentials:

```bash
test -f "$HOME/.claude/.credentials.json" || \
  test -n "${CLAUDE_CODE_OAUTH_TOKEN:-}" || \
  test -n "${CLAUDE_OAUTH_TOKEN:-}"
```

Then run a one-task probe:

```bash
uvx --from "benchflow==${BENCHFLOW_VERSION}" bench eval run \
  --tasks-dir example_tasks \
  --include discord-incident-followup \
  --agent claude-agent-acp \
  --model opus \
  --sandbox docker \
  --context-root . \
  --concurrency 1 \
  --build-concurrency 1 \
  --agent-idle-timeout 900 \
  --jobs-dir .local/bf-claude-opus-probe
```

If BenchFlow fails before starting Docker with `ANTHROPIC_API_KEY required`, it
did not find transferable Claude credentials. If the agent starts and then fails
with `401 Invalid bearer token`, the exported OAuth token is stale. Refresh the
Claude Code login/token locally before rerunning.

Do not pass `--reasoning-effort` to `claude-agent-acp` on BenchFlow 0.6.4.

## Troubleshooting

- If Docker on Apple Silicon builds or runs the wrong architecture, re-export
  `DOCKER_DEFAULT_PLATFORM=linux/amd64`.
- If a verifier reaches the wrong service, compare the script default with
  `tasks/_manifests/env-0.toml`.
- If Codex starts but uses API-key auth instead of subscription auth, unset
  `OPENAI_API_KEY` and `OPENAI_BASE_URL`, then pass `CODEX_AUTH_JSON`.
- If a model task times out, inspect the task's `timeout_sec` in `task.md` and
  the per-task `result.json` under the chosen `--jobs-dir`.
