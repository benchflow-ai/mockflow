#!/usr/bin/env bash
set -euo pipefail

ALL_FILES=$(gws drive files list --params '{"pageSize": 1000}')

DOC_IDS_AND_TITLES=$(echo "$ALL_FILES" | python3 -c "
import sys, json, re
data = json.load(sys.stdin)
pattern = re.compile(r'(Untitled|Draft|Copy of)', re.IGNORECASE)
FOLDER_MIME = 'application/vnd.google-apps.folder'
for f in data.get('files', []):
    if f.get('mimeType') == FOLDER_MIME:
        continue
    name = f.get('name', '')
    if pattern.search(name):
        print(f['id'] + '\t' + name)
")

while IFS=$'\t' read -r DOC_ID DOC_TITLE; do
    [ -z "$DOC_ID" ] && continue

    DOC_JSON=$(gws docs documents get --params "{\"documentId\": \"$DOC_ID\"}" 2>/dev/null || true)
    if [ -z "$DOC_JSON" ]; then
        # Doc not found in Docs API — skip it (could be a non-Docs type)
        SENTENCE_COUNT=0
    else
        SENTENCE_COUNT=$(echo "$DOC_JSON" | python3 -c "
import sys, json, re
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
if 'error' in data:
    print(0)
else:
    text = extract(data.get('body', {})).strip()
    sentences = [s.strip() for s in re.split(r'[.!?]+', text) if len(s.strip()) > 10]
    print(len(sentences))
")
    fi

    if [ "$SENTENCE_COUNT" -lt 2 ]; then
        gws drive files delete --params "{\"fileId\": \"$DOC_ID\"}"
        echo "Deleted: $DOC_TITLE (sentences: $SENTENCE_COUNT)"
    else
        echo "Kept: $DOC_TITLE (sentences: $SENTENCE_COUNT, substantial content)"
    fi
done <<< "$DOC_IDS_AND_TITLES"

echo "Done. Cleanup complete."
