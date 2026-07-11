#!/usr/bin/env bash
set -euo pipefail

GCAL="${CALENDAR_URL:-http://localhost:9002}"
SLACK="${SLACK_URL:-http://localhost:9005}"
LOGS_DIR="${LOGS_DIR:-/logs/verifier}"
mkdir -p "$LOGS_DIR"

# Fetch state from gcal (calendar event creation) and slack (notification)
curl -s "$GCAL/_admin/state"     > /tmp/gcal_state.json
curl -s "$GCAL/_admin/diff"      > /tmp/gcal_diff.json
curl -s "$SLACK/_admin/state"    > /tmp/slack_state.json
curl -s "$SLACK/_admin/diff"     > /tmp/slack_diff.json

# Merge action logs from both services
curl -s "$GCAL/_admin/action_log"  > /tmp/gcal_action_log.json
curl -s "$SLACK/_admin/action_log" > /tmp/slack_action_log.json

python3 -c "
import json
logs = []
for path in ['/tmp/gcal_action_log.json', '/tmp/slack_action_log.json']:
    data = json.load(open(path))
    entries = data.get('entries', data) if isinstance(data, dict) else data
    if isinstance(entries, list):
        logs.extend(entries)
json.dump({'entries': logs}, open('/tmp/action_log.json', 'w'))
"

python3 "$(dirname "$0")/evaluate.py" \
  --gcal-state /tmp/gcal_state.json \
  --gcal-diff /tmp/gcal_diff.json \
  --slack-state /tmp/slack_state.json \
  --slack-diff /tmp/slack_diff.json \
  --action-log /tmp/action_log.json \
  --output "$LOGS_DIR/reward.json"

cat "$LOGS_DIR/reward.json"
