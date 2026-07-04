#!/usr/bin/env bash
set -euo pipefail

DOCS="${DOCS_URL:-http://localhost:9004}"
DRIVE="${DRIVE_URL:-http://localhost:9005}"
SLACK="${SLACK_URL:-http://localhost:9002}"
LOGS_DIR="${LOGS_DIR:-/logs/verifier}"
DOC_ID="1ApiRateLimitingPolicySpec000000000000000000"
mkdir -p "$LOGS_DIR"

curl -s "$DOCS/_admin/state" > /tmp/final_state.json
curl -s "$DOCS/_admin/diff" > /tmp/docs_diff.json

# Agents may create comments via the Docs API (port 9004) or the
# Drive comments API (port 9005).  Fetch from both and merge.
curl -s "$DRIVE/drive/v3/files/${DOC_ID}/comments" > /tmp/drive_comments.json 2>/dev/null || echo '{"comments":[]}' > /tmp/drive_comments.json

python3 -c "
import json

docs_diff = json.load(open('/tmp/docs_diff.json'))
drive_comments_resp = json.load(open('/tmp/drive_comments.json'))
drive_comments = drive_comments_resp.get('comments', [])

# Convert drive comments to the same shape as gdoc diff comments
drive_added = []
for c in drive_comments:
    drive_added.append({
        'id': c.get('commentId', c.get('id', '')),
        'documentId': '${DOC_ID}',
        'content': c.get('content', ''),
        'resolved': c.get('resolved', False),
        'quotedText': c.get('quotedFileContent', {}).get('value', '') if isinstance(c.get('quotedFileContent'), dict) else '',
        'authorId': c.get('author', {}).get('emailAddress', 'agent'),
        'replies': [],
        'createdTime': c.get('createdTime', ''),
        'modifiedTime': c.get('modifiedTime', ''),
    })

# Merge drive comments into docs diff
merged = docs_diff
for uid, udata in merged.get('updated', {}).items():
    udata.setdefault('comments', {'added': [], 'updated': [], 'deleted': []})
    udata['comments']['added'].extend(drive_added)

# If no user entries in updated but we have drive comments, add a synthetic entry
if drive_added and not merged.get('updated', {}):
    merged.setdefault('updated', {})
    merged['updated']['agent'] = {
        'documents': {'added': [], 'updated': [], 'deleted': []},
        'comments': {'added': drive_added, 'updated': [], 'deleted': []},
    }

json.dump(merged, open('/tmp/diff.json', 'w'))
"

# Merge action logs from all services
curl -s "$DOCS/_admin/action_log" > /tmp/docs_action_log.json
curl -s "$DRIVE/_admin/action_log" > /tmp/drive_action_log.json
curl -s "$SLACK/_admin/action_log" > /tmp/slack_action_log.json
python3 -c "
import json
docs = json.load(open('/tmp/docs_action_log.json'))
drive = json.load(open('/tmp/drive_action_log.json'))
slack = json.load(open('/tmp/slack_action_log.json'))
docs_entries = docs.get('entries', docs) if isinstance(docs, dict) else docs
drive_entries = drive.get('entries', drive) if isinstance(drive, dict) else drive
slack_entries = slack.get('entries', slack) if isinstance(slack, dict) else slack
merged = {'entries': docs_entries + drive_entries + slack_entries}
json.dump(merged, open('/tmp/action_log.json', 'w'))
"

python3 "$(dirname "$0")/evaluate.py" \
  --state /tmp/final_state.json \
  --diff /tmp/diff.json \
  --action-log /tmp/action_log.json \
  --output "$LOGS_DIR/reward.json"

cat "$LOGS_DIR/reward.json"
