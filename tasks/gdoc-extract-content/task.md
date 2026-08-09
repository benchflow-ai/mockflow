---
schema_version: '1.3'
task:
  name: env-0/gdoc-extract-content
  description: I've got a bunch of Google Docs about Project Aurora spread across
    my Drive.
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
---

## prompt

I've got a bunch of Google Docs about Project Aurora spread across my Drive. Can you go through them and pull out the key decisions and deadlines into a single doc called "Project Aurora Summary"?
