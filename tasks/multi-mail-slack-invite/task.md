---
schema_version: '1.3'
task:
  name: env-0/multi-mail-slack-invite
  description: We recently launched an open-source project called SkillsBench and
    it’s gotten a lot of traction.
  authors:
  - name: envdash
    email: envdash@example.com
  keywords:
  - gmail
  - slack
metadata:
  author_name: envdash
  author_email: envdash@example.com
  tags:
  - gmail
  - slack
agent:
  timeout_sec: 600
verifier:
  timeout_sec: 120
sandbox:
  cpus: 1
  memory_mb: 2048
  network_mode: public
  build_timeout_sec: 600
  os: linux
  storage_mb: 10240
  gpus: 0
  mcp_servers: []
  env: {}
benchflow:
  environment:
    manifest: ../_manifests/env-0.toml
  env0:
    services:
    - mock-gmail
    - mock-slack
---

## prompt

We recently launched an open-source project called SkillsBench and it’s gotten a lot of traction. Contributors have been emailing their task submissions -- check my inbox for those.

They’re already in our Slack workspace. I want to organize them into difficulty channels based on estimated completion times. Create three public channels: skillsbench_task_easy for quick tasks (under a couple hours or so), skillsbench_task_medium for moderate ones, and skillsbench_task_hard for tasks that would take most of a day or more. If someone submitted tasks at different difficulty levels, put them in each relevant channel.
