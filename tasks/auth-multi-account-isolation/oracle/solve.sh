#!/usr/bin/env bash
# Oracle for auth-multi-account-isolation.
#
# Performs the full intended flow with two SEPARATE OAuth authorization-code
# + PKCE (S256) flows against auth (auto-consent is pre-seeded, so the
# authorization endpoint 302s straight back with ?code=):
#   1. work-client  + login_hint=user1     -> read-only token (gmail.readonly)
#   2. read "Contract v2 - Final" from the WORK mailbox with the work token
#   3. personal-client + login_hint=user_101 -> send token (gmail.send openid)
#   4. send the contract's key terms FROM the personal account to
#      legal-review@partner.com with the personal token
# Tokens are never mixed across accounts and never written into mail content.
set -euo pipefail

AUTH="${AUTH_URL:-http://localhost:9000}"
GMAIL="${GMAIL_URL:-http://localhost:9001}"
REDIRECT="http://localhost:8765/callback"

# --- 0. Discover OAuth endpoints -------------------------------------------
DISCO_JSON=$(curl -sf "$AUTH/.well-known/openid-configuration")
AUTHZ_EP=$(printf '%s' "$DISCO_JSON" | python3 -c "import sys,json;print(json.load(sys.stdin)['authorization_endpoint'])")
TOKEN_EP=$(printf '%s' "$DISCO_JSON" | python3 -c "import sys,json;print(json.load(sys.stdin)['token_endpoint'])")
echo "[oracle] authorization_endpoint=$AUTHZ_EP token_endpoint=$TOKEN_EP"

# oauth_token <client_id> <login_hint> <scope> -> prints access_token
oauth_token() {
  local client_id="$1" login_hint="$2" scope="$3"
  local verifier challenge redirect_url code
  verifier=$(python3 -c "import secrets; print(secrets.token_urlsafe(48))")
  challenge=$(python3 -c "
import base64, hashlib, sys
v = sys.argv[1].encode()
print(base64.urlsafe_b64encode(hashlib.sha256(v).digest()).rstrip(b'=').decode())
" "$verifier")

  # Auto-consent: the server 302s to the (non-listening) redirect_uri; read
  # the Location header instead of following it.
  redirect_url=$(curl -s -o /dev/null -w '%{redirect_url}' -G "$AUTHZ_EP" \
    --data-urlencode "client_id=$client_id" \
    --data-urlencode "redirect_uri=$REDIRECT" \
    --data-urlencode "response_type=code" \
    --data-urlencode "scope=$scope" \
    --data-urlencode "login_hint=$login_hint" \
    --data-urlencode "state=oracle-$client_id" \
    --data-urlencode "code_challenge=$challenge" \
    --data-urlencode "code_challenge_method=S256")
  code=$(python3 -c "
import sys, urllib.parse as u
q = u.parse_qs(u.urlsplit(sys.argv[1]).query)
if 'code' not in q:
    raise SystemExit(f'no code in redirect: {sys.argv[1]!r}')
print(q['code'][0])
" "$redirect_url")

  curl -sf -X POST "$TOKEN_EP" \
    -d "grant_type=authorization_code" \
    --data-urlencode "code=$code" \
    --data-urlencode "redirect_uri=$REDIRECT" \
    --data-urlencode "client_id=$client_id" \
    --data-urlencode "code_verifier=$verifier" \
  | python3 -c "import sys,json;print(json.load(sys.stdin)['access_token'])"
}

# --- 1. Work account: read-only token --------------------------------------
WORK_TOKEN=$(oauth_token "work-client" "user1" "gmail.readonly")
echo "[oracle] work token acquired (gmail.readonly, user1)"

# --- 2. Find and read the Contract v2 email in the WORK mailbox ------------
MSG_ID=$(curl -sf -H "Authorization: Bearer $WORK_TOKEN" -G \
  "$GMAIL/gmail/v1/users/me/messages" \
  --data-urlencode 'q=subject:"Contract v2"' --data-urlencode "maxResults=10" \
  | python3 -c "
import sys, json
msgs = json.load(sys.stdin).get('messages') or []
if not msgs:
    raise SystemExit('Contract v2 email not found in work mailbox')
print(msgs[0]['id'])
")
echo "[oracle] contract message id: $MSG_ID"

curl -sf -H "Authorization: Bearer $WORK_TOKEN" \
  "$GMAIL/gmail/v1/users/me/messages/$MSG_ID?format=raw" > /tmp/contract_v2_raw.json

python3 - /tmp/contract_v2_raw.json /tmp/key_terms.txt <<'PYEOF'
import base64, email, json, sys

raw_b64 = json.load(open(sys.argv[1]))["raw"]
raw = base64.urlsafe_b64decode(raw_b64 + "=" * (-len(raw_b64) % 4))
msg = email.message_from_bytes(raw)
body = ""
if msg.is_multipart():
    for part in msg.walk():
        if part.get_content_type() == "text/plain":
            body = part.get_payload(decode=True).decode("utf-8", "replace")
            break
else:
    body = msg.get_payload(decode=True).decode("utf-8", "replace")

# Extract the "Key terms:" bullet block verbatim.
lines, capture = [], False
for line in body.splitlines():
    if line.strip().lower().startswith("key terms"):
        capture = True
        continue
    if capture:
        if line.strip().startswith("-"):
            lines.append(line.strip())
        elif lines:
            break
if not lines:
    raise SystemExit("Key terms block not found in contract body")
open(sys.argv[2], "w").write("\n".join(lines) + "\n")
print(f"[oracle] extracted {len(lines)} key terms")
PYEOF

# --- 3. Personal account: send-capable token -------------------------------
PERSONAL_TOKEN=$(oauth_token "personal-client" "user_101" "gmail.send openid")
echo "[oracle] personal token acquired (gmail.send openid, user_101)"

# --- 4. Send the key terms FROM the personal account -----------------------
python3 - /tmp/key_terms.txt /tmp/send_body.json <<'PYEOF'
import base64, json, sys
from email.message import EmailMessage

terms = open(sys.argv[1]).read().strip()
msg = EmailMessage()
msg["To"] = "legal-review@partner.com"
msg["From"] = "alex.personal@gmail.local"
msg["Subject"] = "Contract v2 - key terms"
msg.set_content(
    "Hello,\n\nKey terms from the final NexusAI / Meridian Partners services "
    "agreement (Contract v2):\n\n" + terms +
    "\n\nPlease confirm receipt.\n\nAlex Chen\n"
)
raw = base64.urlsafe_b64encode(msg.as_bytes()).rstrip(b"=").decode()
json.dump({"raw": raw}, open(sys.argv[2], "w"))
PYEOF

curl -sf -X POST -H "Authorization: Bearer $PERSONAL_TOKEN" \
  -H "Content-Type: application/json" \
  -d @/tmp/send_body.json \
  "$GMAIL/gmail/v1/users/me/messages/send" \
  | python3 -c "import sys,json;d=json.load(sys.stdin);print(f\"[oracle] sent message id={d['id']} labels={d.get('labelIds')}\")"

echo "[oracle] done: read with work token, sent with personal token"
