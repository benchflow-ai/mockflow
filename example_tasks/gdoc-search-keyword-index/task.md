---
schema_version: '1.3'
task:
  name: env0/gdoc-search-keyword-index
  description: I need to pull together an index of every document in my Drive that relates to budgeting.
  authors:
  - name: env0
    email: 'env0@example.com'
  keywords:
  - gdoc
  - gdrive
metadata:
  author_name: env0
  author_email: 'env0@example.com'
  tags:
  - gdoc
  - gdrive
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
    manifest: ../../tasks/_manifests/env-0.toml
  env0:
    services:
    - mock-gdrive
    - mock-gdoc
---

I need to pull together an index of every document in my Drive that relates to budgeting. Search through my files and create a new document called "Budget Documents Index" listing the title of each document that discusses budgets. Include a one-line summary of what each document covers so I can quickly scan the list without opening every file.

Be thorough, some of these documents might not have "budget" in the title, so you may need to look at the contents. But don't include documents that just happen to mention money or costs in passing if they aren't actually about budgeting.
