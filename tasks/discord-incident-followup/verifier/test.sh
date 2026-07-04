#!/usr/bin/env bash
set -euo pipefail

LOGS_DIR="${LOGS_DIR:-/logs/verifier}"
mkdir -p "$LOGS_DIR"

python3 "$(dirname "$0")/evaluate.py" \
  --db "${DISCORD_DB_PATH:-/data/discord.db}" \
  --output "$LOGS_DIR/reward.json"

cat "$LOGS_DIR/reward.json"
