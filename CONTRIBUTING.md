# Contributing to env0

env0 is the first-party mock-environment runtime for agent testing. It owns
high-fidelity mock services, deterministic seed data, local tooling,
API-parity fixtures, devhub, and the shared Docker base image.

The current v0.1 runtime ships five high-fidelity mock services:
`mock-gmail`, `mock-gcal`, `mock-gdrive`, `mock-gdoc`, and `mock-slack`.
They replicate Google Workspace and Slack API surfaces with state management
and deterministic snapshot/restore.

There are two ways to contribute:

- **Chat with BenchBot.** Best for proposing or prototyping a new mock
  environment with maintainer help. Describe the environment you want in the
  [BenchFlow Discord](https://discord.gg/G9dg3EfSva) and build it
  conversationally with an agent, the same way you interact with coding agents
  like Codex or Claude Code. Final env0 changes still go through maintainer
  review before landing.
- **Open a pull request.** The classic GitHub workflow for direct changes to
  this repo.

If you want to contribute benchmark tasks or scoring policy, use the downstream
benchmark package that owns those tasks. This repo keeps task-shaped assets for
env runtime validation and copied-reference workflows:

- [`example_tasks/`](https://github.com/benchflow-ai/env0/tree/main/example_tasks)
  contains small runtime fixtures/templates for env0 service and launcher
  testing.
- [`tasks/`](https://github.com/benchflow-ai/env0/tree/main/tasks) contains a
  small copied [BenchFlow](https://github.com/benchflow-ai/benchflow)-native
  reference set.

## What To Contribute

| Area | Good contribution | Start here |
|---|---|---|
| Environment packages | Add a new `mock-*` service or improve an existing one. | [`docs/adding-new-environment.md`](docs/adding-new-environment.md) |
| Mock API fidelity | Add or correct endpoints, response shapes, errors, pagination, side effects, or conformance fixtures. | [`docs/api-validation-playbook.md`](docs/api-validation-playbook.md) |
| Seed realism | Improve deterministic seed data, filler distributions, role markers, or task-aware seed paths. | Existing `packages/environments/mock-*/seed/` modules |
| Dev tooling | Improve `scripts/dev.sh`, `scripts/env0_control.py`, devhub, smoke tests, or Docker base-image generation. | [`docs/dev.md`](docs/dev.md) |
| Documentation | Fix inaccurate commands, clarify preconditions, or document real parity gaps. | This file plus [`README.md`](README.md) |

Not sure where to start? See
[`docs/good-first-contributions.md`](docs/good-first-contributions.md).

## Contribute New Environments With BenchBot

BenchBot is [BenchFlow](https://www.benchflow.ai/)'s Discord-native build
agent for guided prototyping. You drive it the way you would use Claude Code or
Codex: say what you want, hand it reference material, and iterate on what it
builds. Behind the scenes BenchBot provisions a dedicated build VM for you,
runs coding agents on it, streams progress back into the Discord thread, and
can post live preview URLs for generated artifacts.

Treat BenchBot output as a starting point. Finished env0 contributions still
need to satisfy the repo boundaries and validation checks below.

### 1. Join the BenchFlow Discord

Join at [discord.gg/G9dg3EfSva](https://discord.gg/G9dg3EfSva).

### 2. Connect your agent credentials

Builds run with your own agent credentials on a per-user VM provided by
BenchFlow. Run `/bot-connect` in Discord and follow the link to the
[dashboard connect page](https://benchchat.vercel.app/connect), then paste your
Anthropic API key there.

Credentials are entered on the dashboard only and stored encrypted. Never
paste API keys or any other secret into a Discord message.

### 3. Tell BenchBot what you want to build

Mention `@BenchBot` in a channel where it is active and describe the
environment. Name the real service, the API surfaces that matter, and what
realistic state looks like. For example:

```text
@BenchBot I want to add a mock Notion environment to env0: REST API parity
for pages, databases, and search; deterministic seed data; and conformance
fixtures. API reference: https://developers.notion.com/reference
```

### 4. Provide docs and files

The fidelity of a mock tracks the quality of its reference material. Share in
the thread:

- links to the real service's API documentation
- sample request/response payloads, error shapes, pagination examples
- what realistic seed data should look like (inbox contents, channel history,
  file trees; use sanitized synthetic data, never real account exports or
  handoff bundles)
- one or two agent tasks the environment should be able to support

### 5. Iterate in the thread

Reply in the thread to keep going — follow-up messages continue the same
session, no re-mention needed. Ask for changes, point out parity gaps, and
check each round's preview URL, exactly like a code-review loop with Claude
Code or Codex.

### 6. Follow along on the dashboard

Open [benchchat.vercel.app](https://benchchat.vercel.app) and sign in with
Discord. The dashboard shows your sessions, run history, agent traces,
artifacts, and preview links.

One note on lifecycle: build VMs are recycled after a couple of hours of
inactivity. Your traces and artifacts stay on the dashboard; a new message
simply starts a fresh session.

### 7. Landing it in env0

When the prototype holds up — endpoints behave, seeds are deterministic, and
previews look right — say so in the thread and a maintainer will review it
against the boundaries below. A maintainer may land the generated work directly
or ask you to open a normal PR from the generated branch. Skimming
[`docs/adding-new-environment.md`](docs/adding-new-environment.md) is still
worthwhile so you know what a finished environment includes, even when BenchBot
does the typing.

## Boundaries

These apply to every contribution, whether it comes from BenchBot or a direct
PR:

- Keep service ids and CLIs on current `mock-*` names.
- Keep service URL env vars on current `MOCK_*_URL` names.
- Read service metadata from `config.toml`; do not infer services from
  Dockerfile text.
- Keep public launcher UX task-name based: `scripts/dev.sh task <name>`.
- Keep raw `--task-data` plumbing internal to env CLIs, control scripts, and
  Dockerfiles.
- Preserve `example_tasks/*/environment/Dockerfile` as minimal runtime
  templates.
- Do not copy environment source code into thin task images.
- Do not commit credentials, OAuth tokens, live account exports, or private
  customer data — and do not paste them into Discord.
- Do not commit BenchChat handoff bundles, `.env` files, generated credential
  exports, or API-key screenshots.

## Contribute With A Pull Request

Prefer this path for direct code changes: bug fixes, tooling, docs, or when
you want full local control over an environment package.

### Development setup

Use `uv run` from the relevant package directory. Normal workflows do not need
manual virtualenv setup.

From the repo root:

```bash
scripts/smoke_dev.sh
```

Start every configured mock service plus devhub:

```bash
scripts/dev.sh
```

Start only services declared by an example task:

```bash
scripts/dev.sh task gdrive-archive-stale-drafts
```

### Validation matrix

Pick the narrowest checks that cover your change.

Launcher, control script, devhub, or seed routing:

```bash
scripts/smoke_dev.sh
```

One environment package:

```bash
cd packages/environments/mock-gdrive
uv run --extra dev pytest tests -q
```

API response-shape or golden-fixture work:

```bash
cd packages/environments/mock-gdrive
uv run --extra dev pytest tests/test_conformance.py -q
```

Docker base image or example task image changes:

```bash
docker/build-base.sh
PULL_BASE=0 scripts/smoke_docker_examples.sh
```

Copied BenchFlow task packages under `tasks/`:

```bash
for task in tasks/*; do
  [ -d "$task" ] || continue
  [ "$(basename "$task")" = "_manifests" ] && continue
  bench tasks check "$task" --level structural
done
```

These checks require the BenchFlow CLI and validate copied task packages
structurally only.

End-to-end evaluation of copied downstream task packages may also require the
upstream `ghcr.io/benchflow-ai/env-0-base:latest` image because those packages
preserve their source-runner contract. New env0 example-task Dockerfiles should
instead use `ghcr.io/benchflow-ai/env0:<VERSION>`.

### Pull request checklist

Before opening a PR:

- Run the validation command that matches your change.
- Update docs when changing seed, Docker, API, or devhub contracts.
- Add conformance coverage for committed real API fixtures.
- Keep unrelated refactors out of the PR.
- Make sure new commands in docs have been run or clearly state their
  preconditions.

In the PR body, include:

- What changed.
- Why it changed.
- The validation commands and results.
- Any credentials, image-publish permissions, or provider access that were
  intentionally not available.

## Questions, Conduct, And Security

- Questions or ideas? Ask in the
  [BenchFlow Discord](https://discord.gg/G9dg3EfSva) — the same server where
  BenchBot lives.
- All community spaces follow the
  [Code of Conduct](CODE_OF_CONDUCT.md).
- Report vulnerabilities privately per the [security policy](SECURITY.md),
  not in public issues.
