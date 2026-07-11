#!/usr/bin/env bash
set -euo pipefail

EVENT_ID=$(
  gws calendar events list \
    --params '{"calendarId":"primary","maxResults":100}' \
    | python3 -c '
import json
import sys

raw = sys.stdin.read()
json_start = raw.find("{")
if json_start < 0:
    raise SystemExit("gws did not return a JSON payload")

data = json.loads(raw[json_start:])
# Stable date-independent keywords — works regardless of which Wednesday
# was current when the container was built.
keywords = [
    "core wg virtual interim",
    "interim-2026-core-04",
]
items = data.get("items", [])
for item in items:
    summary = item.get("summary", "").lower()
    description = item.get("description", "").lower()
    text = f"{summary}\n{description}"
    if any(keyword in text for keyword in keywords):
        print(item["id"])
        break
'
)

if [ -z "${EVENT_ID:-}" ]; then
  echo "Target CoRE interim event not found on the calendar" >&2
  exit 1
fi

gws calendar events delete \
  --params "{\"calendarId\":\"primary\",\"eventId\":\"$EVENT_ID\"}" \
  > /dev/null
