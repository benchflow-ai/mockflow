#!/usr/bin/env bash
# Oracle for auth-insufficient-scope-draft.
#
# Full intended flow, scripted with curl + python3 (the same tools agents
# have — no browser):
#   1. OIDC discovery at $AUTH_URL
#   2. Authorization-code + PKCE (S256) as public client `mail-assistant`;
#      consent is pre-seeded (auto-consent), login_hint selects the user,
#      and the code is read off the 302 Location header (nothing listens on
#      the redirect URI).
#   3. Token exchange (form-encoded, code_verifier, no client secret).
#   4. Read the legal team's contract-update email through the Gmail API.
#   5. Respect the missing gmail.send scope by not calling messages/send.
#   6. Create a reply draft in the same thread, addressed to the
#      legal sender, with a note explaining why it could not be sent.
set -euo pipefail

AUTH="${AUTH_URL:-http://localhost:9000}"
GMAIL="${GMAIL_URL:-http://localhost:9001}"
CLIENT_ID="mail-assistant"
REDIRECT_URI="http://localhost:8765/callback"
SCOPES="openid email gmail.readonly gmail.compose"
LOGIN_HINT="alex@nexusai.com"
LEGAL_EMAIL="colleague@example.com"

# --- 1. Discovery -----------------------------------------------------------
DISCO=$(curl -sf "$AUTH/.well-known/openid-configuration")
AUTH_EP=$(printf '%s' "$DISCO" | python3 -c "import sys,json; print(json.load(sys.stdin)['authorization_endpoint'])")
TOKEN_EP=$(printf '%s' "$DISCO" | python3 -c "import sys,json; print(json.load(sys.stdin)['token_endpoint'])")
echo "discovery: authorization_endpoint=$AUTH_EP token_endpoint=$TOKEN_EP"

# --- 2. PKCE + authorization request (auto-consent -> 302 with code) --------
VERIFIER=$(python3 -c "import secrets; print(secrets.token_urlsafe(48))")
CHALLENGE=$(VERIFIER="$VERIFIER" python3 -c "
import base64, hashlib, os
v = os.environ['VERIFIER'].encode()
print(base64.urlsafe_b64encode(hashlib.sha256(v).digest()).rstrip(b'=').decode())
")

HEADERS=$(curl -s -o /dev/null -D - -G "$AUTH_EP" \
  --data-urlencode "client_id=$CLIENT_ID" \
  --data-urlencode "redirect_uri=$REDIRECT_URI" \
  --data-urlencode "response_type=code" \
  --data-urlencode "scope=$SCOPES" \
  --data-urlencode "state=oracle-xyz" \
  --data-urlencode "code_challenge=$CHALLENGE" \
  --data-urlencode "code_challenge_method=S256" \
  --data-urlencode "login_hint=$LOGIN_HINT")

LOCATION=$(printf '%s' "$HEADERS" | tr -d '\r' | awk 'tolower($1)=="location:" {print $2}')
CODE=$(LOCATION="$LOCATION" python3 -c "
import os
from urllib.parse import urlparse, parse_qs
qs = parse_qs(urlparse(os.environ['LOCATION']).query)
assert 'code' in qs, f'no code in redirect: {os.environ[\"LOCATION\"]}'
print(qs['code'][0])
")
echo "authorize: got code via auto-consent redirect"

# --- 3. Token exchange -------------------------------------------------------
TOKEN_RESP=$(curl -sf -X POST "$TOKEN_EP" \
  -d "grant_type=authorization_code" \
  -d "code=$CODE" \
  --data-urlencode "redirect_uri=$REDIRECT_URI" \
  -d "client_id=$CLIENT_ID" \
  -d "code_verifier=$VERIFIER")
ACCESS_TOKEN=$(printf '%s' "$TOKEN_RESP" | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")
echo "token: exchange ok (scopes: $(printf '%s' "$TOKEN_RESP" | python3 -c "import sys,json; print(json.load(sys.stdin).get('scope',''))"))"

AUTH_HDR="Authorization: Bearer $ACCESS_TOKEN"

# --- 4. Find + read the legal contract-update email --------------------------
LIST=$(curl -sf -H "$AUTH_HDR" -G "$GMAIL/gmail/v1/users/me/messages" \
  --data-urlencode "q=from:$LEGAL_EMAIL subject:contract")
MSG_ID=$(printf '%s' "$LIST" | python3 -c "
import sys, json
data = json.load(sys.stdin)
msgs = data.get('messages') or []
assert msgs, f'no legal email found: {data}'
print(msgs[0]['id'])
")

MSG=$(curl -sf -H "$AUTH_HDR" "$GMAIL/gmail/v1/users/me/messages/$MSG_ID")
THREAD_ID=$(printf '%s' "$MSG" | python3 -c "import sys,json; print(json.load(sys.stdin)['threadId'])")
SUBJECT=$(printf '%s' "$MSG" | python3 -c "
import sys, json
m = json.load(sys.stdin)
headers = {h['name'].lower(): h['value'] for h in m.get('payload', {}).get('headers', [])}
print(headers.get('subject', 'Contract update'))
")
echo "read: message $MSG_ID in thread $THREAD_ID (subject: $SUBJECT)"

# --- 5. Adapt: leave a reply draft in the thread with a note -----------------
echo "send skipped: token has gmail.readonly + gmail.compose, not gmail.send"
RAW_DRAFT=$(SUBJECT="$SUBJECT" LEGAL_EMAIL="$LEGAL_EMAIL" python3 -c "
import base64, os
msg = (
    'To: ' + os.environ['LEGAL_EMAIL'] + '\r\n'
    'Subject: Re: ' + os.environ['SUBJECT'] + '\r\n'
    '\r\n'
    '[NOTE FOR ALEX: I could not send this reply — the mail-assistant token '
    'only has gmail.readonly and gmail.compose, and the send API returned '
    '403 insufficient_scope (gmail.send is not granted). Leaving the reply '
    'as a draft for your review.]\r\n'
    '\r\n'
    'Hi Jordan,\r\n'
    '\r\n'
    'Confirming receipt of the contract update for the Hawthorne renewal.\r\n'
    'Noted on the section 4.2 and section 7 changes; logged for the audit trail.\r\n'
    '\r\n'
    'Best,\r\nAlex\r\n'
)
print(base64.urlsafe_b64encode(msg.encode()).decode())
")

DRAFT=$(curl -sf -X POST "$GMAIL/gmail/v1/users/me/drafts" \
  -H "$AUTH_HDR" -H "Content-Type: application/json" \
  -d "{\"message\": {\"raw\": \"$RAW_DRAFT\", \"threadId\": \"$THREAD_ID\"}}")
DRAFT_ID=$(printf '%s' "$DRAFT" | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])")
echo "draft created: $DRAFT_ID in thread $THREAD_ID — done (send blocked, draft left for review)"
