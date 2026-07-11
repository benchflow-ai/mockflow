#!/usr/bin/env bash
set -euo pipefail

AUTH="${AUTH_URL:-http://localhost:9000}"
STRIPE="${STRIPE_URL:-http://localhost:9007}"
LOGS_DIR="${LOGS_DIR:-/logs/verifier}"
mkdir -p "$LOGS_DIR"

curl -s "$STRIPE/_admin/state" > /tmp/stripe_state.json
curl -s "$AUTH/_admin/audit_log?limit=10000" > /tmp/auth_audit.json
curl -s "$AUTH/_admin/metrics" > /tmp/auth_metrics.json
curl -s "$AUTH/_admin/state" > /tmp/auth_state.json

# Merge action logs from both services
curl -s "$STRIPE/_admin/action_log" > /tmp/stripe_action_log.json
curl -s "$AUTH/_admin/action_log" > /tmp/auth_action_log.json
python3 - <<'PY'
import json

def entries(path):
    with open(path) as f:
        data = json.load(f)
    return data.get("entries", data) if isinstance(data, dict) else data

merged = {"entries": entries("/tmp/stripe_action_log.json") + entries("/tmp/auth_action_log.json")}
with open("/tmp/action_log.json", "w") as f:
    json.dump(merged, f)
PY

python3 "$(dirname "$0")/evaluate.py" \
  --stripe-state /tmp/stripe_state.json \
  --auth-audit /tmp/auth_audit.json \
  --auth-state /tmp/auth_state.json \
  --auth-metrics /tmp/auth_metrics.json \
  --action-log /tmp/action_log.json \
  --output "$LOGS_DIR/reward.json"

cat "$LOGS_DIR/reward.json"
