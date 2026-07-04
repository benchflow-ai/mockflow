#!/usr/bin/env bash
set -euo pipefail

DISCORD="${DISCORD_URL:-http://localhost:9006}"

EXPECTED_MESSAGE="$(python3 - <<'PY'
import importlib.util
import os

path = os.path.join(
    os.environ.get("TASKS_DIR", "/tasks"),
    "discord-incident-followup",
    "data",
    "needles.py",
)
spec = importlib.util.spec_from_file_location("discord_needles", path)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
print(mod.EXPECTED_MESSAGE)
PY
)"

guild_id="$(curl -fsS "$DISCORD/api/v10/users/@me/guilds" | jq -r '.[0].id')"
channel_id="$(
  curl -fsS "$DISCORD/api/v10/guilds/$guild_id/channels" |
    jq -r '.[] | select(.name == "backend") | .id' |
    head -n 1
)"

if [[ -z "$channel_id" || "$channel_id" == "null" ]]; then
  echo "backend channel not found" >&2
  exit 1
fi

payload="$(python3 - "$EXPECTED_MESSAGE" <<'PY'
import json
import sys

print(json.dumps({"content": sys.argv[1]}))
PY
)"

curl -fsS \
  -X POST "$DISCORD/api/v10/channels/$channel_id/messages" \
  -H "Authorization: Bot env0-public-demo" \
  -H "Content-Type: application/json" \
  --data "$payload" >/dev/null
