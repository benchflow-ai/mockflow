#!/usr/bin/env bash
set -euo pipefail

DOCS="${DOCS_URL:-http://localhost:9004}"
DRIVE="${DRIVE_URL:-http://localhost:9003}"
GCAL="${CALENDAR_URL:-http://localhost:9002}"
SLACK="${SLACK_URL:-http://localhost:9005}"
LOGS_DIR="${LOGS_DIR:-/logs/verifier}"
mkdir -p "$LOGS_DIR"

# Fetch state from gdoc (schedule content) and slack (posted message)
curl -s "$DOCS/_admin/state"      > /tmp/docs_state.json
curl -s "$DOCS/_admin/diff"       > /tmp/docs_diff.json
curl -s "$SLACK/_admin/state"     > /tmp/slack_state.json
curl -s "$SLACK/_admin/diff"      > /tmp/slack_diff.json

# Merge action logs from all four services
curl -s "$DOCS/_admin/action_log"  > /tmp/docs_action_log.json
curl -s "$DRIVE/_admin/action_log" > /tmp/drive_action_log.json
curl -s "$GCAL/_admin/action_log"  > /tmp/gcal_action_log.json
curl -s "$SLACK/_admin/action_log" > /tmp/slack_action_log.json

python3 -c "
import json
logs = []
for path in ['/tmp/docs_action_log.json', '/tmp/drive_action_log.json',
             '/tmp/gcal_action_log.json', '/tmp/slack_action_log.json']:
    data = json.load(open(path))
    entries = data.get('entries', data) if isinstance(data, dict) else data
    if isinstance(entries, list):
        logs.extend(entries)
json.dump({'entries': logs}, open('/tmp/action_log.json', 'w'))
"

python3 "$(dirname "$0")/evaluate.py" \
  --docs-state /tmp/docs_state.json \
  --docs-diff /tmp/docs_diff.json \
  --slack-state /tmp/slack_state.json \
  --slack-diff /tmp/slack_diff.json \
  --action-log /tmp/action_log.json \
  --output "$LOGS_DIR/reward.json"

cat "$LOGS_DIR/reward.json"
