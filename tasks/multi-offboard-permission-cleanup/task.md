---
schema_version: '1.3'
task:
  name: env-0/multi-offboard-permission-cleanup
  description: Someone flagged that the Q2 Strategy Deck in Leadership might still
    be shared with people who should not have access.
  authors:
  - name: envdash
    email: envdash@example.com
  keywords:
  - gdrive
  - slack
metadata:
  author_name: envdash
  author_email: envdash@example.com
  tags:
  - gdrive
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
    - mock-gdrive
    - mock-gdoc
---

## prompt

Someone flagged that the Q2 Strategy Deck in Leadership might still be shared with people who should not have access. I know there are a few external collaborators on it for legitimate reasons, so please do not just remove everyone. Check the recent messages in #it-ops on Slack for context on who should and should not have access, then clean up only what needs to be cleaned up.
