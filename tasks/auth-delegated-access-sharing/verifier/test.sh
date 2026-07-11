#!/usr/bin/env bash
set -euo pipefail

AUTH="${AUTH_URL:-http://localhost:9000}"
GCAL="${CALENDAR_URL:-http://localhost:9002}"
GDRIVE="${DRIVE_URL:-http://localhost:9003}"
LOGS_DIR="${LOGS_DIR:-/logs/verifier}"
mkdir -p "$LOGS_DIR"

curl -s "$AUTH/_admin/audit_log?limit=10000" > /tmp/auth_audit.json
curl -s "$AUTH/_admin/metrics" > /tmp/auth_metrics.json
curl -s "$GCAL/_admin/state" > /tmp/gcal_state.json
curl -s "$GDRIVE/_admin/state" > /tmp/gdrive_state.json

# Merge action logs from all three services (for trajectory inspection).
curl -s "$AUTH/_admin/action_log" > /tmp/auth_action_log.json
curl -s "$GCAL/_admin/action_log" > /tmp/gcal_action_log.json
curl -s "$GDRIVE/_admin/action_log" > /tmp/gdrive_action_log.json
python3 - <<'PY'
import json

def entries(path):
    try:
        with open(path) as f:
            data = json.load(f)
    except FileNotFoundError:
        return []
    return data.get("entries", data) if isinstance(data, dict) else data

merged = {"entries": (
    entries("/tmp/auth_action_log.json")
    + entries("/tmp/gcal_action_log.json")
    + entries("/tmp/gdrive_action_log.json")
)}
with open("/tmp/action_log.json", "w") as f:
    json.dump(merged, f)
PY

python3 "$(dirname "$0")/evaluate.py" \
  --gcal-state /tmp/gcal_state.json \
  --gdrive-state /tmp/gdrive_state.json \
  --auth-audit /tmp/auth_audit.json \
  --auth-metrics /tmp/auth_metrics.json \
  --action-log /tmp/action_log.json \
  --output "$LOGS_DIR/reward.json"

cat "$LOGS_DIR/reward.json"
