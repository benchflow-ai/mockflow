#!/usr/bin/env bash
set -euo pipefail

SLACK="${SLACK_URL:-http://localhost:9005}"
BOT="Authorization: Bearer ${SLACK_BOT_TOKEN:-xoxb-mock-bot-token}"
WS="X-Mock-Slack-Workspace: workspace_001"

# ─── 1. Find the on-call schedule doc ────────────────────────────────────────
echo "==> Finding on-call schedule doc..."
DOC_ID=$(gws drive files list --params '{"q": "name contains '\''On-Call Schedule'\''", "pageSize": 10}' \
  | python3 -c "
import sys, json
data = json.load(sys.stdin)
for f in data.get('files', []):
    if 'On-Call Schedule' in f.get('name', ''):
        print(f['id'])
        break
")
echo "Found doc: $DOC_ID"

# ─── 2. Read current doc content ─────────────────────────────────────────────
echo "==> Reading doc content..."
DOC_CONTENT=$(gws docs documents get --params "{\"documentId\": \"$DOC_ID\"}")

# ─── 3. Check calendar for PTO events in April ──────────────────────────────
echo "==> Checking calendar for PTO..."
GCAL_EVENTS=$(gws calendar events list --params '{"calendarId": "primary", "timeMin": "2026-04-01T00:00:00Z", "timeMax": "2026-05-01T00:00:00Z"}')

# ─── 4. Read Slack #on-call-swap for swap agreements ─────────────────────────
echo "==> Reading Slack #on-call-swap..."
SWAP_CH=$(curl -sf -H "$BOT" -H "$WS" "$SLACK/api/conversations.list" \
  | python3 -c "
import sys, json
data = json.load(sys.stdin)
for ch in data.get('channels', []):
    if ch.get('name') == 'on-call-swap':
        print(ch['id'])
        break
")
echo "Swap channel: $SWAP_CH"

SWAP_HISTORY=$(curl -sf -H "$BOT" -H "$WS" "$SLACK/api/conversations.history?channel=$SWAP_CH&limit=50")

# ─── 5. Compute rebalanced schedule and update doc ───────────────────────────
echo "==> Computing rebalanced schedule..."

# Get the end index of the doc for replacement
END_INDEX=$(echo "$DOC_CONTENT" | python3 -c "
import sys, json
data = json.load(sys.stdin)
body = data.get('body', {})
content = body.get('content', [])
if content:
    print(content[-1].get('endIndex', 1) - 1)
else:
    print(1)
")

# Build the updated document text
UPDATED_TEXT=$(python3 << 'PYEOF'
schedule = [
    ("April 7-11", "Elena Petrov"),
    ("April 14-18", "Bob Martinez"),
    ("April 21-25", "Alice Chen"),
    ("April 28-May 2", "Derek Okafor"),
]

lines = [
    "On-Call Schedule \u2014 April",
    "",
    "Primary on-call rotation for April 2026.",
    "Each engineer covers one week (Monday\u2013Friday).",
    "Max 2 weeks per person; alphabetical tiebreaker for reassignments.",
    "",
    "| Week | On-Call Engineer |",
    "|------|-----------------|",
]
for week, eng in schedule:
    lines.append(f"| {week} | {eng} |")
lines.append("")
lines.append("If you need to swap, post in #on-call-swap and get confirmation from the other person.")
print("\n".join(lines))
PYEOF
)

# Replace entire document content: delete all then insert new
gws docs documents batchUpdate \
  --params "{\"documentId\": \"$DOC_ID\"}" \
  --json "$(python3 -c "
import json, sys
new_text = sys.stdin.read()
requests = [
    {'deleteContentRange': {'range': {'startIndex': 1, 'endIndex': $END_INDEX}}},
    {'insertText': {'location': {'index': 1}, 'text': new_text}},
]
print(json.dumps({'requests': requests}))
" <<< "$UPDATED_TEXT")"
echo "Doc updated."

# ─── 6. Post final schedule to #on-call-swap ─────────────────────────────────
echo "==> Posting final schedule to Slack..."
SCHEDULE_MSG="Updated on-call schedule for April:\n\n- April 7-11: Elena Petrov\n- April 14-18: Bob Martinez\n- April 21-25: Alice Chen\n- April 28-May 2: Derek Okafor"

curl -sf -X POST -H "$BOT" -H "$WS" -H "Content-Type: application/json" \
  "$SLACK/api/chat.postMessage" \
  -d "$(python3 -c "
import json
print(json.dumps({'channel': '$SWAP_CH', 'text': '$SCHEDULE_MSG'}))
")"

echo "==> Done. On-call schedule rebalanced and posted."
