---
schema_version: '1.3'
task:
  name: env-0/gcal-fosdem-2023-amendments
  description: Some of my FOSDEM 2023 calendar entries need updating.
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

Some of my FOSDEM 2023 calendar entries need updating. They posted schedule amendments and five of my sessions got officially cancelled. Can you delete those? They all have "CANCELLED" in the title already, but heads up, I also have a "CANCELLED Network Performance in the Linux Kernel" event that wasn't part of this amendment batch, so leave that one alone.

The cancelled LLVM talk in AW1.120 got replaced with a new session about organizing LLVM socials/meetups. Same time slot, same room. Can you add that? Title it with "AMENDMENT" at the start like the other amended events. Use UTC times.

Don't touch anything else on the calendar.
