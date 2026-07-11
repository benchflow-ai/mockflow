#!/usr/bin/env bash
set -euo pipefail

# Single Python script handles everything to avoid shell quoting issues
python3 << 'PYEOF'
import json
import subprocess
import re
import sys

def gws(*args):
    """Run a gws command and return parsed JSON."""
    result = subprocess.run(["gws"] + list(args), capture_output=True, text=True)
    if result.returncode != 0:
        print(f"gws error: {result.stderr}", file=sys.stderr)
    return json.loads(result.stdout) if result.stdout.strip() else {}

def extract_text(body):
    parts = []
    for el in body.get("content", []):
        p = el.get("paragraph")
        if not p:
            continue
        for pe in p.get("elements", []):
            tr = pe.get("textRun")
            if tr:
                parts.append(tr.get("content", ""))
    return "".join(parts)

# Step 1: Find all API docs via Drive
files_resp = gws("drive", "files", "list", "--params",
                  json.dumps({"q": "name contains 'API'", "pageSize": 100}))

api_docs = []
for f in files_resp.get("files", []):
    if "API" in f.get("name", ""):
        api_docs.append((f["id"], f["name"]))

print(f"Found {len(api_docs)} API docs", file=sys.stderr)

# Step 2: Extract changelog entries from each doc
all_entries = []
for doc_id, doc_name in api_docs:
    doc = gws("docs", "documents", "get", "--params",
              json.dumps({"documentId": doc_id}))
    text = extract_text(doc.get("body", {}))

    in_changelog = False
    for line in text.split("\n"):
        stripped = line.strip()
        lower = stripped.lower()
        if lower.startswith("changelog") or lower.startswith("changes"):
            in_changelog = True
            continue
        if in_changelog:
            if stripped.startswith("- "):
                all_entries.append(f"{stripped} [{doc_name}]")
            elif stripped and not stripped.startswith("-"):
                in_changelog = False

print(f"Found {len(all_entries)} changelog entries", file=sys.stderr)

# Step 3: Sort by date (newest first)
def sort_key(line):
    m = re.search(r"(\d{4}-\d{2}-\d{2})", line)
    return m.group(1) if m else "0000-00-00"

all_entries.sort(key=sort_key, reverse=True)

# Step 4: Create the unified changelog document
create_resp = gws("docs", "documents", "create", "--json",
                   json.dumps({"title": "API Changelog"}))
new_doc_id = create_resp["documentId"]
print(f"Created doc: {new_doc_id}", file=sys.stderr)

# Step 5: Insert sorted changelog content
body_text = "API Changelog\n\nUnified changelog from all API documentation, sorted by date (newest first).\n\n"
body_text += "\n".join(all_entries) + "\n"

update_resp = gws("docs", "documents", "batchUpdate",
                   "--params", json.dumps({"documentId": new_doc_id}),
                   "--json", json.dumps({
                       "requests": [{"insertText": {"location": {"index": 1}, "text": body_text}}]
                   }))
print(json.dumps(update_resp, indent=2))
print(f"Done. Created API Changelog: {new_doc_id}")
PYEOF
