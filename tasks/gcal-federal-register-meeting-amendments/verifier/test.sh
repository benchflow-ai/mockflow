#!/usr/bin/env bash
set -euo pipefail

GCAL="${CALENDAR_URL:-http://localhost:9003}"
LOGS_DIR="${LOGS_DIR:-/logs/verifier}"
mkdir -p "$LOGS_DIR"

curl -s "$GCAL/_admin/state" > /tmp/gcal_state.json
curl -s "$GCAL/_admin/diff" > /tmp/gcal_diff.json
curl -s "$GCAL/_admin/action_log" > /tmp/gcal_action_log.json

python3 "$(dirname "$0")/evaluate.py" \
  --gcal-state /tmp/gcal_state.json \
  --gcal-diff /tmp/gcal_diff.json \
  --gcal-action-log /tmp/gcal_action_log.json \
  --output "$LOGS_DIR/reward.json"

cat "$LOGS_DIR/reward.json"
