#!/usr/bin/env bash
set -euo pipefail

GCAL="${MOCK_GCAL_URL:-http://localhost:9002}"
GMAIL="${MOCK_GMAIL_URL:-http://localhost:9001}"
LOGS_DIR="${LOGS_DIR:-/logs/verifier}"
mkdir -p "$LOGS_DIR"

# GCal state
curl -s "$GCAL/_admin/state"      > /tmp/gcal_state.json
curl -s "$GCAL/_admin/diff"       > /tmp/gcal_diff.json
curl -s "$GCAL/_admin/action_log" > /tmp/gcal_action_log.json

# Gmail state (for safety gate — sent message checks)
curl -s "$GMAIL/_admin/state"      > /tmp/gmail_state.json
curl -s "$GMAIL/_admin/diff"       > /tmp/gmail_diff.json
curl -s "$GMAIL/_admin/action_log" > /tmp/gmail_action_log.json

python3 "$(dirname "$0")/evaluate.py" \
  --gcal-state /tmp/gcal_state.json \
  --gcal-diff /tmp/gcal_diff.json \
  --gcal-action-log /tmp/gcal_action_log.json \
  --gmail-state /tmp/gmail_state.json \
  --gmail-diff /tmp/gmail_diff.json \
  --gmail-action-log /tmp/gmail_action_log.json \
  --output "$LOGS_DIR/reward.json"

cat "$LOGS_DIR/reward.json"
