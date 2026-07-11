#!/usr/bin/env bash
set -euo pipefail

# Search for all documents with "Project" in the title
PROJECT_DOCS=$(gws drive files list --params '{"q": "name contains '\''Project'\''", "pageSize": 100}')

# For each Project doc, read content, check if active, extract phase, append status block
echo "$PROJECT_DOCS" | python3 -c "
import sys, json
data = json.load(sys.stdin)
for f in data.get('files', []):
    if f.get('name', '').startswith('Project'):
        print(f['id'] + '|' + f['name'])
" | while IFS='|' read -r DOC_ID DOC_NAME; do
    # Get the document content
    DOC_DATA=$(gws docs documents get --params "{\"documentId\": \"$DOC_ID\"}")

    # Extract text and determine if active + extract phase
    RESULT=$(echo "$DOC_DATA" | python3 -c "
import sys, json

data = json.load(sys.stdin)
body = data.get('body', {})
content = body.get('content', [])
text_parts = []
for el in content:
    p = el.get('paragraph')
    if not p: continue
    for pe in p.get('elements', []):
        tr = pe.get('textRun')
        if tr: text_parts.append(tr.get('content', ''))
text = ''.join(text_parts).lower()

# Check for inactive signals
inactive_signals = ['archived', 'completed', 'cancelled', 'canceled', 'closed',
                    'on hold', 'paused', 'no longer active', 'indefinite hold']
is_inactive = any(signal in text for signal in inactive_signals)

if is_inactive:
    print('SKIP')
else:
    # Extract current phase/focus
    # Look for 'in progress' markers
    lines = ''.join(text_parts).split('\n')
    phase = ''
    for line in lines:
        if 'in progress' in line.lower():
            # Extract the phase description
            phase = line.strip().lstrip('- ').split('(')[0].strip()
            break
    if not phase:
        # Look for first objective or key activity
        in_section = False
        for line in lines:
            ll = line.lower().strip()
            if any(k in ll for k in ['objective:', 'goal:', 'proposed initiative']):
                phase = line.split(':', 1)[-1].strip() if ':' in line else line.strip()
                break
            if any(k in ll for k in ['key activities:', 'objectives:', 'milestones:']):
                in_section = True
                continue
            if in_section and line.strip().startswith('-'):
                phase = line.strip().lstrip('- ')
                break
    print(phase if phase else 'In progress')
")

    if [ "$RESULT" = "SKIP" ]; then
        echo "Skipping inactive doc: $DOC_NAME"
        continue
    fi

    PHASE="$RESULT"

    # Get the end index
    END_INDEX=$(echo "$DOC_DATA" | python3 -c "
import sys, json
data = json.load(sys.stdin)
body = data.get('body', {})
content = body.get('content', [])
if content:
    last = content[-1]
    print(last.get('endIndex', 1) - 1)
else:
    print(1)
")

    # Build the status block
    STATUS_TEXT=$(python3 -c "
name = '''$DOC_NAME'''
phase = '''$PHASE'''
# Extract project name from doc title
proj = name
for suffix in [' Overview', ' Design Doc', ' Proposal', ' Sprint Plan', ' Roadmap', ' Planning']:
    proj = proj.replace(suffix, '')
text = f'''

---
STATUS REVIEW — March 19, 2026
Project: {proj}
Current Phase: {phase}
Status: Active
---
'''
print(text)
")

    # Append the status update at the end
    gws docs documents batchUpdate \
      --params "{\"documentId\": \"$DOC_ID\"}" \
      --json "$(python3 -c "
import json
text = '''$STATUS_TEXT'''
print(json.dumps({
    'requests': [{'insertText': {'location': {'index': $END_INDEX}, 'text': text}}]
}))
")"

    echo "Updated document: $DOC_NAME (phase: $PHASE)"
done

echo "Done. Appended status updates to all active Project documents."
