#!/usr/bin/env bash
set -euo pipefail

# Find the master reviews document
DOC_ID=$(gws drive files list --params '{"q": "name contains '\''Annual Performance Reviews 2025'\''"}' | python3 -c "
import sys, json
data = json.load(sys.stdin)
for f in data.get('files', []):
    if 'Annual Performance Reviews 2025' in f.get('name', ''):
        print(f['id'])
        break
")

# Get its content and parse out each person's section
SECTIONS=$(gws docs documents get --params "{\"documentId\": \"$DOC_ID\"}" | python3 -c "
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

sections = text.split('---')
people = {}
for section in sections:
    stripped = section.strip()
    if 'Employee: Alice Chen' in stripped:
        people['alice'] = stripped
    elif 'Employee: Bob Martinez' in stripped:
        people['bob'] = stripped
    elif 'Employee: Carol Wu' in stripped:
        people['carol'] = stripped

for key in ['alice', 'bob', 'carol']:
    print(people.get(key, ''))
    print('===SECTION_BREAK===')
")

# Create individual review documents
for PERSON in "Alice Chen" "Bob Martinez" "Carol Wu"; do
    PERSON_KEY=$(echo "$PERSON" | tr '[:upper:]' '[:lower:]' | cut -d' ' -f1)

    SECTION=$(echo "$SECTIONS" | python3 -c "
import sys
text = sys.stdin.read()
sections = text.split('===SECTION_BREAK===')
keys = ['alice', 'bob', 'carol']
idx = keys.index('$PERSON_KEY')
print(sections[idx].strip())
")

    NEW_DOC_ID=$(gws docs documents create --json "{\"title\": \"Performance Review - $PERSON\"}" | python3 -c "
import sys, json
print(json.load(sys.stdin)['documentId'])
")

    gws docs documents batchUpdate \
      --params "{\"documentId\": \"$NEW_DOC_ID\"}" \
      --json "$(python3 -c "
import json
text = '''$SECTION'''
print(json.dumps({
    'requests': [{'insertText': {'location': {'index': 1}, 'text': text}}]
}))
")"

    echo "Created Performance Review - $PERSON: $NEW_DOC_ID"
done

echo "Done. Created individual review documents."
