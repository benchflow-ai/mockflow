#!/usr/bin/env bash
# Fetch state/diff/action_log from the stripe environment and score.
set -euo pipefail

STRIPE="${STRIPE_URL:-http://localhost:9007}"
LOGS_DIR="${LOGS_DIR:-/logs/verifier}"
mkdir -p "$LOGS_DIR"

curl -s "$STRIPE/_admin/state" > /tmp/final_state.json
curl -s "$STRIPE/_admin/diff" > /tmp/diff.json
curl -s "$STRIPE/_admin/action_log" > /tmp/action_log.json

python3 "$(dirname "$0")/evaluate.py" \
  --state /tmp/final_state.json \
  --diff /tmp/diff.json \
  --action-log /tmp/action_log.json \
  --output "$LOGS_DIR/reward.json"

cat "$LOGS_DIR/reward.json"
