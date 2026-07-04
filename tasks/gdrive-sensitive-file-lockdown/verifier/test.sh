#!/usr/bin/env bash
# Fetch state/diff/action_log from the environment and run evaluate.py
set -euo pipefail

BASE="${DRIVE_URL:-http://localhost:9005}"
LOGS_DIR="${LOGS_DIR:-/logs/verifier}"
mkdir -p "$LOGS_DIR"

# Fetch evaluation data
curl -s "$BASE/_admin/state" > /tmp/final_state.json
curl -s "$BASE/_admin/diff" > /tmp/diff.json
curl -s "$BASE/_admin/action_log" > /tmp/action_log.json

# Run evaluation
python3 "$(dirname "$0")/evaluate.py" \
  --state /tmp/final_state.json \
  --diff /tmp/diff.json \
  --action-log /tmp/action_log.json \
  --output "$LOGS_DIR/reward.json"

cat "$LOGS_DIR/reward.json"
