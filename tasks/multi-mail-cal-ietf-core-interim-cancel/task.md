---
schema_version: '1.3'
task:
  name: env-0/multi-mail-cal-ietf-core-interim-cancel
  description: Check your recent Gmail emails and update your Google Calendar accordingly.
  authors:
  - name: Bingran You
    email: bingran.you@berkeley.edu
  keywords:
  - gmail
  - gcal
metadata:
  author_name: Bingran You
  author_email: bingran.you@berkeley.edu
  tags:
  - gmail
  - gcal
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
    - mock-gmail
    - mock-gcal
---

## prompt

Check your recent Gmail emails and update your Google Calendar accordingly. Some meetings may have been cancelled, so remove or cancel only those specific calendar events. Be careful not to touch events that are still confirmed. Do not create duplicate events, and only act on information already present in Gmail or Google Calendar.
