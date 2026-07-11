---
schema_version: '1.3'
task:
  name: env-0/gcal-ietf-interim-cancelled-sessions
  description: I imported a bunch of IETF interim sessions from the datatracker, but
    some have since been cancelled.
  authors:
  - name: Bingran You
    email: bingran.you@berkeley.edu
  keywords:
  - gcal
metadata:
  author_name: Bingran You
  author_email: bingran.you@berkeley.edu
  tags:
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
    - mock-gcal
---

## prompt

I imported a bunch of IETF interim sessions from the datatracker, but some have since been cancelled. Delete these cancelled sessions:

•	cbor - Concise Binary Object Representation Maintenance and Extensions
2024-10-02 14:00–15:00 UTC

•	moq - Media Over QUIC
2025-01-08 17:00–18:00 UTC

•	idr - Inter-Domain Routing
2024-06-24 14:00–17:00 UTC

•	core - Constrained RESTful Environments
2026-02-25 15:00–16:30 UTC

Don't touch any other events on the calendar.
