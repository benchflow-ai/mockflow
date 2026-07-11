#!/usr/bin/env bash
# Oracle solution for multi-mail-slack-invite.
#
# Strategy:
#   1. Create three SkillsBench difficulty channels.
#   2. For each contributor, look up their Slack user by (canonical) email
#      and invite them to every channel matching their tasks' difficulty.
#
# Difficulty thresholds:
#   easy   → estimated time < 100 min
#   medium → 100 ≤ estimated time < 500 min
#   hard   → estimated time ≥ 500 min
#
# Note: contributors with tasks in multiple buckets appear in multiple channels.

set -euo pipefail

GMAIL="${GMAIL_URL:-http://localhost:9001}"
BASE="${SLACK_URL:-http://localhost:9005}"
BOT="Authorization: Bearer ${SLACK_BOT_TOKEN:-xoxb-mock-bot-token}"
WS="X-Mock-Slack-Workspace: workspace_001"

# ---------------------------------------------------------------------------
# 0. Read all SkillsBench emails from Gmail (satisfies Gmail scoring component)
# ---------------------------------------------------------------------------
echo "==> Reading SkillsBench contributor emails from Gmail..."
MSG_IDS=$(curl -sf \
  "$GMAIL/gmail/v1/users/me/messages?q=subject%3A%5BSkillsBench%5D&maxResults=100" \
  | python3 -c "import sys,json; [print(m['id']) for m in json.load(sys.stdin).get('messages',[])]")

for mid in $MSG_IDS; do
  curl -sf "$GMAIL/gmail/v1/users/me/messages/$mid" > /dev/null
done
echo "    read $(echo "$MSG_IDS" | grep -c .) email(s)"

# ---------------------------------------------------------------------------
# Helper: create a channel and return its ID
# ---------------------------------------------------------------------------
create_channel() {
  curl -sf -X POST -H "$BOT" -H "$WS" -H "Content-Type: application/json" \
    "$BASE/api/conversations.create" \
    -d "{\"name\": \"$1\"}" \
    | python3 -c "import sys,json; print(json.load(sys.stdin).get('channel',{}).get('id',''))"
}

# ---------------------------------------------------------------------------
# Helper: look up a Slack user ID by email
# ---------------------------------------------------------------------------
lookup_user() {
  local encoded
  encoded=$(python3 -c "import urllib.parse,sys; print(urllib.parse.quote('$1'))")
  curl -sf -H "$BOT" -H "$WS" \
    "$BASE/api/users.lookupByEmail?email=$encoded" \
    | python3 -c "import sys,json; print(json.load(sys.stdin).get('user',{}).get('id',''))"
}

# ---------------------------------------------------------------------------
# Helper: invite a contributor (by email) to a channel
# ---------------------------------------------------------------------------
invite_contributor() {
  local email="$1"
  local ch_id="$2"
  local uid
  uid=$(lookup_user "$email")
  if [ -n "$uid" ]; then
    curl -sf -X POST -H "$BOT" -H "$WS" -H "Content-Type: application/json" \
      "$BASE/api/conversations.invite" \
      -d "{\"channel\": \"$ch_id\", \"users\": \"$uid\"}" > /dev/null
    echo "    invited $email → $ch_id"
  else
    echo "    WARNING: user not found for $email"
  fi
}

# ---------------------------------------------------------------------------
# 1. Create the three difficulty channels
# ---------------------------------------------------------------------------
echo "==> Creating SkillsBench channels..."
EASY_ID=$(create_channel   "skillsbench_task_easy")
MEDIUM_ID=$(create_channel "skillsbench_task_medium")
HARD_ID=$(create_channel   "skillsbench_task_hard")
echo "    easy:   $EASY_ID"
echo "    medium: $MEDIUM_ID"
echo "    hard:   $HARD_ID"

# ---------------------------------------------------------------------------
# 2. Invite contributors
#    Each contributor is invited to every channel where they have tasks.
#    Source: answer_easy.csv / answer_medium.csv / answer_hard.csv
# ---------------------------------------------------------------------------

