---
schema_version: '1.3'
task:
  name: env-0/gdoc-search-by-title
  description: Hey, I need you to find my sprint planning notes from Q1, specifically
    the ones from the March 3 planning session and the async follow-ups that came
    after.
  authors:
  - name: envdash
    email: envdash@example.com
  keywords:
  - gdoc
  - gdrive
metadata:
  author_name: envdash
  author_email: envdash@example.com
  tags:
  - gdoc
  - gdrive
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

Hey, I need you to find my sprint planning notes from Q1, specifically the ones from the March 3 planning session and the async follow-ups that came after. There should be two docs. Pull together all the action items from those two docs into a new doc called "Sprint Action Items". Just the action items, nothing else. No attendees, decisions, or meeting notes. Make sure you're only pulling from the actual planning session docs, not from old drafts, templates, retros, or other teams' notes.
