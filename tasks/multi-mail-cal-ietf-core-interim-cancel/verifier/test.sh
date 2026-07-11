#!/usr/bin/env bash
set -euo pipefail

GMAIL="${GMAIL_URL:-http://localhost:9001}"
GCAL="${CALENDAR_URL:-http://localhost:9002}"
LOGS_DIR="${LOGS_DIR:-/logs/verifier}"
mkdir -p "$LOGS_DIR"

curl -s "$GCAL/_admin/state" > /tmp/gcal_state.json
curl -s "$GCAL/_admin/diff" > /tmp/gcal_diff.json
curl -s "$GMAIL/_admin/action_log" > /tmp/gmail_action_log.json
curl -s "$GCAL/_admin/action_log" > /tmp/gcal_action_log_raw.json

python3 - <<'PYEOF'
import json

with open("/tmp/gmail_action_log.json") as f:
    gmail = json.load(f)
with open("/tmp/gcal_action_log_raw.json") as f:
    gcal = json.load(f)

gmail_entries = gmail.get("entries", gmail) if isinstance(gmail, dict) else gmail
gcal_entries = gcal.get("entries", gcal) if isinstance(gcal, dict) else gcal

with open("/tmp/gcal_action_log.json", "w") as f:
    json.dump({"entries": gmail_entries + gcal_entries}, f)
PYEOF

python3 "$(dirname "$0")/evaluate.py" \
  --gcal-state /tmp/gcal_state.json \
  --gcal-diff /tmp/gcal_diff.json \
  --gcal-action-log /tmp/gcal_action_log.json \
  --output "$LOGS_DIR/reward.json"

cat "$LOGS_DIR/reward.json"
