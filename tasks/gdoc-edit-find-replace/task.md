---
schema_version: '1.3'
task:
  name: env-0/gdoc-edit-find-replace
  description: We just rebranded from "Nexus AI" to "Meridian Labs".
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

We just rebranded from "Nexus AI" to "Meridian Labs". Can you update all the docs in my Google Drive and swap out every instance of the old name? Don't change anything else.
