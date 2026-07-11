#!/usr/bin/env bash
set -euo pipefail

# Find all Aurora docs via Drive files.list
AURORA_DOCS=$(gws drive files list --params "{\"q\": \"name contains 'Aurora'\", \"pageSize\": 100}" | python3 -c "
import sys, json
data = json.load(sys.stdin)
for f in data.get('files', []):
    if 'aurora' in f.get('name', '').lower():
        print(f['id'])
")

# Extract decisions and deadlines from each doc
SUMMARY=""
for DOC_ID in $AURORA_DOCS; do
    DOC_CONTENT=$(gws docs documents get --params "{\"documentId\": \"$DOC_ID\"}" | python3 -c "
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
title = data.get('title', '')
text = extract(data.get('body', {}))

# Extract sections
sections = {'decisions': [], 'deadlines': []}
current = None
for line in text.split('\n'):
    stripped = line.strip()
    if 'Key Decisions' in line or 'Decision' in line:
        current = 'decisions'
        continue
    elif 'Deadline' in line:
        current = 'deadlines'
        continue
    elif stripped and not stripped.startswith('-') and ':' not in stripped and current:
        current = None
    if current and stripped.startswith('-'):
        sections[current].append(stripped)

print(f'From: {title}')
if sections['decisions']:
    print('Decisions:')
    for d in sections['decisions']:
        print(f'  {d}')
if sections['deadlines']:
    print('Deadlines:')
    for d in sections['deadlines']:
        print(f'  {d}')
print()
")
    SUMMARY="$SUMMARY$DOC_CONTENT"
done

# Create summary doc
NEW_DOC_ID=$(gws docs documents create --json '{"title": "Project Aurora Summary"}' | python3 -c "
import sys, json
print(json.load(sys.stdin)['documentId'])
")

# Insert content
gws docs documents batchUpdate \
  --params "{\"documentId\": \"$NEW_DOC_ID\"}" \
  --json "$(python3 -c "
import json, sys
text = '''Project Aurora Summary

$SUMMARY'''
print(json.dumps({
    'requests': [{'insertText': {'location': {'index': 1}, 'text': text}}]
}))
")"

echo "Done. Created Project Aurora Summary: $NEW_DOC_ID"
