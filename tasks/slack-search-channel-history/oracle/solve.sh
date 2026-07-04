#!/usr/bin/env bash
# Solution for slack-search-channel-history.
#
# Correct token usage:
#   - SLACK_BOT_TOKEN  (xoxb-) for conversations.list / history / replies / postMessage
#   - SLACK_USER_TOKEN (xoxp-) for search.messages (bot token is rejected)
#
# Strategy:
#   1. Attempt search.messages with bot token → expect not_allowed_token_type error.
#   2. Retry search.messages with user token → may return results, but answer lives in a
#      thread reply so we still need conversations.history + replies to confirm.
#   3. Paginate conversations.history on #product-archive until we find the thread.
#   4. Call conversations.replies to read all 20 replies.
#   5. Extract the confirmed rate limit and post it in #general.

set -euo pipefail

BASE="${SLACK_URL:-http://localhost:9002}"
BOT="Authorization: Bearer ${SLACK_BOT_TOKEN:-mock-bot-token}"
USER_TOK="Authorization: Bearer ${SLACK_USER_TOKEN:-mock-user-token}"

# ---------------------------------------------------------------------------
# 1. Demonstrate correct token awareness: search.messages requires user token
# ---------------------------------------------------------------------------
echo "==> Trying search.messages with bot token (should fail)..."
SEARCH_BOT=$(curl -sf -H "$BOT" \
  "$BASE/api/search.messages?query=enterprise+rate+limit&count=5" || true)
BOT_ERROR=$(echo "$SEARCH_BOT" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('error',''))" 2>/dev/null || true)
echo "    Bot token error: ${BOT_ERROR:-none}"

echo "==> Retrying search.messages with user token..."
SEARCH_USER=$(curl -sf -H "$USER_TOK" \
  "$BASE/api/search.messages?query=enterprise+rate+limit&count=10" || true)
SEARCH_OK=$(echo "$SEARCH_USER" | python3 -c "import sys,json; print(json.load(sys.stdin).get('ok',False))" 2>/dev/null || echo "false")
echo "    User token ok: $SEARCH_OK"

# ---------------------------------------------------------------------------
# 2. Resolve #product-archive channel ID via bot token
# ---------------------------------------------------------------------------
echo "==> Fetching channel list..."
CHANNELS=$(curl -sf -H "$BOT" "$BASE/api/conversations.list?types=public_channel&limit=1000")
ARCHIVE_ID=$(echo "$CHANNELS" | python3 -c "
import sys, json
chs = json.load(sys.stdin)['channels']
ch = next((c for c in chs if c['name'] == 'product-archive'), None)
print(ch['id'] if ch else '')
")

if [ -z "$ARCHIVE_ID" ]; then
  echo "ERROR: #product-archive channel not found" >&2
  exit 1
fi
echo "    #product-archive id: $ARCHIVE_ID"

# ---------------------------------------------------------------------------
# 3. Paginate conversations.history until we find a thread with many replies
# ---------------------------------------------------------------------------
echo "==> Paginating conversations.history (limit=20, bot token)..."
CURSOR=""
THREAD_TS=""
PAGE=0

while true; do
  PAGE=$((PAGE + 1))
  URL="$BASE/api/conversations.history?channel=$ARCHIVE_ID&limit=20"
  if [ -n "$CURSOR" ]; then
    URL="${URL}&cursor=${CURSOR}"
  fi

  RESP=$(curl -sf -H "$BOT" "$URL")

  # Look for a top-level message with ≥10 replies (our needle has 20)
  FOUND=$(echo "$RESP" | python3 -c "
import sys, json
msgs = json.load(sys.stdin).get('messages', [])
for m in msgs:
    if m.get('reply_count', 0) >= 10:
        print(m['ts'])
        break
" 2>/dev/null || true)

  if [ -n "$FOUND" ]; then
    THREAD_TS="$FOUND"
    echo "    Found threaded message on page $PAGE: ts=$THREAD_TS"
    break
  fi

  CURSOR=$(echo "$RESP" | python3 -c "
import sys, json
print(json.load(sys.stdin).get('response_metadata', {}).get('next_cursor', ''))
" 2>/dev/null || true)

  if [ -z "$CURSOR" ]; then
    echo "ERROR: exhausted history without finding the thread" >&2
    exit 1
  fi
  echo "    Page $PAGE done, following cursor..."
done

# ---------------------------------------------------------------------------
# 4. Read the full thread with conversations.replies
# ---------------------------------------------------------------------------
echo "==> Fetching thread replies (bot token)..."
REPLIES=$(curl -sf -H "$BOT" \
  "$BASE/api/conversations.replies?channel=$ARCHIVE_ID&ts=$THREAD_TS&limit=100")

REPLY_COUNT=$(echo "$REPLIES" | python3 -c "
import sys, json
print(len(json.load(sys.stdin).get('messages', [])))
" 2>/dev/null || echo 0)
echo "    Thread messages (parent + replies): $REPLY_COUNT"

# ---------------------------------------------------------------------------
# 5. Extract the confirmed rate limit from replies
# ---------------------------------------------------------------------------
ANSWER=$(echo "$REPLIES" | python3 -c "
import sys, json, re
msgs = json.load(sys.stdin).get('messages', [])
pattern = re.compile(r'(\d[\d,]+)\s*requests?[/ ]*(per\s*)?minute', re.IGNORECASE)
for m in msgs:
    hit = pattern.search(m.get('text', ''))
    if hit:
        limit = hit.group(1).replace(',', '')
        print(limit)
        break
" 2>/dev/null || true)

if [ -z "$ANSWER" ]; then
  echo "ERROR: could not extract rate limit from thread" >&2
  exit 1
fi
echo "    Extracted rate limit: $ANSWER requests/minute"

# ---------------------------------------------------------------------------
# 6. Post the answer in #general
# ---------------------------------------------------------------------------
echo "==> Resolving #general channel ID..."
GENERAL_ID=$(echo "$CHANNELS" | python3 -c "
import sys, json
chs = json.load(sys.stdin)['channels']
ch = next((c for c in chs if c['name'] == 'general'), None)
print(ch['id'] if ch else '')
")
if [ -z "$GENERAL_ID" ]; then
  echo "ERROR: #general channel not found" >&2
  exit 1
fi
echo "    #general id: $GENERAL_ID"

echo "==> Posting answer to #general (bot token)..."
POST=$(curl -sf -X POST \
  -H "$BOT" \
  -H "Content-Type: application/json" \
  "$BASE/api/chat.postMessage" \
  -d "{\"channel\": \"${GENERAL_ID}\", \"text\": \"The Enterprise API rate limit is **${ANSWER} requests/minute** (source: #product-archive)\"}")

POST_OK=$(echo "$POST" | python3 -c "import sys,json; print(json.load(sys.stdin).get('ok',False))" 2>/dev/null || echo false)
echo "    Post ok: $POST_OK"

echo "==> Done. Enterprise API rate limit: $ANSWER requests/minute"
