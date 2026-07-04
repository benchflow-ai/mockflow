#!/usr/bin/env bash
set -euo pipefail

GMAIL="${GMAIL_URL:-http://localhost:9001}"
AUTH="${AUTH_URL:-http://localhost:9000}"
LOGS_DIR="${LOGS_DIR:-/logs/verifier}"
mkdir -p "$LOGS_DIR"

# Gmail state (draft completion + safety checks)
curl -s "$GMAIL/_admin/state"      > /tmp/gmail_state.json
curl -s "$GMAIL/_admin/diff"       > /tmp/gmail_diff.json
curl -s "$GMAIL/_admin/action_log" > /tmp/gmail_action_log.json

# auth audit log + safety metrics (scope minimality)
curl -s "$AUTH/_admin/audit_log?limit=10000" > /tmp/auth_audit_log.json
curl -s "$AUTH/_admin/metrics"               > /tmp/auth_metrics.json

python3 "$(dirname "$0")/evaluate.py" \
  --state /tmp/gmail_state.json \
  --diff /tmp/gmail_diff.json \
  --action-log /tmp/gmail_action_log.json \
  --audit-log /tmp/auth_audit_log.json \
  --auth-metrics /tmp/auth_metrics.json \
  --output "$LOGS_DIR/reward.json"

cat "$LOGS_DIR/reward.json"
