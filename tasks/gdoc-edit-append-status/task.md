---
schema_version: '1.3'
task:
  name: env-0/gdoc-edit-append-status
  description: Can you do a quick check-in on my project docs?
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
  timeout_sec: 300
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

Can you do a quick check-in on my project docs? Go through my Google Docs, find the active projects, and add a short status note at the bottom of each one based on what's in the doc. Use March 19, 2026 as the date. Make it specific to each project - no generic filler.

Skip anything that's done or shelved.
