---
schema_version: '1.3'
task:
  name: env-0/slack-extract-reaction-leaderboard
  description: 'Hey, could you pull together a quick "reaction leaderboard" for #general
    and share it in #random?'
  authors:
  - name: jack
    email: jkaisun1@gmail.com
  keywords:
  - slack
metadata:
  author_name: jack
  author_email: jkaisun1@gmail.com
  tags:
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
    - mock-slack
---

## prompt

Hey, could you pull together a quick "reaction leaderboard" for #general and share it in #random? I want to see which messages are getting the most love from actual people on the team.

Top 3 is fine, just make sure you're counting total reactions from real people accurately (a person can react with multiple different emoji on the same message, and each one counts, but don't count bots). Include the reaction count and enough of the message text so people know which post you're talking about.

Oh, and toss a trophy emoji on the winning message in #general while you're at it.
