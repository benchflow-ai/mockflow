#!/usr/bin/env bash
set -euo pipefail

AUTH="${AUTH_URL:-http://localhost:9000}"
GMAIL="${GMAIL_URL:-http://localhost:9001}"
LOGS_DIR="${LOGS_DIR:-/logs/verifier}"
mkdir -p "$LOGS_DIR"

curl -s "$AUTH/_admin/state" > /tmp/auth_state.json
curl -s "$AUTH/_admin/audit_log?limit=10000" > /tmp/auth_audit.json
curl -s "$AUTH/_admin/metrics" > /tmp/auth_metrics.json
curl -s "$GMAIL/_admin/state" > /tmp/gmail_state.json
curl -s "$GMAIL/_admin/diff" > /tmp/gmail_diff.json

# Merge action logs from both services (best effort).
curl -s "$AUTH/_admin/action_log" > /tmp/auth_action_log.json
curl -s "$GMAIL/_admin/action_log" > /tmp/gmail_action_log.json
python3 - <<'PY'
import json

def entries(path):
    try:
        with open(path) as f:
            data = json.load(f)
    except Exception:
        return []
    return data.get("entries", data) if isinstance(data, dict) else data

merged = {"entries": entries("/tmp/auth_action_log.json") + entries("/tmp/gmail_action_log.json")}
with open("/tmp/action_log.json", "w") as f:
    json.dump(merged, f)
PY

python3 "$(dirname "$0")/evaluate.py" \
  --auth-state /tmp/auth_state.json \
  --auth-audit /tmp/auth_audit.json \
  --auth-metrics /tmp/auth_metrics.json \
  --gmail-state /tmp/gmail_state.json \
  --gmail-diff /tmp/gmail_diff.json \
  --action-log /tmp/action_log.json \
  --output "$LOGS_DIR/reward.json"

cat "$LOGS_DIR/reward.json"
