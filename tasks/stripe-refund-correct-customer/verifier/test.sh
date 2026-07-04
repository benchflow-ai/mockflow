#!/usr/bin/env bash
set -euo pipefail

STRIPE="${STRIPE_URL:-http://localhost:9007}"
LOGS_DIR="${LOGS_DIR:-/logs/verifier}"
mkdir -p "$LOGS_DIR"

curl -s "$STRIPE/_admin/state" > /tmp/stripe_state.json
curl -s "$STRIPE/_admin/diff" > /tmp/stripe_diff.json
curl -s "$STRIPE/_admin/action_log" > /tmp/stripe_action_log.json

python3 "$(dirname "$0")/evaluate.py" \
  --state /tmp/stripe_state.json \
  --diff /tmp/stripe_diff.json \
  --action-log /tmp/stripe_action_log.json \
  --output "$LOGS_DIR/reward.json"

cat "$LOGS_DIR/reward.json"
