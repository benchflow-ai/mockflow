#!/usr/bin/env bash
# Oracle: aggregate total reactions per user across all public channels (last 7 days),
# excluding self-reactions (author reacting to their own message).
# If rank-1 user exceeds 20 reactions, also share the leaderboard to #random.
set -euo pipefail

BASE="${SLACK_URL:-http://localhost:9005}"
CUTOFF_TS=$(python3 -c "import time; print(int(time.time()) - 7 * 86400)")

# 1. Get all public non-archived channels
CHANNELS_JSON=$(curl -s "$BASE/api/conversations.list")
GENERAL_ID=$(echo "$CHANNELS_JSON" | python3 -c "
import sys, json
data = json.load(sys.stdin)
print(next(c['id'] for c in data['channels'] if c['name'] == 'general'))
")
RANDOM_ID=$(echo "$CHANNELS_JSON" | python3 -c "
import sys, json
data = json.load(sys.stdin)
print(next(c['id'] for c in data['channels'] if c['name'] == 'random'))
")
CHANNEL_IDS=$(echo "$CHANNELS_JSON" | python3 -c "
import sys, json
data = json.load(sys.stdin)
ids = [c['id'] for c in data['channels']
       if not c.get('is_im') and not c.get('is_private') and not c.get('is_archived', False)]
print('\n'.join(ids))
")

# 2. Aggregate reactions per user across all channels (last 7 days),
#    excluding self-reactions (reactions where reactor == message author).
LEADERBOARD=$(python3 - "$BASE" "$CUTOFF_TS" "$CHANNEL_IDS" << 'PYEOF'
import sys, json, urllib.request
from collections import defaultdict

base = sys.argv[1]
cutoff = float(sys.argv[2])
channel_ids = sys.argv[3].strip().split('\n') if sys.argv[3].strip() else []

reaction_totals = defaultdict(int)

for ch_id in channel_ids:
    try:
        url = f"{base}/api/conversations.history?channel={ch_id}&oldest={cutoff}&limit=200"
        resp = urllib.request.urlopen(url)
        data = json.loads(resp.read())
        for msg in data.get("messages", []):
            author_id = msg.get("user", "")
            if not author_id:
                continue
            for rxn in msg.get("reactions") or []:
                users = rxn.get("users") or []
                # Exclude self-reactions: don't count the author reacting to their own message
                non_self_count = sum(1 for u in users if u != author_id)
                reaction_totals[author_id] += non_self_count
    except Exception:
        pass

# Resolve display names for top 3
top3_ids = sorted(reaction_totals, key=lambda uid: -reaction_totals[uid])[:3]
result = []
for uid in top3_ids:
    try:
        u_resp = urllib.request.urlopen(f"{base}/api/users.info?user={uid}")
        u_data = json.loads(u_resp.read()).get("user", {})
        name = u_data.get("real_name") or u_data.get("name", uid)
    except Exception:
        name = uid
    result.append({"name": name, "user_id": uid, "count": reaction_totals[uid]})

print(json.dumps(result))
PYEOF
)

# 3. Build leaderboard text
POST_TEXT=$(echo "$LEADERBOARD" | python3 -c "
import sys, json
top3 = json.load(sys.stdin)
medals = ['1st 🥇', '2nd 🥈', '3rd 🥉']
lines = ['Weekly Vibe Leaderboard — top reaction-getters (last 7 days, self-reactions excluded):']
for i, u in enumerate(top3):
    m = medals[i] if i < len(medals) else f'{i+1}.'
    lines.append(f'{m} {u[\"name\"]} — {u[\"count\"]} reactions')
print('\n'.join(lines))
")

# 4. Post to #general
curl -s -X POST "$BASE/api/chat.postMessage" \
  -H "Content-Type: application/json" \
  -d "$(python3 -c "import json,sys; print(json.dumps({'channel': '$GENERAL_ID', 'text': sys.stdin.read()}))" <<< "$POST_TEXT")"

# 5. If rank-1 total > 20, also post to #random
RANK1_COUNT=$(echo "$LEADERBOARD" | python3 -c "
import sys, json
top3 = json.load(sys.stdin)
print(top3[0]['count'] if top3 else 0)
")

if [ "$RANK1_COUNT" -gt 20 ]; then
  curl -s -X POST "$BASE/api/chat.postMessage" \
    -H "Content-Type: application/json" \
    -d "$(python3 -c "import json,sys; print(json.dumps({'channel': '$RANDOM_ID', 'text': sys.stdin.read()}))" <<< "$POST_TEXT")"
fi

echo "Done."
