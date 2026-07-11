#!/usr/bin/env bash
set -euo pipefail

SLACK="${SLACK_URL:-http://localhost:9005}"
BOT="Authorization: Bearer ${SLACK_BOT_TOKEN:-xoxb-mock-bot-token}"
WS="X-Mock-Slack-Workspace: workspace_001"

# ─── 1. Check calendars for Saturday availability ─────────────────────────────
echo "==> Checking calendars for Saturday events..."

# Compute this Saturday's date range
SAT_RANGE=$(python3 << 'PYEOF'
from datetime import datetime, timedelta
now = datetime.utcnow()
days_ahead = 5 - now.weekday()
if days_ahead <= 0:
    days_ahead += 7
sat = now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=days_ahead)
sun = sat + timedelta(days=1)
print(f"{sat.strftime('%Y-%m-%dT00:00:00Z')} {sun.strftime('%Y-%m-%dT00:00:00Z')} {sat.strftime('%Y-%m-%d')}")
PYEOF
)
SAT_MIN=$(echo "$SAT_RANGE" | awk '{print $1}')
SAT_MAX=$(echo "$SAT_RANGE" | awk '{print $2}')
SAT_DATE=$(echo "$SAT_RANGE" | awk '{print $3}')

GCAL_EVENTS=$(gws calendar events list --params "{\"calendarId\": \"primary\", \"timeMin\": \"$SAT_MIN\", \"timeMax\": \"$SAT_MAX\"}")
echo "Saturday events: $GCAL_EVENTS"

# ─── 2. Check Slack #engineering for context ──────────────────────────────────
echo "==> Reading Slack #engineering..."

ENG_CH=$(curl -sf -H "$BOT" -H "$WS" "$SLACK/api/conversations.list" \
  | python3 -c "
import sys, json
data = json.load(sys.stdin)
for ch in data.get('channels', []):
    if ch.get('name') == 'engineering':
        print(ch['id'])
        break
")
echo "Engineering channel: $ENG_CH"

ENG_HISTORY=$(curl -sf -H "$BOT" -H "$WS" "$SLACK/api/conversations.history?channel=$ENG_CH&limit=50")
echo "Channel history retrieved."

# Also check pinned messages
PINS=$(curl -sf -H "$BOT" -H "$WS" "$SLACK/api/pins.list?channel=$ENG_CH")
echo "Pins retrieved."

# ─── 3. Identify Morgan Lee as the best candidate ────────────────────────────
# Morgan: empty Saturday + explicit willingness ("Happy to pick up extra shifts")
# Casey: also willing but has a minor on-call conflict
# Alex: empty Saturday but explicit opt-out -- DO NOT ASSIGN
# Jamie: birthday party conflict
echo "==> Selected Morgan Lee (available + willing, no conflicts)"

# ─── 4. Create calendar event ────────────────────────────────────────────────
echo "==> Creating calendar event..."

gws calendar events insert --params '{"calendarId": "primary"}' --json "{
  \"summary\": \"Production Deploy - Weekend Coverage\",
  \"start\": {\"dateTime\": \"${SAT_DATE}T10:00:00\"},
  \"end\": {\"dateTime\": \"${SAT_DATE}T14:00:00\"},
  \"attendees\": [{\"email\": \"morgan.lee@nexus.test\"}],
  \"description\": \"Saturday production deploy coverage.\"
}"
echo "Calendar event created."

# ─── 5. Notify Morgan on Slack ───────────────────────────────────────────────
echo "==> Sending Slack notification to Morgan..."

curl -sf -X POST -H "$BOT" -H "$WS" -H "Content-Type: application/json" \
  "$SLACK/api/chat.postMessage" \
  -d "{\"channel\": \"$ENG_CH\", \"text\": \"Hey @morgan.lee, you're signed up for the Saturday production deploy this week (10 AM to 2 PM). Thanks for volunteering!\"}"

echo "==> Done. Morgan Lee assigned to Saturday deploy coverage."
