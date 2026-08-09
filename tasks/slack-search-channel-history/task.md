---
schema_version: '1.3'
task:
  name: env-0/slack-search-channel-history
  description: 'Find the agreed-upon enterprise tier API rate limit from the product
    team''s recent discussion in #product-archive and post the answer in #general.'
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

Find the agreed-upon enterprise tier API rate limit from the product team's recent discussion in #product-archive and post the answer in #general.
Use this format: > The Enterprise API rate limit is **X requests/minute** (source: #product-archive)
