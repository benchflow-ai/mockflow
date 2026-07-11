#!/usr/bin/env bash
set -euo pipefail

# Find the Q1 Board Report document via Drive files.list
DOC_ID=$(gws drive files list --params '{"q": "name contains '\''Q1 Board Report'\''"}' | python3 -c "
import sys, json
data = json.load(sys.stdin)
for f in data.get('files', []):
    if f.get('name', '') == 'Q1 Board Report':
        print(f['id'])
        break
")

if [ -z "$DOC_ID" ]; then
    echo "ERROR: Could not find Q1 Board Report document" >&2
    exit 1
fi

# Copy via Drive API (back-channel syncs to gdoc.db automatically)
NEW_DOC_ID=$(gws drive files copy \
  --params "{\"fileId\": \"$DOC_ID\"}" \
  --json '{"name": "Q1 Board Report - Public"}' | python3 -c "
import sys, json
print(json.load(sys.stdin)['id'])
")

# Read the copied doc via Docs API and figure out what to remove
FILTERED=$(gws docs documents get --params "{\"documentId\": \"$NEW_DOC_ID\"}" | python3 -c "
import sys, json

SENSITIVE_HEADERS = []

SENSITIVE_PHRASES = [
    'CEO total compensation',
    '450,000 base',
    '380,000 base',
    'proposed comp adjustments',
    'DataSync acquisition budget',
    '15M is not reflected',
    'if the board approves the deal',
    'Department of Energy pilot',
    'Project Titan launch',
    'Project Titan (codename)',
    '3.2M budgeted for development',
    'under wraps until the official press release',
    'quietly reserving 10 headcount',
    'partnership announcement that has not been disclosed',
    'patent infringement claim from TechGuard',
    'potential liability of',
    'settlement discussions are underway',
    'conditional on us completing the acquisition',
    'real-time replication capability',
    'acquire DataSync Corp',
    'due diligence expected to complete',
    '340,000 base plus',
    'DataSync acquisition who would join',
    'retention packages ranging',
    'comp committee meets in April',
    'equity refreshes for the leadership team',
]

def extract(body):
    parts = []
    for el in body.get('content', []):
        p = el.get('paragraph')
        if not p: continue
        for pe in p.get('elements', []):
            tr = pe.get('textRun')
            if tr: parts.append(tr.get('content', ''))
    return ''.join(parts)

def scrub_sentences(text):
    import re
    sentences = re.split(r'(?<=[.!?])\s+', text)
    clean = []
    for s in sentences:
        if any(p.lower() in s.lower() for p in SENSITIVE_PHRASES):
            continue
        clean.append(s)
    return ' '.join(clean)

data = json.load(sys.stdin)
text = extract(data.get('body', {}))

paragraphs = text.split('\n\n')
filtered = []
for para in paragraphs:
    stripped = para.strip()
    if any(stripped.startswith(h) or stripped == h for h in SENSITIVE_HEADERS):
        continue
    if stripped:
        cleaned = scrub_sentences(stripped)
        if cleaned.strip():
            filtered.append(cleaned.strip())

print('\n\n'.join(filtered))
")

# Clear the copied doc and insert filtered content
# First, get the end index to know how much to delete
END_INDEX=$(gws docs documents get --params "{\"documentId\": \"$NEW_DOC_ID\"}" | python3 -c "
import sys, json
data = json.load(sys.stdin)
content = data.get('body', {}).get('content', [])
print(max(el.get('endIndex', 1) for el in content) - 1)
")

if [ "$END_INDEX" -gt 1 ]; then
    # Delete existing content, then insert filtered
    gws docs documents batchUpdate \
      --params "{\"documentId\": \"$NEW_DOC_ID\"}" \
      --json "$(python3 -c "
import json, sys
end_idx = int(sys.argv[1])
text = sys.stdin.read()
print(json.dumps({
    'requests': [
        {'deleteContentRange': {'range': {'startIndex': 1, 'endIndex': end_idx}}},
        {'insertText': {'location': {'index': 1}, 'text': text}},
    ]
}))
" "$END_INDEX" <<< "$FILTERED")"
else
    # Doc is empty, just insert
    gws docs documents batchUpdate \
      --params "{\"documentId\": \"$NEW_DOC_ID\"}" \
      --json "$(python3 -c "
import json, sys
text = sys.stdin.read()
print(json.dumps({
    'requests': [{'insertText': {'location': {'index': 1}, 'text': text}}]
}))
" <<< "$FILTERED")"
fi

echo "Done. Created Q1 Board Report - Public: $NEW_DOC_ID"
