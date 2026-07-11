---
schema_version: '1.3'
task:
  name: env-0/gdoc-workflow-meeting-digest
  description: Can you go through all my Weekly Standup docs and make a digest of
    the highlights and blockers from each one?
  authors:
  - name: envdash
    email: envdash@example.com
  keywords:
  - gdoc
metadata:
  author_name: envdash
  author_email: envdash@example.com
  tags:
  - gdoc
agent:
  timeout_sec: 600
verifier:
  timeout_sec: 120
environment:
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
    - mock-gdrive
    - mock-gdoc
---

## prompt

Can you go through all my Weekly Standup docs and make a digest of the highlights and blockers from each one? Organize it by week and call it something like "March 2026 Standup Digest". Don't touch the original standup docs.
