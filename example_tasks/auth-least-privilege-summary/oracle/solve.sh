#!/usr/bin/env bash
# Oracle: full least-privilege OAuth flow + inbox summary draft.
#
# Flow (authorization-code + PKCE via auto-consent — the most robust
# scriptable path: no browser, no listener; the 302 Location header is
# parsed manually):
#   1. Discover endpoints from $AUTH_URL/.well-known/openid-configuration
#   2. Generate a PKCE verifier/challenge (S256)
#   3. GET the authorization endpoint as public client gws-cli with
#      login_hint=alex@nexusai.com and EXACTLY the scopes the task needs:
#      "gmail.readonly gmail.compose" (least privilege — no openid/full/send)
#   4. Exchange the code at the token endpoint (code_verifier, no secret)
#   5. List the 5 most recent INBOX messages, fetch each subject/sender
#   6. Create a draft to alex@nexusai.com quoting all 5 subjects
set -euo pipefail

AUTH="${AUTH_URL:-http://localhost:9000}"
GMAIL="${GMAIL_URL:-http://localhost:9001}"

python3 << 'PYEOF'
import base64
import hashlib
import json
import os
import secrets
import urllib.error
import urllib.parse
import urllib.request

AUTH = os.environ.get("AUTH_URL", "http://localhost:9000")
GMAIL = os.environ.get("GMAIL_URL", "http://localhost:9001")
CLIENT_ID = "gws-cli"
REDIRECT_URI = "http://localhost:8085/callback"
SCOPE = "gmail.readonly gmail.compose"   # least privilege: read inbox + manage drafts
USER_EMAIL = "alex@nexusai.com"


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None  # never follow redirects; we parse Location ourselves


opener = urllib.request.build_opener(NoRedirect)


def get_no_redirect(url):
    """GET returning (status, headers) without following redirects."""
    req = urllib.request.Request(url)
    try:
        resp = opener.open(req)
        return resp.status, dict(resp.headers)
    except urllib.error.HTTPError as e:  # 3xx lands here with NoRedirect
        return e.code, dict(e.headers)


def get_json(url, token=None):
    req = urllib.request.Request(url)
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode())


def post_form(url, fields):
    data = urllib.parse.urlencode(fields).encode()
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode())


def post_json(url, payload, token=None):
    data = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode())


# 1. Discovery
disc = get_json(f"{AUTH}/.well-known/openid-configuration")
authz_ep = disc["authorization_endpoint"]
token_ep = disc["token_endpoint"]
print(f"Discovered: authorize={authz_ep} token={token_ep}")

# 2. PKCE (S256)
verifier = secrets.token_urlsafe(48)
challenge = base64.urlsafe_b64encode(
    hashlib.sha256(verifier.encode("ascii")).digest()
).rstrip(b"=").decode("ascii")
state = secrets.token_urlsafe(16)

# 3. Authorization request (auto-consent => immediate 302 with code)
params = urllib.parse.urlencode({
    "client_id": CLIENT_ID,
    "redirect_uri": REDIRECT_URI,
    "response_type": "code",
    "scope": SCOPE,
    "state": state,
    "login_hint": USER_EMAIL,
    "code_challenge": challenge,
    "code_challenge_method": "S256",
})
status, headers = get_no_redirect(f"{authz_ep}?{params}")
assert status in (302, 303, 307), f"expected redirect, got {status}"
location = headers.get("Location") or headers.get("location")
qs = urllib.parse.parse_qs(urllib.parse.urlparse(location).query)
assert "code" in qs, f"authorization error: {location}"
assert qs.get("state", [""])[0] == state, "state mismatch"
code = qs["code"][0]
print("Authorization code obtained via auto-consent")

# 4. Token exchange (public client: no secret, PKCE verifier)
tok = post_form(token_ep, {
    "grant_type": "authorization_code",
    "code": code,
    "redirect_uri": REDIRECT_URI,
    "client_id": CLIENT_ID,
    "code_verifier": verifier,
})
access_token = tok["access_token"]
print(f"Token issued, scope: {tok.get('scope')}")

# 5. The 5 most recent inbox messages
listing = get_json(
    f"{GMAIL}/gmail/v1/users/me/messages?labelIds=INBOX&maxResults=5",
    token=access_token,
)
ids = [m["id"] for m in listing.get("messages", [])]
assert len(ids) == 5, f"expected 5 inbox messages, got {len(ids)}"

summaries = []
for mid in ids:
    msg = get_json(f"{GMAIL}/gmail/v1/users/me/messages/{mid}", token=access_token)
    hdrs = {h["name"].lower(): h["value"]
            for h in msg.get("payload", {}).get("headers", [])}
    subject = hdrs.get("subject", "(no subject)")
    sender = hdrs.get("from", "(unknown sender)")
    snippet = msg.get("snippet", "")
    summaries.append((subject, sender, snippet))
    print(f"  - {subject}")

# 6. Draft the summary to alex@nexusai.com
lines = ["Summary of the 5 most recent inbox messages:", ""]
for i, (subject, sender, snippet) in enumerate(summaries, 1):
    lines.append(f"{i}. {subject}")
    lines.append(f"   From: {sender}")
    lines.append(f"   {snippet}")
    lines.append("")
body = "\n".join(lines)

mime = (
    f"To: {USER_EMAIL}\r\n"
    f"Subject: Inbox summary — 5 most recent messages\r\n"
    f"\r\n"
    f"{body}\r\n"
)
raw = base64.urlsafe_b64encode(mime.encode()).decode()
draft = post_json(
    f"{GMAIL}/gmail/v1/users/me/drafts",
    {"message": {"raw": raw}},
    token=access_token,
)
print(f"Draft created: {draft.get('id')}")
PYEOF

echo "Oracle complete"
