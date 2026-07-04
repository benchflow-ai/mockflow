#!/usr/bin/env bash
set -euo pipefail
BASE="${MOCK_GMAIL_URL:-http://localhost:9001}"
LOGS_DIR="${LOGS_DIR:-/logs/verifier}"
mkdir -p "$LOGS_DIR"
curl -s "$BASE/_admin/state" > /tmp/final_state.json
curl -s "$BASE/_admin/diff" > /tmp/diff.json
curl -s "$BASE/_admin/action_log" > /tmp/action_log.json
python3 "$(dirname "$0")/evaluate.py" \
  --state /tmp/final_state.json \
  --diff /tmp/diff.json \
  --action-log /tmp/action_log.json \
  --output "$LOGS_DIR/reward.json"
cat "$LOGS_DIR/reward.json"
