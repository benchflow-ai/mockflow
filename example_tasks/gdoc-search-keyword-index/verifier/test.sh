#!/usr/bin/env bash
# Fetch state/diff/action_log from the environment and run evaluate.py
set -euo pipefail

DOCS="${MOCK_GDOC_URL:-http://localhost:9004}"
DRIVE="${MOCK_GDRIVE_URL:-http://localhost:9003}"
LOGS_DIR="${LOGS_DIR:-/logs/verifier}"
mkdir -p "$LOGS_DIR"

curl -s "$DOCS/_admin/state" > /tmp/final_state.json
curl -s "$DOCS/_admin/diff" > /tmp/diff.json

# Merge action logs from both docs and drive services
curl -s "$DOCS/_admin/action_log" > /tmp/docs_action_log.json
curl -s "$DRIVE/_admin/action_log" > /tmp/drive_action_log.json
python3 -c "
import json, sys
docs = json.load(open('/tmp/docs_action_log.json'))
drive = json.load(open('/tmp/drive_action_log.json'))
docs_entries = docs.get('entries', docs) if isinstance(docs, dict) else docs
drive_entries = drive.get('entries', drive) if isinstance(drive, dict) else drive
merged = {'entries': docs_entries + drive_entries}
json.dump(merged, open('/tmp/action_log.json', 'w'))
"

python3 "$(dirname "$0")/evaluate.py" \
  --state /tmp/final_state.json \
  --diff /tmp/diff.json \
  --action-log /tmp/action_log.json \
  --output "$LOGS_DIR/reward.json"

cat "$LOGS_DIR/reward.json"
