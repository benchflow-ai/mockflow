---
schema_version: '1.3'
task:
  name: env-0/multi-rebalance-on-call-rotation
  description: Can you sort out the April on-call rotation?
  authors:
  - name: envdash
    email: envdash@example.com
  keywords:
  - gdoc
  - gdrive
  - gcal
  - slack
metadata:
  author_name: envdash
  author_email: envdash@example.com
  tags:
  - gdoc
  - gdrive
  - gcal
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
    - mock-gdrive
    - mock-gdoc
    - mock-gcal
    - mock-slack
---

## prompt

Can you sort out the April on-call rotation? I think there's a schedule doc somewhere in Drive. A few people have PTO that month so check the calendar, and look at #on-call-swap. I think some swaps were already discussed.

Make sure every week is covered and it's fair. Post the updated schedule to #on-call-swap when you're done.
