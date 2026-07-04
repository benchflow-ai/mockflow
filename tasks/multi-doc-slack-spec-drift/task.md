---
schema_version: '1.3'
task:
  name: env-0/multi-doc-slack-spec-drift
  description: There's been a bunch of backend discussion in Slack lately and I have
    a feeling our rate limiting spec in Drive is out of date.
  authors:
  - name: envdash
    email: envdash@example.com
  keywords:
  - gdoc
  - slack
metadata:
  author_name: envdash
  author_email: envdash@example.com
  tags:
  - gdoc
  - slack
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
    - mock-slack
    - mock-gdrive
    - mock-gdoc
---

## prompt

There's been a bunch of backend discussion in Slack lately and I have a feeling our rate limiting spec in Drive is out of date. Can you check #backend and see if anything was decided that doesn't match what's in the doc? Just leave comments where things are off. Don't change the doc.
