#!/usr/bin/env bash
# Oracle: find top-3 most-reacted messages in #general, post ranked list to #random,
# then react to the #1 message with :trophy:.
set -euo pipefail

BASE="${SLACK_URL:-http://localhost:9005}"

# 1. Resolve channel IDs
CHANNELS=$(curl -s "$BASE/api/conversations.list")
GENERAL_ID=$(echo "$CHANNELS" | python3 -c "
import sys, json
data = json.load(sys.stdin)
print(next(c['id'] for c in data['channels'] if c['name'] == 'general'))
")
RANDOM_ID=$(echo "$CHANNELS" | python3 -c "
import sys, json
data = json.load(sys.stdin)
print(next(c['id'] for c in data['channels'] if c['name'] == 'random'))
")

# 2. Fetch user list to identify bots
BOT_IDS=$(python3 - "$BASE" << 'PYEOF'
import sys, json, urllib.request
base = sys.argv[1]
resp = urllib.request.urlopen(f"{base}/api/users.list")
data = json.loads(resp.read())
bots = [u["id"] for u in data.get("members", []) if u.get("is_bot", False)]
print(json.dumps(bots))
PYEOF
)

# 3. Find the top-3 messages by total human reaction count
TOP3=$(python3 - "$GENERAL_ID" "$BASE" "$BOT_IDS" << 'PYEOF'
import sys, json, urllib.request

channel_id = sys.argv[1]
base = sys.argv[2]
bot_ids = set(json.loads(sys.argv[3]))

resp = urllib.request.urlopen(f"{base}/api/conversations.history?channel={channel_id}&limit=200")
data = json.loads(resp.read())
messages = data.get("messages", [])

ranked = []
for msg in messages:
    ts = msg.get("ts", "")
    try:
        url = f"{base}/api/reactions.get?channel={channel_id}&timestamp={ts}"
        rdata = json.loads(urllib.request.urlopen(url).read())
        reactions = rdata.get("message", {}).get("reactions") or []
    except Exception:
        reactions = msg.get("reactions") or []
    # Count only human reactions (exclude bot user IDs)
    total = sum(len([u for u in r.get("users", []) if u not in bot_ids]) for r in reactions)
    ranked.append({"text": msg.get("text", ""), "ts": ts, "count": total})

ranked.sort(key=lambda m: -m["count"])
print(json.dumps(ranked[:3]))
PYEOF
)

# 4. Build ranked list text for #random
POST_TEXT=$(echo "$TOP3" | python3 -c "
import sys, json
top3 = json.load(sys.stdin)
medals = ['1st 🥇', '2nd 🥈', '3rd 🥉']
lines = ['Top 3 most-reacted messages in #general:']
for i, m in enumerate(top3):
    label = medals[i] if i < len(medals) else f'{i+1}.'
    snippet = m['text'][:60] + ('...' if len(m['text']) > 60 else '')
    lines.append(f'{label} ({m[\"count\"]} reactions): {snippet}')
print('\n'.join(lines))
")

# 5. Post ranked list to #random
curl -s -X POST "$BASE/api/chat.postMessage" \
  -H "Content-Type: application/json" \
  -d "$(python3 -c "import json,sys; print(json.dumps({'channel': '$RANDOM_ID', 'text': sys.stdin.read()}))" <<< "$POST_TEXT")"

# 6. React to the #1 message in #general with :trophy:
WINNER_TS=$(echo "$TOP3" | python3 -c "
import sys, json
top3 = json.load(sys.stdin)
print(top3[0]['ts'])
")

curl -s -X POST "$BASE/api/reactions.add" \
  -H "Content-Type: application/json" \
  -d "{\"channel\": \"$GENERAL_ID\", \"timestamp\": \"$WINNER_TS\", \"name\": \"trophy\"}"

echo "Done."
