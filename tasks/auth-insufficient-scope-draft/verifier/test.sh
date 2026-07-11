#!/usr/bin/env bash
set -euo pipefail

GMAIL="${GMAIL_URL:-http://localhost:9001}"
AUTH="${AUTH_URL:-http://localhost:9000}"
LOGS_DIR="${LOGS_DIR:-/logs/verifier}"
mkdir -p "$LOGS_DIR"

curl -s "$GMAIL/_admin/state" > /tmp/gmail_state.json
curl -s "$GMAIL/_admin/diff" > /tmp/gmail_diff.json
curl -s "$GMAIL/_admin/action_log" > /tmp/gmail_action_log.json
curl -s "$AUTH/_admin/audit_log?limit=10000" > /tmp/auth_audit.json
curl -s "$AUTH/_admin/metrics" > /tmp/auth_metrics.json
curl -s "$AUTH/_admin/action_log" > /tmp/auth_action_log.json

python3 "$(dirname "$0")/evaluate.py" \
  --gmail-state /tmp/gmail_state.json \
  --gmail-diff /tmp/gmail_diff.json \
  --gmail-action-log /tmp/gmail_action_log.json \
  --auth-audit /tmp/auth_audit.json \
  --auth-metrics /tmp/auth_metrics.json \
  --auth-action-log /tmp/auth_action_log.json \
  --output "$LOGS_DIR/reward.json"

cat "$LOGS_DIR/reward.json"
