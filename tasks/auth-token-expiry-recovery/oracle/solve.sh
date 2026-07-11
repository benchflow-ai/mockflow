#!/usr/bin/env bash
# Oracle for auth-token-expiry-recovery.
#
# Full intended flow, scripted with python3 stdlib only (agents get curl +
# python, no browser):
#   1. OIDC discovery at $AUTH_URL/.well-known/openid-configuration
#   2. authorization_code grant for confidential client "expiry-client"
#      (auto-consent is pre-seeded; login_hint selects user1; the redirect is
#      NOT followed — the code is parsed from the Location header; PKCE is not
#      required for confidential clients on this server)
#   3. create labels Internal/External, classify all inbox mail by sender
#      domain, label the first half
#   4. demonstrate expiry recovery: obtain a deliberately short-lived (1s)
#      access token for the same client/user via /_admin/issue_token, use it
#      after it expires -> genuine 401 + token_expired_during_use audit event.
#      NOTE: the mission sketch suggested /_admin/expire_token, but that only
#      flips the SERVER-SIDE record (introspection); gmail validates the
#      JWT exp claim OFFLINE, so an expire_token'd JWT still works. A 1-second
#      real JWT is the fast, robust way to hit the offline-expiry path without
#      sleeping out the full 90s client TTL.
#   5. recover via grant_type=refresh_token (-> token_refreshed audit event +
#      rotation in the refresh_tokens table), then label the remaining half
#      with the fresh access token and verify.
set -euo pipefail

python3 << 'PYEOF'
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

AUTH = os.environ.get("AUTH_URL", "http://localhost:9000").rstrip("/")
GMAIL = os.environ.get("GMAIL_URL", "http://localhost:9001").rstrip("/")

CLIENT_ID = "expiry-client"
CLIENT_SECRET = "client-secret"
REDIRECT_URI = "http://localhost:8765/callback"
SCOPES = "openid gmail.modify gmail.labels"
USER_EMAIL = "alex@nexusai.com"
INTERNAL_DOMAIN = "nexusai.com"


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


_opener = urllib.request.build_opener(NoRedirect)


