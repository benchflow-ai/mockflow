---
schema_version: '1.3'
task:
  name: env-0/slack-channel-reorg
  description: We're shutting down the Metaverse department.
  authors:
  - name: envdash
    email: envdash@example.com
  keywords:
  - slack
metadata:
  author_name: envdash
  author_email: envdash@example.com
  tags:
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
    - mock-slack
---

## prompt

We're shutting down the Metaverse department. :( We want to try placing people internally before anything else.

Create these hiring pool channels: platform-team-hiring, aiml-team-hiring, commerce-team-hiring, infra-team-hiring, product-team-hiring.

Go through the metaverse channels, check each member's profile, and add them to whichever hiring pool fits best. One channel per person max - some people might not match anywhere, that's fine.

DM everyone to let them know what's happening. If they got matched, tell them which channel. If not, just wish them well.
