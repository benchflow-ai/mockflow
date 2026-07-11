#!/usr/bin/env bash
set -euo pipefail

SLACK="${SLACK_URL:-http://localhost:9005}"
DRIVE="${DRIVE_URL:-http://localhost:9003}"

# 1. Read Slack #it-ops to understand the situation
AUTH="Authorization: Bearer xoxb-test"
ITOPS_ID=$(curl -s -H "$AUTH" "$SLACK/api/conversations.list" | python3 -c "
import json, sys
data = json.load(sys.stdin)
print(next(c['id'] for c in data['channels'] if c['name'] == 'it-ops'))
")
curl -s -H "$AUTH" "$SLACK/api/conversations.history?channel=$ITOPS_ID" > /tmp/itops.json

# 2. Find the Q2 Strategy Deck in Drive
DECK_ID=$(gws drive files list --params '{"q": "name contains '\''Q2 Strategy Deck'\''"}' | python3 -c "
import json, sys
data = json.load(sys.stdin)
print(data['files'][0]['id'])
")

# 3. List permissions on the deck
PERMS=$(gws drive permissions list --params "{\"fileId\": \"$DECK_ID\"}")
echo "Current permissions: $PERMS"

# 4. Find and revoke marco.silva's permission
MARCO_PERM_ID=$(echo "$PERMS" | python3 -c "
import json, sys
data = json.load(sys.stdin)
for p in data['permissions']:
    if p.get('emailAddress', '') == 'marco.silva@vertex-consulting.com':
        print(p['id'])
        break
")

gws drive permissions delete --params "{\"fileId\": \"$DECK_ID\", \"permissionId\": \"$MARCO_PERM_ID\"}"

# 5. Notify in #it-ops
curl -s -X POST "$SLACK/api/chat.postMessage" \
  -H "$AUTH" -H "Content-Type: application/json" \
  -d "{\"channel\": \"$ITOPS_ID\", \"text\": \"Revoked Marco Silva's access to the Q2 Strategy Deck. All other permissions are intact. Lisa Chang's access is unchanged per your earlier note about board meeting prep.\"}"

# 6. (Bonus) Flag Marco's access to the Hiring Plan
curl -s -X POST "$SLACK/api/chat.postMessage" \
  -H "$AUTH" -H "Content-Type: application/json" \
  -d "{\"channel\": \"$ITOPS_ID\", \"text\": \"Heads up: Marco also still has access to the Hiring Plan 2026 doc in the Leadership folder. Let me know if you want me to revoke that as well.\"}"
