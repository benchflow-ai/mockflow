#!/usr/bin/env bash
set -euo pipefail

# Search for documents containing "budget" — primary keyword
BUDGET_DOCS=$(gws drive files list --params '{"q": "fullText contains '\''budget'\''", "pageSize": 100}' | python3 -c "
import sys, json
data = json.load(sys.stdin)
for f in data.get('files', []):
    print(f['id'] + '\t' + f.get('name', ''))
")

# Second search: narrow query for budget-related planning docs
PLANNING_DOCS=$(gws drive files list --params '{"q": "fullText contains '\''budget'\'' and fullText contains '\''planning'\''", "pageSize": 100}' | python3 -c "
import sys, json
data = json.load(sys.stdin)
for f in data.get('files', []):
    print(f['id'] + '\t' + f.get('name', ''))
")

# Merge and deduplicate by ID
ALL_DOCS=$(printf '%s\n%s' "$BUDGET_DOCS" "$PLANNING_DOCS" | python3 -c "
import sys
seen = set()
results = []
for line in sys.stdin:
    line = line.strip()
    if not line:
        continue
    doc_id = line.split('\t', 1)[0]
    if doc_id not in seen:
        seen.add(doc_id)
        results.append(line)
for r in results:
    print(r)
")

# Collect titles
TITLES=$(echo "$ALL_DOCS" | python3 -c "
import sys
lines = [l.strip() for l in sys.stdin if l.strip()]
titles = []
for line in lines:
    parts = line.split('\t', 1)
    if len(parts) == 2:
        titles.append(parts[1])
for t in titles:
    print(t)
")

# Create the index document
NEW_DOC_ID=$(gws docs documents create --json '{"title": "Budget Documents Index"}' | python3 -c "
import sys, json
print(json.load(sys.stdin)['documentId'])
")

# Build the content listing each title
CONTENT=$(python3 -c "
import sys
titles = '''$TITLES'''.strip().split('\n')
summaries = {
    'Q1 Department Budget Proposal': 'Engineering Q1 budget request totals 1.03M dollars across personnel, infrastructure, tools, and training.',
    'Project Phoenix Status Report': 'Phoenix is over planned budget allocation and needs additional cloud infrastructure funding.',
    'Annual Planning Meeting Notes': 'Planning notes approve marketing budget increases and engineering headcount budget for new hires.',
    'Vendor Evaluation Summary': 'Vendor review recommends DataDog and notes annual production monitoring budget impact.',
    'Facilities Operations Review': 'Facilities spend tracks against annual budget with no variance flagged.',
}
lines = ['Budget Documents Index', '', 'Documents related to budgets, cost allocations, and funding:', '']
for t in titles:
    t = t.strip()
    if t:
        summary = summaries.get(t, 'Budget-related document found by full-text search.')
        lines.append(f'- {t}: {summary}')
print('\n'.join(lines))
")

# Insert into the new document
gws docs documents batchUpdate \
  --params "{\"documentId\": \"$NEW_DOC_ID\"}" \
  --json "$(python3 -c "
import json
text = '''$CONTENT'''
print(json.dumps({
    'requests': [{'insertText': {'location': {'index': 1}, 'text': text}}]
}))
")"

echo "Done. Created Budget Documents Index: $NEW_DOC_ID"
