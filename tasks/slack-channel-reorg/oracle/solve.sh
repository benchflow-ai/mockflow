#!/usr/bin/env bash
# Oracle solution for slack-channel-reorg.
#
# Strategy:
#   1. Get members from all 3 public metaverse-* channels.
#   2. DM chris.taylor (EM) to unlock access to private #metaverse-stealth.
#   3. Get members from #metaverse-stealth; deduplicate all 4 lists.
#   4. Two-pass skill matching (seniors first) with slot limits:
#        - platform: Senior ICs only, 3 slots
#        - commerce: max 2 slots
#   5. Invite matched members to hiring channels.
#   6. Send personal DM to every Metaverse member:
#        matched   -> "You've been added to #<channel>, await interview"
#        unmatched -> "No internal match found, best of luck"

set -euo pipefail

BASE="${SLACK_URL:-http://localhost:9002}"
BOT="Authorization: Bearer ${SLACK_BOT_TOKEN:-mock-bot-token}"
WS="X-Mock-Slack-Workspace: workspace_001"

# ---------------------------------------------------------------------------
# Helper: extract channel ID by name from a JSON channels response
# ---------------------------------------------------------------------------
get_channel_id() {
  local json_str="$1"
  local name="$2"
  echo "$json_str" | python3 -c "
import sys, json
chs = json.load(sys.stdin).get('channels', [])
ch = next((c for c in chs if c['name'] == '$name'), None)
print(ch['id'] if ch else '')
"
}

# ---------------------------------------------------------------------------
# Helper: get space-separated member IDs for a channel
# ---------------------------------------------------------------------------
get_members() {
  curl -sf -H "$BOT" -H "$WS" \
    "$BASE/api/conversations.members?channel=$1&limit=200" \
    | python3 -c "import sys, json; print(' '.join(json.load(sys.stdin).get('members', [])))"
}

# ---------------------------------------------------------------------------
# 1. Resolve public channel IDs
# ---------------------------------------------------------------------------
echo "==> Fetching public channel list..."
PUBLIC_CHANNELS=$(curl -sf -H "$BOT" -H "$WS" "$BASE/api/conversations.list?limit=200")

GENERAL_ID=$(get_channel_id "$PUBLIC_CHANNELS" "metaverse-general")
ENGINEERING_ID=$(get_channel_id "$PUBLIC_CHANNELS" "metaverse-engineering")
PRODUCT_SRC_ID=$(get_channel_id "$PUBLIC_CHANNELS" "metaverse-product")
PLATFORM_ID=$(get_channel_id "$PUBLIC_CHANNELS" "platform-team-hiring")
AIML_ID=$(get_channel_id "$PUBLIC_CHANNELS" "aiml-team-hiring")
COMMERCE_ID=$(get_channel_id "$PUBLIC_CHANNELS" "commerce-team-hiring")
INFRA_ID=$(get_channel_id "$PUBLIC_CHANNELS" "infra-team-hiring")
PRODUCT_ID=$(get_channel_id "$PUBLIC_CHANNELS" "product-team-hiring")

# ---------------------------------------------------------------------------
# 2. Collect members from the 3 public Metaverse channels
# ---------------------------------------------------------------------------
echo "==> Collecting members from public Metaverse channels..."
M1=$(get_members "$GENERAL_ID")
M2=$(get_members "$ENGINEERING_ID")
M3=$(get_members "$PRODUCT_SRC_ID")

# ---------------------------------------------------------------------------
# 3. DM chris.taylor to unlock access to private #metaverse-stealth
# ---------------------------------------------------------------------------
echo "==> Contacting EM to request access to private Metaverse Stealth channel..."

# Find chris.taylor's user ID from the general channel member list
CHRIS_ID=$(echo "$M1" | tr ' ' '\n' | while read -r UID2; do
  NAME=$(curl -sf -H "$BOT" -H "$WS" "$BASE/api/users.info?user=$UID2" \
         | python3 -c "import sys,json; u=json.load(sys.stdin).get('user',{}); print(u.get('name',''))")
  if [ "$NAME" = "chris.taylor" ]; then echo "$UID2"; break; fi
done)
echo "    chris.taylor ID: $CHRIS_ID"

CHRIS_DM_RESP=$(curl -sf -X POST -H "$BOT" -H "$WS" -H "Content-Type: application/json" \
  "$BASE/api/conversations.open" \
  -d "{\"users\": \"$CHRIS_ID\"}")
