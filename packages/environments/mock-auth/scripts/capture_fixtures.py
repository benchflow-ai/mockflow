#!/usr/bin/env python3
"""Re-capture the PUBLIC (unauthenticated) Google OAuth fixtures.

Live-capturable without any credentials:
  - openid_configuration.json  GET https://accounts.google.com/.well-known/openid-configuration
  - jwks.json                  GET https://www.googleapis.com/oauth2/v3/certs
  - token_error_no_client.json POST https://oauth2.googleapis.com/token (no client)
  - tokeninfo_error_invalid.json GET https://oauth2.googleapis.com/tokeninfo?access_token=invalid
  - userinfo_error_invalid_credentials.json GET userinfo with Bearer invalid
  - device_code_error_invalid_client.json POST device/code with bogus client_id
  - revoke_error_invalid_token.json POST revoke with token=invalid

NOT re-captured here (require real Google OAuth client credentials — these are
AUTHORED from public docs, see _capture_metadata.json):
  token_response.json, token_refresh_response.json, userinfo.json,
  device_code_response.json, token_error_invalid_grant.json
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import httpx

FIXTURES_DIR = Path(__file__).parent.parent / "tests" / "fixtures" / "real_googleoauth"

AUTHORED_FILES = {
    "token_response.json",
    "token_refresh_response.json",
    "userinfo.json",
    "device_code_response.json",
    "token_error_invalid_grant.json",
}


def save(name: str, data: dict):
    FIXTURES_DIR.mkdir(parents=True, exist_ok=True)
    data["_captured_at"] = datetime.now(timezone.utc).isoformat()
    path = FIXTURES_DIR / f"{name}.json"
    path.write_text(json.dumps(data, indent=2))
    print(f"  Saved {path.name}")


def main():
    client = httpx.Client(timeout=30)

    print("Capturing public Google OAuth fixtures (no credentials required)...")

    r = client.get("https://accounts.google.com/.well-known/openid-configuration")
    r.raise_for_status()
    save("openid_configuration", r.json())

    r = client.get("https://www.googleapis.com/oauth2/v3/certs")
    r.raise_for_status()
    save("jwks", r.json())

    r = client.post("https://oauth2.googleapis.com/token",
                    data={"grant_type": "authorization_code", "code": "bad"})
    assert r.status_code == 400, r.status_code
    save("token_error_no_client", r.json())

    r = client.get("https://oauth2.googleapis.com/tokeninfo",
                   params={"access_token": "invalid"})
    assert r.status_code == 400, r.status_code
    save("tokeninfo_error_invalid", r.json())

    r = client.get("https://openidconnect.googleapis.com/v1/userinfo",
                   headers={"Authorization": "Bearer invalid"})
    assert r.status_code == 401, r.status_code
    save("userinfo_error_invalid_credentials", r.json())

    r = client.post("https://oauth2.googleapis.com/device/code",
                    data={"client_id": "bogus.apps.googleusercontent.com",
                          "scope": "email"})
    assert r.status_code == 401, r.status_code
    save("device_code_error_invalid_client", r.json())

    r = client.post("https://oauth2.googleapis.com/revoke", data={"token": "invalid"})
    assert r.status_code == 400, r.status_code
    save("revoke_error_invalid_token", r.json())

    # Refresh the metadata timestamp, preserving the per-file provenance notes.
    meta_path = FIXTURES_DIR / "_capture_metadata.json"
    if meta_path.exists():
        meta = json.loads(meta_path.read_text())
        meta["captured_at"] = datetime.now(timezone.utc).isoformat()
        meta_path.write_text(json.dumps(meta, indent=2))
        print("  Updated _capture_metadata.json")

    skipped = sorted(AUTHORED_FILES)
    print(f"Skipped (authored, need real creds): {', '.join(skipped)}")
    print("Done.")


if __name__ == "__main__":
    main()
