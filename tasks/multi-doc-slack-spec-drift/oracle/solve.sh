#!/usr/bin/env bash
set -euo pipefail

# Oracle solution for multi-doc-slack-spec-drift
# 1. Find the spec doc via Drive
# 2. Read doc content via Docs
# 3. Read Slack #backend history
# 4. Add comments for each drift

DOCS="${DOCS_URL:-http://localhost:9004}"
DRIVE="${DRIVE_URL:-http://localhost:9005}"
SLACK="${SLACK_URL:-http://localhost:9002}"

python3 << 'PYEOF'
import json
import subprocess
import os
import sys
import urllib.request

DOCS = os.environ.get("DOCS_URL", "http://localhost:9004")
DRIVE = os.environ.get("DRIVE_URL", "http://localhost:9005")
SLACK = os.environ.get("SLACK_URL", "http://localhost:9002")

def gws(*args):
    """Run a gws command and return parsed JSON."""
    result = subprocess.run(["gws"] + list(args), capture_output=True, text=True)
    if result.returncode != 0:
        print(f"gws error: {result.stderr}", file=sys.stderr)
    return json.loads(result.stdout) if result.stdout.strip() else {}

def slack_get(path):
    """GET request to Slack mock API."""
    url = f"{SLACK}{path}"
    req = urllib.request.Request(url, headers={"Authorization": "Bearer mock-bot-token"})
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())

def docs_post(path, body):
    """POST request to Docs mock API."""
    url = f"{DOCS}{path}"
    data = json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())

# Step 1: Find the API Rate Limiting Policy doc via Drive search
files_resp = gws("drive", "files", "list", "--params",
                  json.dumps({"q": "name contains 'Rate Limiting'", "pageSize": 50}))

doc_id = None
for f in files_resp.get("files", []):
    if "Rate Limiting" in f.get("name", ""):
        doc_id = f["id"]
        break

if not doc_id:
    print("ERROR: Could not find API Rate Limiting Policy doc", file=sys.stderr)
    sys.exit(1)

print(f"Found doc: {doc_id}", file=sys.stderr)

# Step 2: Read doc content
doc = gws("docs", "documents", "get", "--params",
           json.dumps({"documentId": doc_id}))
print(f"Doc title: {doc.get('title', 'N/A')}", file=sys.stderr)

# Step 3: Read Slack #backend history
channels_resp = slack_get("/api/conversations.list?types=public_channel")
backend_id = None
for ch in channels_resp.get("channels", []):
    if ch.get("name") == "backend":
        backend_id = ch["id"]
        break

if not backend_id:
    print("ERROR: Could not find #backend channel", file=sys.stderr)
    sys.exit(1)

history = slack_get(f"/api/conversations.history?channel={backend_id}&limit=100")
messages = history.get("messages", [])
print(f"Found {len(messages)} messages in #backend", file=sys.stderr)

# Step 4: Add comments for each identified drift
# Drift 1: Enterprise tier 1000 -> 2500
comment1 = docs_post(f"/v1/documents/{doc_id}/comments", {
    "content": (
        "Drift: Slack discussion (jordan, ~9 days ago) decided to bump the "
        "Enterprise tier rate limit from 1000 to 2500 requests/minute based on "
        "load test results and customer usage patterns. This doc still says 1000."
    ),
    "quotedText": "Enterprise: 1000 requests/minute",
})
print(f"Comment 1 created: {comment1.get('id', 'N/A')}", file=sys.stderr)

# Drift 2: X-RateLimit-Reset -> Retry-After header
comment2 = docs_post(f"/v1/documents/{doc_id}/comments", {
    "content": (
        "Drift: Slack discussion (alice, ~6 days ago) decided to switch from "
        "X-RateLimit-Reset to the standard Retry-After header (RFC 7231). "
        "This doc still references X-RateLimit-Reset."
    ),
    "quotedText": "X-RateLimit-Reset: UTC epoch timestamp when the window resets",
})
print(f"Comment 2 created: {comment2.get('id', 'N/A')}", file=sys.stderr)

# Drift 3: Burst window 60s -> 10s
comment3 = docs_post(f"/v1/documents/{doc_id}/comments", {
    "content": (
        "Drift: Slack discussion (derek, ~3 days ago) changed the burst window "
        "from 60 seconds to 10 seconds for better abuse protection. "
        "This doc still says 60-second burst window."
    ),
    "quotedText": "60-second burst window",
})
print(f"Comment 3 created: {comment3.get('id', 'N/A')}", file=sys.stderr)

print("Done. Added 3 drift comments to the spec doc.", file=sys.stderr)
PYEOF
