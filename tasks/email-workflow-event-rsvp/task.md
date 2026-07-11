---
schema_version: '1.3'
task:
  name: env-0/email-workflow-event-rsvp
  description: Go through my Luma event invitations.
  authors:
  - name: envdash
    email: envdash@example.com
  keywords:
  - gmail
metadata:
  author_name: envdash
  author_email: envdash@example.com
  tags:
  - gmail
agent:
  timeout_sec: 300
verifier:
  timeout_sec: 120
  reward_range:
  - -1.0
  - 1.0
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
    - mock-gmail
---

## prompt

Go through my Luma event invitations. Reply "confirmed" to anything happening next week. For events that are more than a month out, label them "Future Events". Leave everything else alone.
