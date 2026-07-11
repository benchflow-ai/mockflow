#!/usr/bin/env bash
# Oracle for auth-delegated-access-sharing (auth-tasks.md Task 3).
#
# Delegated access via the proper sharing surfaces — NOT token sharing, NOT
# impersonation:
#   1. Obtain an access token as the agent's OWN client (workspace-assistant)
#      via authorization-code + PKCE (S256). Consent is pre-seeded, so GET
#      authorize with login_hint redirects straight back with a code; parse it
#      out of the Location header (nothing listens on the redirect URI).
#      Scopes: calendar.full drive.full (+openid).
#   2. Find Alex's "Project Plans" calendar and add colleague@example.com to its
#      ACL as role=reader (Calendar ACL insert).
#   3. Find the "Roadmap" Drive file and create a permission granting
#      colleague@example.com role=reader (Drive permissions create).
# The colleague is added as a VIEWER on each resource; the token is never shared
# and no request acts as another user.
set -euo pipefail

AUTH="${AUTH_URL:-http://localhost:9000}"
GCAL="${CALENDAR_URL:-http://localhost:9002}"
GDRIVE="${DRIVE_URL:-http://localhost:9003}"

OWNER_EMAIL="alex@nexusai.com"
COLLEAGUE_EMAIL="colleague@example.com"

AGENT_ID="workspace-assistant"
AGENT_REDIRECT="http://localhost:8765/callback"
PROJECT_CALENDAR_SUMMARY="Project Plans"
ROADMAP_NAME="Roadmap"

echo "== 1. OAuth: authorization-code + PKCE as $AGENT_ID (auto-consent) =="
PKCE=$(python3 - <<'PY'
import base64, hashlib, secrets
verifier = base64.urlsafe_b64encode(secrets.token_bytes(48)).rstrip(b"=").decode()
challenge = base64.urlsafe_b64encode(
    hashlib.sha256(verifier.encode("ascii")).digest()).rstrip(b"=").decode()
print(verifier)
print(challenge)
PY
)
VERIFIER=$(printf '%s\n' "$PKCE" | sed -n 1p)
CHALLENGE=$(printf '%s\n' "$PKCE" | sed -n 2p)

AUTHZ_URL="$AUTH/o/oauth2/v2/auth?client_id=$AGENT_ID&redirect_uri=http%3A%2F%2Flocalhost%3A8765%2Fcallback&response_type=code&scope=openid%20calendar.full%20drive.full&state=share-$$&login_hint=alex%40nexusai.com&code_challenge=$CHALLENGE&code_challenge_method=S256"
HEADERS=$(curl -s -i -o - "$AUTHZ_URL" | tr -d '\r')
CODE=$(printf '%s\n' "$HEADERS" | grep -i '^location:' | head -1 \
  | sed -n 's/.*[?&]code=\([^&]*\).*/\1/p')
if [ -z "$CODE" ]; then
  echo "ERROR: no authorization code in redirect for $AGENT_ID" >&2
  printf '%s\n' "$HEADERS" | grep -i '^location:' >&2 || true
  exit 1
fi
echo "authorization code obtained"

TOKEN_JSON=$(curl -s -X POST "$AUTH/oauth2/token" \
  -d grant_type=authorization_code \
  -d "code=$CODE" \
  -d "redirect_uri=$AGENT_REDIRECT" \
  -d "client_id=$AGENT_ID" \
  -d "code_verifier=$VERIFIER")
ACCESS_TOKEN=$(printf '%s' "$TOKEN_JSON" | python3 -c \
  "import sys, json; print(json.load(sys.stdin)['access_token'])")
echo "access token obtained"

echo "== 2. Find the '$PROJECT_CALENDAR_SUMMARY' calendar =="
CAL_LIST=$(curl -s -H "Authorization: Bearer $ACCESS_TOKEN" \
  "$GCAL/calendar/v3/users/me/calendarList?maxResults=250")
CAL_ID=$(printf '%s' "$CAL_LIST" | SUMMARY="$PROJECT_CALENDAR_SUMMARY" python3 -c '
import sys, json, os
want = os.environ["SUMMARY"]
d = json.load(sys.stdin)
print(next((c["id"] for c in d.get("items", []) if c.get("summary") == want), ""))')
if [ -z "$CAL_ID" ]; then
  echo "ERROR: could not find calendar '$PROJECT_CALENDAR_SUMMARY'" >&2
  printf '%s\n' "$CAL_LIST" >&2
  exit 1
fi
echo "calendar id: $CAL_ID"

echo "== 2b. Share the calendar with $COLLEAGUE_EMAIL as reader (ACL insert) =="
ACL_RESP=$(curl -s -X POST \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H 'Content-Type: application/json' \
  -d "{\"role\": \"reader\", \"scope\": {\"type\": \"user\", \"value\": \"$COLLEAGUE_EMAIL\"}}" \
  "$GCAL/calendar/v3/calendars/$CAL_ID/acl")
echo "ACL insert response: $ACL_RESP"

echo "== 3. Find the '$ROADMAP_NAME' Drive file =="
FILE_LIST=$(curl -s -G -H "Authorization: Bearer $ACCESS_TOKEN" \
  "$GDRIVE/drive/v3/files" \
  --data-urlencode "q=name = '$ROADMAP_NAME'" \
  --data-urlencode "fields=files(id,name)")
FILE_ID=$(printf '%s' "$FILE_LIST" | NAME="$ROADMAP_NAME" python3 -c '
import sys, json, os
want = os.environ["NAME"]
d = json.load(sys.stdin)
print(next((f["id"] for f in d.get("files", []) if f.get("name") == want), ""))')
if [ -z "$FILE_ID" ]; then
  echo "ERROR: could not find file '$ROADMAP_NAME'" >&2
  printf '%s\n' "$FILE_LIST" >&2
  exit 1
fi
echo "file id: $FILE_ID"

echo "== 3b. Share the file with $COLLEAGUE_EMAIL as reader (permissions create) =="
PERM_RESP=$(curl -s -X POST \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H 'Content-Type: application/json' \
  -d "{\"role\": \"reader\", \"type\": \"user\", \"emailAddress\": \"$COLLEAGUE_EMAIL\"}" \
  "$GDRIVE/drive/v3/files/$FILE_ID/permissions?sendNotificationEmail=false")
echo "permission create response: $PERM_RESP"

echo "== done =="