CHRIS_DM_ID=$(echo "$CHRIS_DM_RESP" \
  | python3 -c "import sys,json; print(json.load(sys.stdin).get('channel',{}).get('id',''))")

curl -sf -X POST -H "$BOT" -H "$WS" -H "Content-Type: application/json" \
  "$BASE/api/chat.postMessage" \
  -d "{\"channel\": \"$CHRIS_DM_ID\", \"text\": \"Hi Chris — I'm coordinating the Metaverse reorg placement and need access to the private Stealth Project channel to include those engineers in the matching process.\"}" \
  > /dev/null
echo "    DM sent to chris.taylor — trigger activated."

# ---------------------------------------------------------------------------
# 4. Fetch private channels and get metaverse-stealth members
# ---------------------------------------------------------------------------
echo "==> Fetching private channel list..."
PRIVATE_CHANNELS=$(curl -sf -H "$BOT" -H "$WS" \
  "$BASE/api/conversations.list?types=private_channel&limit=200")

STEALTH_ID=$(get_channel_id "$PRIVATE_CHANNELS" "metaverse-stealth")
echo "    metaverse-stealth ID: $STEALTH_ID"

M4=""
if [ -n "$STEALTH_ID" ]; then
  M4=$(get_members "$STEALTH_ID")
  echo "    Stealth members: $M4"
fi

# ---------------------------------------------------------------------------
# 5. Deduplicate all Metaverse members
# ---------------------------------------------------------------------------
echo "==> Deduplicating all Metaverse members..."
MEMBER_IDS=$(echo "$M1 $M2 $M3 $M4" | tr ' ' '\n' | grep -v '^$' | sort -u | tr '\n' ' ')
echo "    Unique member count: $(echo "$MEMBER_IDS" | wc -w | tr -d ' ')"

# ---------------------------------------------------------------------------
# 6. Skill matching with slot limits — two passes (seniors first)
# ---------------------------------------------------------------------------
echo "==> Matching members to hiring channels (seniors first)..."

NON_METAVERSE="HR Admin|Platform Team Lead|AI/ML Team Lead|Commerce Team Lead|Infrastructure Team Lead|Product Team Lead"

RESULTS_FILE=$(mktemp)
MATCHED_IDS_FILE=$(mktemp)
COMMERCE_COUNT=0

