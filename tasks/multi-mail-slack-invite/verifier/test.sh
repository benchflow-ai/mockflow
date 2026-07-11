#!/usr/bin/env bash
set -euo pipefail

SLACK="${SLACK_URL:-http://localhost:9005}"
GMAIL="${GMAIL_URL:-http://localhost:9001}"
LOGS_DIR="${LOGS_DIR:-/logs/verifier}"
mkdir -p "$LOGS_DIR"

curl -s "$SLACK/_admin/state"            > /tmp/final_state.json
curl -s "$SLACK/_admin/diff"             > /tmp/diff.json
curl -s "$SLACK/_admin/action_log"       > /tmp/action_log.json
curl -s "$GMAIL/_admin/state"            > /tmp/gmail_state.json
curl -s "$GMAIL/_admin/action_log"       > /tmp/gmail_action_log.json

python3 "$(dirname "$0")/evaluate.py" \
  --state            /tmp/final_state.json \
  --diff             /tmp/diff.json \
  --action-log       /tmp/action_log.json \
  --gmail-state      /tmp/gmail_state.json \
  --gmail-action-log /tmp/gmail_action_log.json \
  --output           "$LOGS_DIR/reward.json"

cat "$LOGS_DIR/reward.json"
