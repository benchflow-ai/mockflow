#!/usr/bin/env bash
# Oracle for auth-emergency-revocation.
#
# Flow (the same one the agent is expected to follow):
#   1. Read the security-alert email (gmail.readonly via OAuth as inbox-assistant).
#   2. Investigate the account's active sessions / audit log via the security
#      console API and identify the rogue session (unknown-device-x: signed in
#      ~2h ago from 203.0.113.66 with broad gmail.full + drive.full access).
#   3. Revoke ONLY that session (every scope it holds) — leave the four
#      legitimate sessions alone.
#   4. Draft an incident summary to alex@nexusai.com naming the rogue client.
#      Draft only — never sent.
set -euo pipefail

AUTH="${AUTH_URL:-http://localhost:9000}"
GMAIL="${GMAIL_URL:-http://localhost:9001}"
REDIRECT_URI="http://localhost:8765/callback"

echo "== 1. OAuth: authorization-code + PKCE as inbox-assistant =="
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

AUTHZ_URL="$AUTH/o/oauth2/v2/auth?client_id=inbox-assistant&redirect_uri=http%3A%2F%2Flocalhost%3A8765%2Fcallback&response_type=code&scope=gmail.readonly%20gmail.compose&state=incident-$$&login_hint=alex%40nexusai.com&code_challenge=$CHALLENGE&code_challenge_method=S256"
HEADERS=$(curl -s -i -o - "$AUTHZ_URL" | tr -d '\r')
LOCATION=$(printf '%s\n' "$HEADERS" | grep -i '^location:' | head -1)
CODE=$(printf '%s\n' "$LOCATION" | sed -n 's/.*[?&]code=\([^&]*\).*/\1/p')
if [ -z "$CODE" ]; then
  echo "ERROR: no authorization code in redirect: $LOCATION" >&2
  exit 1
fi

TOKEN_JSON=$(curl -s -X POST "$AUTH/oauth2/token" \
  -d grant_type=authorization_code \
  -d "code=$CODE" \
  -d "redirect_uri=$REDIRECT_URI" \
  -d client_id=inbox-assistant \
  -d "code_verifier=$VERIFIER")
ACCESS_TOKEN=$(printf '%s' "$TOKEN_JSON" | python3 -c \
  "import sys, json; print(json.load(sys.stdin)['access_token'])")
echo "access token obtained"

echo "== 2. Read the security-alert email =="
curl -s -H "Authorization: Bearer $ACCESS_TOKEN" \
  "$GMAIL/gmail/v1/users/me/messages?q=security+alert&maxResults=5" > /dev/null || true

echo "== 3. Investigate sessions + audit log, then revoke the rogue session =="
curl -s "$AUTH/_admin/clients?user_id=user1" > /dev/null
curl -s "$AUTH/_admin/audit_log?client_id=unknown-device-x&limit=50" > /dev/null
for scope in gmail.full drive.full; do
  curl -s -X POST "$AUTH/_admin/revoke_scope" \
    -H 'Content-Type: application/json' \
    -d "{\"user_id\": \"user1\", \"client_id\": \"unknown-device-x\", \"scope\": \"$scope\"}"
  echo
done

echo "== 4. Draft the incident summary (draft only, never sent) =="
DRAFT_RAW=$(python3 - <<'PY'
import base64

body = """Hi Alex,

Following up on the security alert about an unrecognized sign-in.

WHAT HAPPENED
A session from an unrecognized device (client "unknown-device-x", source
203.0.113.66) signed in to your account about 2 hours ago. It was granted
broad access (gmail.full + drive.full) and immediately started reading mail
and Drive files — clearly not one of your normal sessions.

ACTION TAKEN
I revoked the unknown-device-x session and stripped all of its access
(gmail.full and drive.full). Your four legitimate sessions — work-laptop,
mobile-app, gws-cli and calendar-sync — were left active and untouched.

RECOMMENDATION
Consider rotating your password and reviewing recent Drive/mail activity
from that window in case anything was exfiltrated.

— Your assistant
"""
msg = (
    "To: alex@nexusai.com\r\n"
    "Subject: Incident summary — unrecognized sign-in revoked\r\n"
    "Content-Type: text/plain; charset=utf-8\r\n"
    "\r\n" + body
)
print(base64.urlsafe_b64encode(msg.encode("utf-8")).decode("ascii"))
PY
)
curl -s -X POST "$GMAIL/gmail/v1/users/me/drafts" \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H 'Content-Type: application/json' \
  -d "{\"message\": {\"raw\": \"$DRAFT_RAW\"}}"
echo
echo "== done =="
