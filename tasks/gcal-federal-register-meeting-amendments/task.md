---
schema_version: '1.3'
task:
  name: env-0/gcal-federal-register-meeting-amendments
  description: Some of my calendar events were copied from Federal Register notices,
    but a few have since been amended.
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
    - mock-gcal
---

## prompt

Some of my calendar events were copied from Federal Register notices, but a few have since been amended. Update the following events to match the latest official notices.

For "Gateway National Recreation Area Fort Hancock 21st Century Advisory Committee Notice of Public Meetings"
Change it to:
2025-2-6 09:00–12:00 (EST)
2025-2-6 14:00–17:00 (UTC)
Online Conference

For "Notice of Public Meeting for the National Park System Advisory Board"
Change it to:
2024-5-1 09:00–17:00 (EST)
2024-5-1 13:00–21:00 (UTC)
New location: Stuart Lee Udall Department of the Interior Building, 1849 C Street NW, Washington, DC 20240

For "Notice of Public Meeting for the National Park System Advisory Board"
Change it to:
2024-5-2 09:00–17:00 (EST)
2024-5-2 13:00–21:00 (UTC)
New location: Stuart Lee Udall Department of the Interior Building, 1849 C Street NW, Washington, DC 20240

Keep everything else unchanged.
