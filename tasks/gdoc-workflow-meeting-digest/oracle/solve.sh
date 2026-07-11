#!/usr/bin/env bash
set -euo pipefail

# Find all Weekly Standup documents
STANDUP_DATA=$(gws drive files list --params '{"q": "name contains '\''Weekly Standup'\''", "pageSize": 100}' | python3 -c "
import sys, json
data = json.load(sys.stdin)
import re
def date_key(f):
    m = re.search(r'March\s+(\d+)', f.get('name', ''))
    return int(m.group(1)) if m else 0
for f in sorted(data.get('files', []), key=date_key):
    print(f['id'] + '|' + f['name'])
")

DIGEST_BODY="March 2026 Standup Digest\n\n"

while IFS='|' read -r DOC_ID DOC_NAME; do
    [ -z "$DOC_ID" ] && continue

    CONTENT=$(gws docs documents get --params "{\"documentId\": \"$DOC_ID\"}" | python3 -c "
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

highlights = []
blockers = []
section = None
for line in text.split('\n'):
    stripped = line.strip()
    if stripped.lower().startswith('highlights'):
        section = 'highlights'
        continue
    elif stripped.lower().startswith('blockers'):
        section = 'blockers'
        continue
    elif stripped and not stripped.startswith('-') and section:
        section = None
    if section == 'highlights' and stripped.startswith('-'):
        highlights.append(stripped)
    elif section == 'blockers' and stripped.startswith('-'):
        blockers.append(stripped)

print('HIGHLIGHTS:')
for h in highlights:
    print(h)
print('BLOCKERS:')
for b in blockers:
    print(b)
")

    DIGEST_BODY+="$DOC_NAME\n\n"
    DIGEST_BODY+="$CONTENT\n\n"
done <<< "$STANDUP_DATA"

# Create the digest document
NEW_DOC_ID=$(gws docs documents create --json '{"title": "March 2026 Standup Digest"}' | python3 -c "
import sys, json
print(json.load(sys.stdin)['documentId'])
")

# Insert digest content
gws docs documents batchUpdate \
  --params "{\"documentId\": \"$NEW_DOC_ID\"}" \
  --json "$(python3 -c "
import json, sys
text = '''$DIGEST_BODY'''
print(json.dumps({
    'requests': [{'insertText': {'location': {'index': 1}, 'text': text}}]
}))
")"

echo "Done. Created March 2026 Standup Digest: $NEW_DOC_ID"
