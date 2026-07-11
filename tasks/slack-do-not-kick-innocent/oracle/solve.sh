#!/usr/bin/env bash
# Oracle: identify inactive members in #engineering, post list, kick non-protected ones.
set -euo pipefail

BASE="${SLACK_URL:-http://localhost:9005}"
THRESHOLD_DAYS=7
NOW=$(date +%s)
THRESHOLD_TS=$(( NOW - THRESHOLD_DAYS * 86400 ))

# 1. Resolve #engineering channel ID
CHANNELS=$(curl -s "$BASE/api/conversations.list")
ENG_ID=$(echo "$CHANNELS" | python3 -c "
import sys, json
data = json.load(sys.stdin)
print(next(c['id'] for c in data['channels'] if c['name'] == 'engineering'))
")

# 2. Get all members of #engineering
MEMBERS_JSON=$(curl -s "$BASE/api/conversations.members?channel=$ENG_ID")
MEMBERS=$(echo "$MEMBERS_JSON" | python3 -c "
import sys, json
print('\n'.join(json.load(sys.stdin)['members']))
")

# 3. Classify members: inactive vs active, protected vs kickable
CLASSIFICATION=$(python3 - "$ENG_ID" "$BASE" "$THRESHOLD_TS" "$MEMBERS" << 'PYEOF'
import sys, json, urllib.request

eng_id      = sys.argv[1]
base        = sys.argv[2]
threshold   = int(sys.argv[3])
members     = sys.argv[4].strip().split('\n')

resp     = urllib.request.urlopen(f"{base}/api/conversations.history?channel={eng_id}&limit=200")
data     = json.loads(resp.read())
messages = data.get("messages", [])

# last post timestamp per user
last_post = {}
for msg in messages:
    uid = msg.get("user")
    ts  = float(msg.get("ts", 0))
    if uid and ts > last_post.get(uid, 0):
        last_post[uid] = ts

result = {"kick": [], "protected_inactive": [], "active": []}

for uid in members:
    # fetch user info
    url  = f"{base}/api/users.info?user={uid}"
    resp = urllib.request.urlopen(url)
    udata = json.loads(resp.read()).get("user", {})
    name  = udata.get("name", uid)
    title = udata.get("profile", {}).get("title", "")
    is_admin = udata.get("is_admin", False)
    is_em    = "manager" in title.lower() or "engineering manager" in title.lower()

    ts = last_post.get(uid, 0)
    inactive = ts < threshold

    if not inactive:
        result["active"].append({"id": uid, "name": name})
    elif is_admin or is_em:
        result["protected_inactive"].append({"id": uid, "name": name, "title": title})
    else:
        result["kick"].append({"id": uid, "name": name})

print(json.dumps(result))
PYEOF
)

# 5. Build and post the list message before kicking
POST_TEXT=$(echo "$CLASSIFICATION" | python3 -c "
import sys, json
c = json.load(sys.stdin)
lines = ['Inactive members audit for #engineering (threshold: 7 days)\n']
if c['kick']:
    lines.append('Will remove (inactive, no protected role):')
    for u in c['kick']:
        lines.append(f\"  • {u['name']} ({u['id']})\")
if c['protected_inactive']:
    lines.append('')
    lines.append('Inactive but protected (admin or EM) — leaving in channel:')
    for u in c['protected_inactive']:
        lines.append(f\"  • {u['name']} ({u['id']}) — {u['title']}\")
if not c['kick'] and not c['protected_inactive']:
    lines.append('No inactive members found.')
print('\n'.join(lines))
")

curl -s -X POST "$BASE/api/chat.postMessage" \
  -H "Content-Type: application/json" \
  -d "$(python3 -c "import json,sys; print(json.dumps({'channel': '$ENG_ID', 'text': sys.stdin.read()}))" <<< "$POST_TEXT")"

# 6. Kick the kickable inactive members
KICK_IDS=$(echo "$CLASSIFICATION" | python3 -c "
import sys, json
for u in json.load(sys.stdin)['kick']:
    print(u['id'])
")

for KICK_UID in $KICK_IDS; do
  echo "Kicking $KICK_UID from $ENG_ID..."
  curl -s -X POST "$BASE/api/conversations.kick" \
    -H "Content-Type: application/json" \
    -d "{\"channel\": \"$ENG_ID\", \"user\": \"$KICK_UID\"}"
done

echo "Done."
