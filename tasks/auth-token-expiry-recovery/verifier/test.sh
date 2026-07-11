#!/usr/bin/env bash
set -euo pipefail

AUTH="${AUTH_URL:-http://localhost:9000}"
GMAIL="${GMAIL_URL:-http://localhost:9001}"
LOGS_DIR="${LOGS_DIR:-/logs/verifier}"
mkdir -p "$LOGS_DIR"

curl -s "$GMAIL/_admin/state" > /tmp/gmail_state.json
curl -s "$GMAIL/_admin/diff" > /tmp/gmail_diff.json
curl -s "$AUTH/_admin/audit_log?limit=10000" > /tmp/auth_audit.json
curl -s "$AUTH/_admin/metrics" > /tmp/auth_metrics.json
curl -s "$AUTH/_admin/state" > /tmp/auth_state.json

python3 "$(dirname "$0")/evaluate.py" \
  --gmail-state /tmp/gmail_state.json \
  --gmail-diff /tmp/gmail_diff.json \
  --auth-audit /tmp/auth_audit.json \
  --auth-metrics /tmp/auth_metrics.json \
  --auth-state /tmp/auth_state.json \
  --output "$LOGS_DIR/reward.json"

cat "$LOGS_DIR/reward.json"
