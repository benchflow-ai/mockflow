---
schema_version: '1.3'
task:
  name: env-0/slack-reaction-weekly-leaderboard
  description: Can you put together a weekly reaction leaderboard?
  authors:
  - name: jkaisun1
    email: jkaisun1@gmail.com
  keywords:
  - slack
metadata:
  author_name: jkaisun1
  author_email: jkaisun1@gmail.com
  tags:
  - slack
agent:
  timeout_sec: 300
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
    - mock-slack
---

## prompt

Can you put together a weekly reaction leaderboard? I’d like to know who got the most love on their messages across our public Slack channels this past week.

Post the top 3 to #general, and if the winner really crushed it, cross-post to #random so the whole company sees.
