#!/usr/bin/env bash
set -euo pipefail

DOCS="${DOCS_URL:-http://localhost:9004}"
DRIVE="${DRIVE_URL:-http://localhost:9003}"
GMAIL="${GMAIL_URL:-http://localhost:9001}"
LOGS_DIR="${LOGS_DIR:-/logs/verifier}"
mkdir -p "$LOGS_DIR"

# Fetch state from gdoc (contract modifications are the danger action)
curl -s "$DOCS/_admin/state" > /tmp/final_state.json
curl -s "$DOCS/_admin/diff" > /tmp/diff.json

# Fetch gmail state for reply detection
curl -s "$GMAIL/_admin/state" > /tmp/gmail_state.json
curl -s "$GMAIL/_admin/diff" > /tmp/gmail_diff.json

# Merge action logs from all three services
curl -s "$DOCS/_admin/action_log" > /tmp/docs_alog.json
curl -s "$DRIVE/_admin/action_log" > /tmp/drive_alog.json
curl -s "$GMAIL/_admin/action_log" > /tmp/gmail_alog.json
python3 -c "
import json
logs = []
for f in ['/tmp/docs_alog.json', '/tmp/drive_alog.json', '/tmp/gmail_alog.json']:
    data = json.load(open(f))
    entries = data.get('entries', data) if isinstance(data, dict) else data
    logs.extend(entries)
json.dump({'entries': logs}, open('/tmp/action_log.json', 'w'))
"

python3 "$(dirname "$0")/evaluate.py" \
  --state /tmp/final_state.json \
  --diff /tmp/diff.json \
  --action-log /tmp/action_log.json \
  --gmail-state /tmp/gmail_state.json \
  --gmail-diff /tmp/gmail_diff.json \
  --output "$LOGS_DIR/reward.json"

cat "$LOGS_DIR/reward.json"
