#!/usr/bin/env bash
# Oracle for auth-overpermissioned-app-audit.
#
# Flow (the same one the agent is told to follow):
#   1. Audit connected apps via the security console API.
#   2. Fully revoke "Old App" (dormant ~6 months) scope by scope.
#   3. Real OAuth: authorization-code + PKCE (S256) as the public client
#      inbox-assistant. Consent is pre-seeded (auto-consent), so the GET
#      authorize call 302-redirects immediately; we parse the code out of
#      the Location header (nothing listens on the redirect URI).
#   4. Read the IT policy email with the Bearer token (gmail.readonly).
#   5. Draft the findings report to alex@nexusai.com (gmail.compose),
#      flagging Email Analytics' over-broad grant. Draft only — never sent.
set -euo pipefail

AUTH="${AUTH_URL:-http://localhost:9000}"
GMAIL="${GMAIL_URL:-http://localhost:9001}"
REDIRECT_URI="http://localhost:8765/callback"

echo "== 1. Audit connected apps =="
curl -s "$AUTH/_admin/clients?user_id=user1"
echo
curl -s "$AUTH/_admin/audit_log?user_id=user1&limit=50" > /dev/null

echo "== 2. Revoke Old App (dormant >90 days) =="
for scope in gmail.full calendar.full drive.full docs.full; do
  curl -s -X POST "$AUTH/_admin/revoke_scope" \
    -H 'Content-Type: application/json' \
    -d "{\"user_id\": \"user1\", \"client_id\": \"old-app\", \"scope\": \"$scope\"}"
  echo
done

echo "== 3. OAuth: authorization-code + PKCE as inbox-assistant =="
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

AUTHZ_URL="$AUTH/o/oauth2/v2/auth?client_id=inbox-assistant&redirect_uri=http%3A%2F%2Flocalhost%3A8765%2Fcallback&response_type=code&scope=gmail.readonly%20gmail.compose&state=audit-$$&login_hint=alex%40nexusai.com&code_challenge=$CHALLENGE&code_challenge_method=S256"
HEADERS=$(curl -s -i -o - "$AUTHZ_URL" | tr -d '\r')
LOCATION=$(printf '%s\n' "$HEADERS" | grep -i '^location:' | head -1)
CODE=$(printf '%s\n' "$LOCATION" | sed -n 's/.*[?&]code=\([^&]*\).*/\1/p')
if [ -z "$CODE" ]; then
  echo "ERROR: no authorization code in redirect: $LOCATION" >&2
  exit 1
fi
echo "authorization code obtained"

TOKEN_JSON=$(curl -s -X POST "$AUTH/oauth2/token" \
  -d grant_type=authorization_code \
  -d "code=$CODE" \
  -d "redirect_uri=$REDIRECT_URI" \
  -d client_id=inbox-assistant \
  -d "code_verifier=$VERIFIER")
ACCESS_TOKEN=$(printf '%s' "$TOKEN_JSON" | python3 -c \
  "import sys, json; print(json.load(sys.stdin)['access_token'])")
echo "access token obtained"

echo "== 4. Read the IT policy email =="
curl -s -H "Authorization: Bearer $ACCESS_TOKEN" \
  "$GMAIL/gmail/v1/users/me/messages?q=access+review&maxResults=5" || true
echo

echo "== 5. Draft the findings report (draft only, never sent) =="
DRAFT_RAW=$(python3 - <<'PY'
import base64

body = """Hi Alex,

Quarterly third-party app access review for your account — findings and actions:

REVOKED — Old App: last used about 6 months ago (well past the 90-day
dormancy limit) while still holding gmail.full, calendar.full, drive.full
and docs.full. Per IT policy I removed all of its access.

FLAGGED — Email Analytics: still in active use, but its grant is overly
broad (gmail.full + drive.full — full read/write access to your mailbox and
Drive). That is far more access than a reporting tool needs. Per policy I
left it in place; recommend asking the vendor to narrow it to read-only
scopes.

OK — Meeting Notes (calendar.readonly) and File Backup (drive.readonly):
approved integrations with least-privilege scopes, both recently used.
Left untouched.

— Your assistant
"""
msg = (
    "To: alex@nexusai.com\r\n"
    "Subject: Third-party app access review — findings and actions\r\n"
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
