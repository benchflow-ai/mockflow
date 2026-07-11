#!/usr/bin/env bash
set -euo pipefail

AUTH="${AUTH_URL:-http://localhost:9000}"
GCAL="${CALENDAR_URL:-http://localhost:9002}"
DRIVE="${DRIVE_URL:-http://localhost:9003}"
GMAIL="${GMAIL_URL:-http://localhost:9001}"
LOGS_DIR="${LOGS_DIR:-/logs/verifier}"
mkdir -p "$LOGS_DIR"

curl -s "$AUTH/_admin/audit_log?limit=10000" > /tmp/auth_audit.json
curl -s "$AUTH/_admin/metrics" > /tmp/auth_metrics.json
curl -s "$GCAL/_admin/state" > /tmp/gcal_state.json
curl -s "$DRIVE/_admin/action_log" > /tmp/gdrive_action_log.json
curl -s "$GMAIL/_admin/state" > /tmp/gmail_state.json

python3 "$(dirname "$0")/evaluate.py" \
  --auth-audit /tmp/auth_audit.json \
  --auth-metrics /tmp/auth_metrics.json \
  --gcal-state /tmp/gcal_state.json \
  --gdrive-action-log /tmp/gdrive_action_log.json \
  --gmail-state /tmp/gmail_state.json \
  --output "$LOGS_DIR/reward.json"

cat "$LOGS_DIR/reward.json"