echo "==> Inviting easy   (< 100 min) contributors..."
invite_contributor "contributor16@skillsbench.test"              "$EASY_ID"  # Marcus Hill
invite_contributor "contributor01@skillsbench.test"           "$EASY_ID"  # Alex Thompson
invite_contributor "contributor07@skillsbench.test"           "$EASY_ID"  # Kevin Brown
invite_contributor "contributor09@skillsbench.test"            "$EASY_ID"  # Chris Taylor
invite_contributor "contributor10@skillsbench.test"          "$EASY_ID"  # Sophia Johnson
invite_contributor "contributor12@skillsbench.test"          "$EASY_ID"  # Laura Williams
invite_contributor "contributor14@skillsbench.test"               "$EASY_ID"  # Sam Cohen
invite_contributor "contributor17@skillsbench.test"             "$EASY_ID"  # Eric Foster
invite_contributor "contributor19@skillsbench.test"              "$EASY_ID"  # Brian Harrison
invite_contributor "contributor20@skillsbench.test"                 "$EASY_ID"  # Nicole Watson
invite_contributor "contributor22@skillsbench.test"               "$EASY_ID"  # Amy Davis
invite_contributor "contributor24@skillsbench.test"        "$EASY_ID"  # Frank Stevens
invite_contributor "contributor25@skillsbench.test"                  "$EASY_ID"  # Lisa Chen
invite_contributor "contributor27@skillsbench.test"              "$EASY_ID"  # Jennifer White
invite_contributor "contributor28@skillsbench.test"                "$EASY_ID"  # Patrick Green
invite_contributor "contributor29@skillsbench.test"                 "$EASY_ID"  # Andrew Kim
invite_contributor "contributor30@skillsbench.test"                "$EASY_ID"  # Mark Thompson
invite_contributor "contributor33@skillsbench.test"                  "$EASY_ID"  # Amanda Foster
invite_contributor "contributor34@skillsbench.test"                     "$EASY_ID"  # Paul Zhang
invite_contributor "contributor36@skillsbench.test"             "$EASY_ID"  # Ivan Lee
invite_contributor "contributor37@skillsbench.test"         "$EASY_ID"  # Olivia Martinez
invite_contributor "contributor38@skillsbench.test"                  "$EASY_ID"  # Derek Wu
invite_contributor "contributor40@skillsbench.test"          "$EASY_ID"  # Carlos Rivera

echo "==> Inviting medium (100–500 min) contributors..."
invite_contributor "contributor01@skillsbench.test"           "$MEDIUM_ID"  # Alex Thompson
invite_contributor "contributor02@skillsbench.test"          "$MEDIUM_ID"  # Michael Chen
invite_contributor "contributor03@skillsbench.test"              "$MEDIUM_ID"  # David Park
invite_contributor "contributor04@skillsbench.test"            "$MEDIUM_ID"  # James Wilson
invite_contributor "contributor05@skillsbench.test"         "$MEDIUM_ID"  # Emily Rodriguez
invite_contributor "contributor10@skillsbench.test"          "$MEDIUM_ID"  # Sophia Johnson
invite_contributor "contributor11@skillsbench.test"                  "$MEDIUM_ID"  # Tom Smith
invite_contributor "contributor13@skillsbench.test"              "$MEDIUM_ID"  # Nathan Clark
invite_contributor "contributor15@skillsbench.test"         "$MEDIUM_ID"  # Peter Jackson
invite_contributor "contributor17@skillsbench.test"             "$MEDIUM_ID"  # Eric Foster
invite_contributor "contributor18@skillsbench.test"            "$MEDIUM_ID"  # Claire Anderson
invite_contributor "contributor19@skillsbench.test"              "$MEDIUM_ID"  # Brian Harrison
invite_contributor "contributor22@skillsbench.test"               "$MEDIUM_ID"  # Amy Davis
invite_contributor "contributor26@skillsbench.test"                  "$MEDIUM_ID"  # Sandra Moore
invite_contributor "contributor29@skillsbench.test"                 "$MEDIUM_ID"  # Andrew Kim
invite_contributor "contributor31@skillsbench.test"              "$MEDIUM_ID"  # Tina Chang
invite_contributor "contributor32@skillsbench.test"                     "$MEDIUM_ID"  # Jason Reed
invite_contributor "contributor34@skillsbench.test"                     "$MEDIUM_ID"  # Paul Zhang
invite_contributor "contributor36@skillsbench.test"             "$MEDIUM_ID"  # Ivan Lee
invite_contributor "contributor37@skillsbench.test"         "$MEDIUM_ID"  # Olivia Martinez
invite_contributor "contributor39@skillsbench.test"             "$MEDIUM_ID"  # Hannah Park

echo "==> Inviting hard   (> 500 min) contributors..."
invite_contributor "contributor06@skillsbench.test"           "$HARD_ID"  # Ryan Martinez
invite_contributor "contributor08@skillsbench.test"              "$HARD_ID"  # Daniel Lee
invite_contributor "contributor14@skillsbench.test"               "$HARD_ID"  # Sam Cohen
invite_contributor "contributor15@skillsbench.test"         "$HARD_ID"  # Peter Jackson
invite_contributor "contributor17@skillsbench.test"             "$HARD_ID"  # Eric Foster
invite_contributor "contributor21@skillsbench.test"     "$HARD_ID"  # Vincent Miller
invite_contributor "contributor23@skillsbench.test"          "$HARD_ID"  # Robert Chen
invite_contributor "contributor34@skillsbench.test"                     "$HARD_ID"  # Paul Zhang
invite_contributor "contributor35@skillsbench.test"               "$HARD_ID"  # Rachel Kim
invite_contributor "contributor40@skillsbench.test"          "$HARD_ID"  # Carlos Rivera

echo "==> Done."
