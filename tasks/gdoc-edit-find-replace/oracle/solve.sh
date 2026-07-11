#!/usr/bin/env bash
set -euo pipefail

DOC_IDS=$(gws drive files list --params '{"q": "fullText contains '\''Nexus AI'\''", "pageSize": 100}' | python3 -c "
import sys, json
data = json.load(sys.stdin)
for f in data.get('files', []):
    print(f['id'])
")

for DOC_ID in $DOC_IDS; do
    gws docs documents batchUpdate \
      --params "{\"documentId\": \"$DOC_ID\"}" \
      --json '{
        "requests": [{
          "replaceAllText": {
            "containsText": {"text": "Nexus AI", "matchCase": true},
            "replaceText": "Meridian Labs"
          }
        }]
      }'
    echo "Replaced in doc: $DOC_ID"
done

echo "Done. All occurrences of Nexus AI replaced with Meridian Labs."