match_member() {
  local SLACK_UID="$1"
  local SENIOR_ONLY="$2"   # "yes" = only process seniors; "no" = only process non-seniors

  local PROFILE
  PROFILE=$(curl -sf -H "$BOT" -H "$WS" "$BASE/api/users.info?user=$SLACK_UID")
  local REAL_NAME
  REAL_NAME=$(echo "$PROFILE" | python3 -c "
import sys, json
u = json.load(sys.stdin).get('user', {})
print(u.get('real_name', u.get('name', '')))")
  local TITLE
  TITLE=$(echo "$PROFILE" | python3 -c "
import sys, json
u = json.load(sys.stdin).get('user', {})
print(u.get('profile', {}).get('title', u.get('title', '')))")

  # Skip non-Metaverse department leads
  if echo "$REAL_NAME" | grep -qE "^($NON_METAVERSE)$"; then
    return
  fi

  # Skip if already matched in pass 1
  if grep -qx "$SLACK_UID" "$MATCHED_IDS_FILE" 2>/dev/null; then
    return
  fi

  local TITLE_LOWER
  TITLE_LOWER=$(echo "$TITLE" | tr '[:upper:]' '[:lower:]')

  local IS_SENIOR="no"
  if echo "$TITLE_LOWER" | grep -qE "^senior "; then
    IS_SENIOR="yes"
  fi

  # In pass 1, skip non-seniors; in pass 2, skip seniors
  if [ "$SENIOR_ONLY" = "yes" ] && [ "$IS_SENIOR" = "no" ]; then return; fi
  if [ "$SENIOR_ONLY" = "no"  ] && [ "$IS_SENIOR" = "yes" ]; then return; fi

  echo "    $REAL_NAME | senior=$IS_SENIOR | $TITLE"

  local TARGET_ID=""
  local TARGET_NAME=""

  if echo "$TITLE_LOWER" | grep -qE "kubernetes|terraform|gitops|sre\b|ci/cd"; then
    TARGET_ID="$INFRA_ID"; TARGET_NAME="infra-team-hiring"
  elif echo "$TITLE_LOWER" | grep -qE "pytorch|tensorflow|computer vision|neural|ml engineer|ml research"; then
    TARGET_ID="$AIML_ID"; TARGET_NAME="aiml-team-hiring"
  elif echo "$TITLE_LOWER" | grep -qE "grpc|distributed system|microservice|event-driven|fastapi|django|celery"; then
    # Platform is Senior-only
    if [ "$IS_SENIOR" = "yes" ]; then
      TARGET_ID="$PLATFORM_ID"; TARGET_NAME="platform-team-hiring"
    else
      echo "      -> no match (platform requires Senior IC)"
    fi
  elif echo "$TITLE_LOWER" | grep -qE "react|typescript|node\.js|serverless|webgl|full.stack engineer"; then
    # Commerce: max 2 slots
    if [ "$COMMERCE_COUNT" -lt 2 ]; then
      TARGET_ID="$COMMERCE_ID"; TARGET_NAME="commerce-team-hiring"
      COMMERCE_COUNT=$((COMMERCE_COUNT + 1))
    else
      echo "      -> no match (commerce 2-slot limit reached)"
    fi
  elif echo "$TITLE_LOWER" | grep -qE "user research|growth analytics|a/b test|conversion|go-to-market"; then
    TARGET_ID="$PRODUCT_ID"; TARGET_NAME="product-team-hiring"
  fi

  if [ -n "$TARGET_ID" ]; then
    echo "      -> $TARGET_NAME"
    curl -sf -X POST -H "$BOT" -H "$WS" -H "Content-Type: application/json" \
      "$BASE/api/conversations.invite" \
      -d "{\"channel\": \"$TARGET_ID\", \"users\": \"$SLACK_UID\"}" > /dev/null
    echo "$SLACK_UID" >> "$MATCHED_IDS_FILE"
  else
    echo "      -> unmatched"
  fi

  echo "${SLACK_UID}|${REAL_NAME}|${TARGET_NAME}" >> "$RESULTS_FILE"
}

# Pass 1: seniors first (ensures senior-only channels and slot-priority)
echo "  -- Pass 1: seniors --"
for SLACK_UID in $MEMBER_IDS; do
  match_member "$SLACK_UID" "yes"
done

# Pass 2: non-seniors (fills remaining slots)
echo "  -- Pass 2: non-seniors --"
for SLACK_UID in $MEMBER_IDS; do
  match_member "$SLACK_UID" "no"
done

rm -f "$MATCHED_IDS_FILE"

# ---------------------------------------------------------------------------
# 7. Send personal DM to every Metaverse member
# ---------------------------------------------------------------------------
echo "==> Sending personal DMs..."

while IFS='|' read -r SLACK_UID REAL_NAME TARGET_NAME; do
  DM_RESP=$(curl -sf -X POST -H "$BOT" -H "$WS" -H "Content-Type: application/json" \
    "$BASE/api/conversations.open" \
    -d "{\"users\": \"$SLACK_UID\"}")
  DM_ID=$(echo "$DM_RESP" \
    | python3 -c "import sys, json; print(json.load(sys.stdin).get('channel', {}).get('id', ''))")

  if [ -z "$DM_ID" ]; then
    echo "    WARNING: no DM channel for $REAL_NAME"
    continue
  fi

  if [ -n "$TARGET_NAME" ]; then
    MSG="Hi $REAL_NAME — you've been matched to an internal team! You've been added to #$TARGET_NAME. The team will reach out soon to arrange next steps. Thank you for your contributions to the Metaverse division."
  else
    MSG="Hi $REAL_NAME — we've completed the internal talent match process. Unfortunately we were unable to find an internal match for your current skills profile. We wish you the very best of luck in your next chapter."
  fi

  curl -sf -X POST -H "$BOT" -H "$WS" -H "Content-Type: application/json" \
    "$BASE/api/chat.postMessage" \
    -d "{\"channel\": \"$DM_ID\", \"text\": $(echo "$MSG" | python3 -c 'import sys,json; print(json.dumps(sys.stdin.read()))')}" \
    > /dev/null

  echo "    DM sent -> $REAL_NAME (${TARGET_NAME:-unmatched})"
done < "$RESULTS_FILE"

rm -f "$RESULTS_FILE"
echo "==> Done."
