#!/usr/bin/env bash
set -euo pipefail

# Search for Q1 sprint planning docs
PLANNING_DOCS=$(gws drive files list --params '{"q": "name contains '\''Q1 Sprint Planning'\''"}')

# Extract the main planning notes doc ID (exact match, not draft/archive/platform/retro)
DOC_ID=$(echo "$PLANNING_DOCS" | python3 -c "
import sys, json
data = json.load(sys.stdin)
for f in data.get('files', []):
    name = f.get('name', '')
    if name == 'Q1 Sprint Planning Notes':
        print(f['id'])
        break
")

# Extract the follow-up doc ID
FOLLOWUP_ID=$(echo "$PLANNING_DOCS" | python3 -c "
import sys, json
data = json.load(sys.stdin)
for f in data.get('files', []):
    name = f.get('name', '')
    if 'Follow-up' in name or 'Followup' in name or 'Async' in name:
        # Make sure it's not a retro or platform team doc
        if 'Retro' not in name and 'Platform' not in name:
            print(f['id'])
            break
")

# Get content from the main planning doc
ITEMS1=$(gws docs documents get --params "{\"documentId\": \"$DOC_ID\"}" | python3 -c "
import sys, json
def extract(body):
    parts = []
    for el in body.get('content', []):
        p = el.get('paragraph')
        if not p: continue
        for pe in p.get('elements', []):
            tr = pe.get('textRun')
            if tr: parts.append(tr.get('content', ''))
    return ''.join(parts)

data = json.load(sys.stdin)
text = extract(data.get('body', {}))
in_actions = False
items = []
for line in text.split('\n'):
    if 'Action Items' in line:
        in_actions = True
        continue
    if in_actions and line.strip().startswith('- ['):
        items.append(line.strip()[5:])
    elif in_actions and line.strip() and not line.strip().startswith('-'):
        break
print('\n'.join(items))
")

# Get content from the follow-up doc
ITEMS2=$(gws docs documents get --params "{\"documentId\": \"$FOLLOWUP_ID\"}" | python3 -c "
import sys, json
def extract(body):
    parts = []
    for el in body.get('content', []):
        p = el.get('paragraph')
        if not p: continue
        for pe in p.get('elements', []):
            tr = pe.get('textRun')
            if tr: parts.append(tr.get('content', ''))
    return ''.join(parts)

data = json.load(sys.stdin)
text = extract(data.get('body', {}))
in_actions = False
items = []
for line in text.split('\n'):
    if 'Action Items' in line:
        in_actions = True
        continue
    if in_actions and line.strip().startswith('- ['):
        items.append(line.strip()[5:])
    elif in_actions and line.strip() and not line.strip().startswith('-'):
        break
print('\n'.join(items))
")

# Create the new document
NEW_DOC_ID=$(gws docs documents create --json '{"title": "Sprint Action Items"}' | python3 -c "
import sys, json
print(json.load(sys.stdin)['documentId'])
")

# Combine and insert all action items
ALL_ITEMS="Sprint Action Items\n\n$ITEMS1\n$ITEMS2"
gws docs documents batchUpdate \
  --params "{\"documentId\": \"$NEW_DOC_ID\"}" \
  --json "$(python3 -c "
import json
text = '''$ALL_ITEMS'''
print(json.dumps({
    'requests': [{'insertText': {'location': {'index': 1}, 'text': text}}]
}))
")"

echo "Done. Created Sprint Action Items doc: $NEW_DOC_ID"