def http(method, url, *, headers=None, data=None, form=None, expect_error=False):
    """Tiny stdlib HTTP helper. Returns (status, headers, parsed-or-raw body)."""
    body = None
    hdrs = dict(headers or {})
    if form is not None:
        body = urllib.parse.urlencode(form).encode()
        hdrs["Content-Type"] = "application/x-www-form-urlencoded"
    elif data is not None:
        body = json.dumps(data).encode()
        hdrs["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=body, headers=hdrs, method=method)
    try:
        with _opener.open(req, timeout=30) as resp:
            raw = resp.read().decode()
            status, rheaders = resp.status, dict(resp.headers)
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        status, rheaders = e.code, dict(e.headers)
        if not expect_error and status >= 400 and status not in (301, 302, 303, 307):
            print(f"FATAL: {method} {url} -> {status}: {raw[:500]}", file=sys.stderr)
            sys.exit(1)
    try:
        parsed = json.loads(raw) if raw else {}
    except ValueError:
        parsed = raw
    return status, rheaders, parsed


def gmail_api(method, path, token, *, data=None, expect_error=False):
    return http(method, f"{GMAIL}{path}",
                headers={"Authorization": f"Bearer {token}"},
                data=data, expect_error=expect_error)


# --- 1. discovery -----------------------------------------------------------
_, _, disc = http("GET", f"{AUTH}/.well-known/openid-configuration")
auth_ep = disc["authorization_endpoint"]
token_ep = disc["token_endpoint"]
print(f"[oracle] discovery ok: authorize={auth_ep} token={token_ep}")

# --- 2. authorization_code flow (auto-consent, no redirect following) -------
qs = urllib.parse.urlencode({
    "response_type": "code",
    "client_id": CLIENT_ID,
    "redirect_uri": REDIRECT_URI,
    "scope": SCOPES,
    "state": "oracle-state-42",
    "login_hint": USER_EMAIL,
})
status, rheaders, _ = http("GET", f"{auth_ep}?{qs}", expect_error=True)
assert status in (302, 303, 307), f"expected auto-consent redirect, got {status}"
location = rheaders.get("Location") or rheaders.get("location")
loc_qs = urllib.parse.parse_qs(urllib.parse.urlparse(location).query)
assert "code" in loc_qs, f"no code in redirect: {location}"
assert loc_qs.get("state") == ["oracle-state-42"], "state mismatch"
code = loc_qs["code"][0]
print("[oracle] got authorization code via auto-consent")

_, _, tok = http("POST", token_ep, form={
    "grant_type": "authorization_code",
    "code": code,
    "redirect_uri": REDIRECT_URI,
    "client_id": CLIENT_ID,
    "client_secret": CLIENT_SECRET,
})
access_token = tok["access_token"]
refresh_token = tok["refresh_token"]
assert tok.get("expires_in") == 90, f"expected 90s client TTL, got {tok.get('expires_in')}"
print(f"[oracle] token exchange ok (expires_in={tok['expires_in']})")

# --- 3. labels + classification + first half --------------------------------
_, _, lab_int = gmail_api("POST", "/gmail/v1/users/me/labels", access_token,
                          data={"name": "Internal"})
_, _, lab_ext = gmail_api("POST", "/gmail/v1/users/me/labels", access_token,
                          data={"name": "External"})
internal_label, external_label = lab_int["id"], lab_ext["id"]
print(f"[oracle] labels created: Internal={internal_label} External={external_label}")

_, _, listing = gmail_api(
    "GET", "/gmail/v1/users/me/messages?maxResults=500&labelIds=INBOX", access_token)
ids = [m["id"] for m in listing.get("messages", [])]
print(f"[oracle] inbox messages: {len(ids)}")

def classify(msg_id, token):
    _, _, msg = gmail_api(
        "GET", f"/gmail/v1/users/me/messages/{msg_id}?format=metadata", token)
    sender = ""
    for h in msg.get("payload", {}).get("headers", []):
        if h.get("name", "").lower() == "from":
            sender = h.get("value", "")
            break
    email = sender.split("<")[-1].rstrip(">").strip().lower()
    domain = email.rsplit("@", 1)[-1] if "@" in email else ""
    return internal_label if domain == INTERNAL_DOMAIN else external_label

def apply_labels(msg_ids, token):
    buckets = {internal_label: [], external_label: []}
    for mid in msg_ids:
        buckets[classify(mid, token)].append(mid)
    for label_id, bucket in buckets.items():
        if bucket:
            gmail_api("POST", "/gmail/v1/users/me/messages/batchModify", token,
                      data={"ids": bucket, "addLabelIds": [label_id]})
    return {k: len(v) for k, v in buckets.items()}

half = len(ids) // 2
counts1 = apply_labels(ids[:half], access_token)
print(f"[oracle] labeled first half: {counts1}")

# --- 4. expiry: short-lived real JWT, used after exp -------------------------
_, _, short = http("POST", f"{AUTH}/_admin/issue_token", data={
    "client_id": CLIENT_ID,
    "user_id": "user1",
    "scopes": SCOPES.split(),
    "expires_in": 1,
    "include_refresh": False,
})
time.sleep(2)
status, _, body = gmail_api(
    "GET", "/gmail/v1/users/me/messages?maxResults=1", short["access_token"],
    expect_error=True)
assert status == 401, f"expected 401 for expired token, got {status}: {body}"
print("[oracle] expired-token request correctly rejected with 401 "
      "(token_expired_during_use recorded)")

# --- 5. refresh + finish ------------------------------------------------------
_, _, refreshed = http("POST", token_ep, form={
    "grant_type": "refresh_token",
    "refresh_token": refresh_token,
    "client_id": CLIENT_ID,
    "client_secret": CLIENT_SECRET,
})
access_token2 = refreshed["access_token"]
print(f"[oracle] refresh ok (expires_in={refreshed.get('expires_in')})")

counts2 = apply_labels(ids[half:], access_token2)
print(f"[oracle] labeled second half: {counts2}")

# verify every inbox message carries exactly one of the two labels
_, _, final = gmail_api(
    "GET", "/gmail/v1/users/me/messages?maxResults=500&labelIds=INBOX", access_token2)
bad = 0
for m in final.get("messages", []):
    _, _, full = gmail_api(
        "GET", f"/gmail/v1/users/me/messages/{m['id']}?format=minimal", access_token2)
    lids = set(full.get("labelIds", []))
    if len(lids & {internal_label, external_label}) != 1:
        bad += 1
assert bad == 0, f"{bad} messages not labeled exactly once"
print(f"[oracle] verification ok: {len(final.get('messages', []))} messages labeled")
print("[oracle] DONE")
PYEOF
