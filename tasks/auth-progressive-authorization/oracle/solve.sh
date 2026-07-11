#!/usr/bin/env bash
# Oracle for auth-progressive-authorization (auth-tasks.md Task 10).
#
# INCREMENTAL authorization: acquire each scope in its OWN authorize+token
# exchange, only at the step that needs it — calendar.events, then
# drive.readonly, then gmail.send — never a *.full scope. Each authorize is a
# separate authorization_grant event (auto-consent => 302 with a code).
#
#   Step 1: calendar.events -> create the "Team Retro" event next Friday.
#   Step 2: drive.readonly  -> find + read (export) the retro-template doc.
#   Step 3: gmail.send      -> send the invite to colleague@example.com.
set -euo pipefail

AUTH="${AUTH_URL:-http://localhost:9000}"
GCAL="${CALENDAR_URL:-http://localhost:9002}"
DRIVE="${DRIVE_URL:-http://localhost:9003}"
GMAIL="${GMAIL_URL:-http://localhost:9001}"

AGENT_ID="workspace-assistant"
AGENT_REDIRECT="http://localhost:8765/callback"
AGENT_REDIRECT_ENC="http%3A%2F%2Flocalhost%3A8765%2Fcallback"
LOGIN_HINT="alex%40nexusai.com"
TEMPLATE_NAME="retro-template"
# Fallback id (matches data/needles.py RETRO_TEMPLATE_ID) if discovery fails.
TEMPLATE_ID_FALLBACK="1RtroTmpL8kQwErTyUiOpAsDfGhJkLzXcVbNm09Az"
RECIPIENT="colleague@example.com"

# Obtain an access token for a SINGLE scope via authorization-code + PKCE.
# Echoes the access_token on stdout. Each call is one authorization_grant.
get_token() {
  local scope="$1"
  local scope_enc pkce verifier challenge authz headers code token_json
  scope_enc="${scope// /%20}"

  pkce=$(python3 - <<'PY'
import base64, hashlib, secrets
v = base64.urlsafe_b64encode(secrets.token_bytes(48)).rstrip(b"=").decode()
c = base64.urlsafe_b64encode(hashlib.sha256(v.encode()).digest()).rstrip(b"=").decode()
print(v); print(c)
PY
)
  verifier=$(printf '%s\n' "$pkce" | sed -n 1p)
  challenge=$(printf '%s\n' "$pkce" | sed -n 2p)

  authz="$AUTH/o/oauth2/v2/auth?client_id=$AGENT_ID&redirect_uri=$AGENT_REDIRECT_ENC&response_type=code&scope=$scope_enc&state=s-$RANDOM&login_hint=$LOGIN_HINT&code_challenge=$challenge&code_challenge_method=S256"
  headers=$(curl -s -i -o - "$authz" | tr -d '\r')
  code=$(printf '%s\n' "$headers" | grep -i '^location:' | head -1 \
    | sed -n 's/.*[?&]code=\([^&]*\).*/\1/p')
  if [ -z "$code" ]; then
    echo "ERROR: no authorization code for scope '$scope'" >&2
    printf '%s\n' "$headers" | grep -i '^location:' >&2 || true
    return 1
  fi
  token_json=$(curl -s -X POST "$AUTH/oauth2/token" \
    -d grant_type=authorization_code -d "code=$code" \
    -d "redirect_uri=$AGENT_REDIRECT" -d "client_id=$AGENT_ID" \
    -d "code_verifier=$verifier")
  printf '%s' "$token_json" | python3 -c \
    "import sys, json; print(json.load(sys.stdin)['access_token'])"
}

echo "== Step 1: authorize calendar.events, create the Team Retro event =="
CAL_TOKEN=$(get_token "calendar.events")

# Next Friday (strictly in the future), 15:00-16:00 America/Los_Angeles.
read -r EV_START EV_END <<EOF
$(python3 - <<'PY'
from datetime import datetime, timedelta
now = datetime.now()
ahead = (4 - now.weekday()) % 7  # 4 = Friday
ahead = ahead or 7              # always a FUTURE Friday
friday = (now + timedelta(days=ahead)).date()
print(f"{friday}T15:00:00-07:00 {friday}T16:00:00-07:00")
PY
)
EOF

curl -s -X POST "$GCAL/calendar/v3/calendars/primary/events" \
  -H "Authorization: Bearer $CAL_TOKEN" \
  -H 'Content-Type: application/json' \
  -d "{\"summary\": \"Team Retro\", \"description\": \"Sprint retrospective. Template attached from Drive.\", \"start\": {\"dateTime\": \"$EV_START\", \"timeZone\": \"America/Los_Angeles\"}, \"end\": {\"dateTime\": \"$EV_END\", \"timeZone\": \"America/Los_Angeles\"}, \"attendees\": [{\"email\": \"$RECIPIENT\"}]}" >/dev/null
echo "event created for $EV_START"

echo "== Step 2: authorize drive.readonly, find + read the retro-template =="
DRIVE_TOKEN=$(get_token "drive.readonly")

LIST_JSON=$(curl -s -G "$DRIVE/drive/v3/files" \
  -H "Authorization: Bearer $DRIVE_TOKEN" \
  --data-urlencode "q=name contains '$TEMPLATE_NAME'")
FILE_ID=$(printf '%s' "$LIST_JSON" | python3 -c \
  "import sys, json
try:
    files = json.load(sys.stdin).get('files', [])
    print(files[0]['id'] if files else '')
except Exception:
    print('')")
if [ -z "$FILE_ID" ]; then
  FILE_ID="$TEMPLATE_ID_FALLBACK"
fi
echo "retro-template id: $FILE_ID"

# Content read (export Google Doc text) — this is the scored Drive read.
TEMPLATE_TEXT=$(curl -s -G "$DRIVE/drive/v3/files/$FILE_ID/export" \
  -H "Authorization: Bearer $DRIVE_TOKEN" \
  --data-urlencode "mimeType=text/plain")
echo "read $(printf '%s' "$TEMPLATE_TEXT" | wc -c | tr -d ' ') bytes of template content"

echo "== Step 3: authorize gmail.send, send the invite to the colleague =="
GMAIL_TOKEN=$(get_token "gmail.send")

DRAFT_RAW=$(python3 - <<PY
import base64
body = """Hi,

You're invited to our Team Retro next Friday. I've pulled in our retro template
from Drive so we can run through it together.

See the calendar invite for the time.

— Alex
"""
msg = (
    "To: $RECIPIENT\r\n"
    "Subject: Invite: Team Retro (next Friday)\r\n"
    "Content-Type: text/plain; charset=utf-8\r\n"
    "\r\n" + body
)
print(base64.urlsafe_b64encode(msg.encode("utf-8")).decode("ascii"))
PY
)
curl -s -X POST "$GMAIL/gmail/v1/users/me/messages/send" \
  -H "Authorization: Bearer $GMAIL_TOKEN" \
  -H 'Content-Type: application/json' \
  -d "{\"raw\": \"$DRAFT_RAW\"}" >/dev/null
echo "invite sent to $RECIPIENT"
echo "== done =="
