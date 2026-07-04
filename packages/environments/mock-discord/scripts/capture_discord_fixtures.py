"""Capture real Discord API responses as golden fixtures.

Usage:
    python scripts/capture_discord_fixtures.py

Requires .env file with:
    DISCORD_BOT_TOKEN=your_token
    DISCORD_GUILD_ID=your_guild_id
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import httpx

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "real_discord"
# Walk up to find .env at the monorepo root
_SCRIPT_DIR = Path(__file__).resolve().parent
ENV_FILE = _SCRIPT_DIR.parent.parent.parent.parent / ".env"

BASE_URL = "https://discord.com/api/v10"


def load_env() -> dict[str, str]:
    """Load .env file."""
    env = {}
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                env[key.strip()] = value.strip()
    return env


def save_fixture(name: str, data: dict | list):
    """Save a fixture JSON file."""
    FIXTURES_DIR.mkdir(parents=True, exist_ok=True)
    path = FIXTURES_DIR / f"{name}.json"
    path.write_text(json.dumps(data, indent=2))
    print(f"  Saved: {path.name}")


def api(client: httpx.Client, method: str, path: str, **kwargs) -> httpx.Response:
    """Make a Discord API request with rate limit handling."""
    resp = client.request(method, f"{BASE_URL}{path}", **kwargs)

    # Handle rate limits
    if resp.status_code == 429:
        retry_after = resp.json().get("retry_after", 1)
        print(f"  Rate limited, waiting {retry_after}s...")
        time.sleep(retry_after + 0.5)
        resp = client.request(method, f"{BASE_URL}{path}", **kwargs)

    return resp


def capture_all(token: str, guild_id: str):
    """Capture all fixture responses from the real Discord API."""
    headers = {"Authorization": f"Bot {token}"}
    client = httpx.Client(headers=headers, timeout=30)

    print("=== Capturing Discord API fixtures ===\n")

    # Track created resources for cleanup
    created_channels = []
    created_roles = []
    created_webhooks = []
    created_emojis = []

    try:
        # --- Users ---
        print("[Users]")
        resp = api(client, "GET", "/users/@me")
        assert resp.status_code == 200, f"GET /users/@me failed: {resp.status_code} {resp.text}"
        save_fixture("user_get_me", resp.json())
        bot_user_id = resp.json()["id"]

        # --- Guild ---
        print("[Guild]")
        resp = api(client, "GET", f"/guilds/{guild_id}")
        assert resp.status_code == 200, f"GET guild failed: {resp.status_code} {resp.text}"
        save_fixture("guild_get", resp.json())

        resp = api(client, "GET", f"/guilds/{guild_id}/preview")
        if resp.status_code == 200:
            save_fixture("guild_preview", resp.json())

        # --- Channels ---
        print("[Channels]")
        resp = api(client, "GET", f"/guilds/{guild_id}/channels")
        assert resp.status_code == 200
        save_fixture("guild_channels_list", resp.json())
        channels = resp.json()

        # Find or create a text channel
        text_channel = next((c for c in channels if c["type"] == 0), None)
        if not text_channel:
            resp = api(client, "POST", f"/guilds/{guild_id}/channels", json={
                "name": "env-0-test",
                "type": 0,
                "topic": "Temporary channel for fixture capture",
            })
            assert resp.status_code in (200, 201)
            text_channel = resp.json()
            created_channels.append(text_channel["id"])

        channel_id = text_channel["id"]

        resp = api(client, "GET", f"/channels/{channel_id}")
        assert resp.status_code == 200
        save_fixture("channel_get", resp.json())

        # Create a test channel then capture modify + delete responses
        resp = api(client, "POST", f"/guilds/{guild_id}/channels", json={
            "name": "env-0-temp",
            "type": 0,
        })
        if resp.status_code in (200, 201):
            save_fixture("channel_create_response", resp.json())
            temp_ch_id = resp.json()["id"]

            resp = api(client, "PATCH", f"/channels/{temp_ch_id}", json={"topic": "Updated"})
            if resp.status_code == 200:
                save_fixture("channel_modify_response", resp.json())

            resp = api(client, "DELETE", f"/channels/{temp_ch_id}")
            if resp.status_code == 200:
                save_fixture("channel_delete_response", resp.json())

        # --- Messages ---
        print("[Messages]")
        resp = api(client, "POST", f"/channels/{channel_id}/messages", json={
            "content": "Hello from env-0 fixture capture!",
        })
        assert resp.status_code == 200
        save_fixture("message_create_response", resp.json())
        msg_id = resp.json()["id"]

        resp = api(client, "GET", f"/channels/{channel_id}/messages/{msg_id}")
        assert resp.status_code == 200
        save_fixture("message_get", resp.json())

        resp = api(client, "GET", f"/channels/{channel_id}/messages?limit=5")
        assert resp.status_code == 200
        save_fixture("messages_list", resp.json())

        resp = api(client, "PATCH", f"/channels/{channel_id}/messages/{msg_id}", json={
            "content": "Edited message",
        })
        if resp.status_code == 200:
            save_fixture("message_edit_response", resp.json())

        # --- Reactions ---
        print("[Reactions]")
        resp = api(client, "PUT", f"/channels/{channel_id}/messages/{msg_id}/reactions/%F0%9F%91%8D/@me")
        save_fixture("reaction_add_status", {"status_code": resp.status_code})

        resp = api(client, "GET", f"/channels/{channel_id}/messages/{msg_id}/reactions/%F0%9F%91%8D")
        if resp.status_code == 200:
            save_fixture("reaction_get_users", resp.json())

        # Fetch message with reactions to see the reaction object shape
        resp = api(client, "GET", f"/channels/{channel_id}/messages/{msg_id}")
        if resp.status_code == 200:
            save_fixture("message_get_with_reactions", resp.json())

        # Clean up reaction
        api(client, "DELETE", f"/channels/{channel_id}/messages/{msg_id}/reactions/%F0%9F%91%8D/@me")

        # --- Roles ---
        print("[Roles]")
        resp = api(client, "GET", f"/guilds/{guild_id}/roles")
        assert resp.status_code == 200
        save_fixture("roles_list", resp.json())

        resp = api(client, "POST", f"/guilds/{guild_id}/roles", json={
            "name": "env-0-test-role",
            "color": 16711680,
            "hoist": True,
        })
        if resp.status_code == 200:
            save_fixture("role_create_response", resp.json())
            role_id = resp.json()["id"]
            created_roles.append(role_id)

            resp = api(client, "PATCH", f"/guilds/{guild_id}/roles/{role_id}", json={
                "name": "env-0-renamed",
            })
            if resp.status_code == 200:
                save_fixture("role_modify_response", resp.json())

        # --- Members ---
        print("[Members]")
        resp = api(client, "GET", f"/guilds/{guild_id}/members?limit=10")
        assert resp.status_code == 200
        save_fixture("members_list", resp.json())

        resp = api(client, "GET", f"/guilds/{guild_id}/members/{bot_user_id}")
        if resp.status_code == 200:
            save_fixture("member_get", resp.json())

        # --- Threads ---
        print("[Threads]")
        resp = api(client, "POST", f"/channels/{channel_id}/messages/{msg_id}/threads", json={
            "name": "env-0-test-thread",
        })
        if resp.status_code in (200, 201):
            save_fixture("thread_create_from_message", resp.json())
            thread_id = resp.json()["id"]
            created_channels.append(thread_id)

            resp = api(client, "GET", f"/channels/{thread_id}/thread-members")
            if resp.status_code == 200:
                save_fixture("thread_members_list", resp.json())

        resp = api(client, "GET", f"/guilds/{guild_id}/threads/active")
        if resp.status_code == 200:
            save_fixture("guild_active_threads", resp.json())

        # --- Webhooks ---
        print("[Webhooks]")
        resp = api(client, "POST", f"/channels/{channel_id}/webhooks", json={
            "name": "env-0-test-hook",
        })
        if resp.status_code == 200:
            save_fixture("webhook_create_response", resp.json())
            webhook = resp.json()
            webhook_id = webhook["id"]
            webhook_token = webhook["token"]
            created_webhooks.append(webhook_id)

            resp = api(client, "GET", f"/webhooks/{webhook_id}")
            if resp.status_code == 200:
                save_fixture("webhook_get", resp.json())

            resp = api(client, "GET", f"/webhooks/{webhook_id}/{webhook_token}")
            if resp.status_code == 200:
                save_fixture("webhook_get_with_token", resp.json())

            # Execute webhook with wait
            resp = api(client, "POST", f"/webhooks/{webhook_id}/{webhook_token}?wait=true", json={
                "content": "Webhook test message",
            })
            if resp.status_code == 200:
                save_fixture("webhook_execute_response", resp.json())

            resp = api(client, "GET", f"/channels/{channel_id}/webhooks")
            if resp.status_code == 200:
                save_fixture("channel_webhooks_list", resp.json())

        # --- Invites ---
        print("[Invites]")
        resp = api(client, "POST", f"/channels/{channel_id}/invites", json={
            "max_age": 3600,
            "max_uses": 1,
        })
        if resp.status_code == 200:
            save_fixture("invite_create_response", resp.json())

        resp = api(client, "GET", f"/channels/{channel_id}/invites")
        if resp.status_code == 200:
            save_fixture("channel_invites_list", resp.json())

        # --- Emojis ---
        print("[Emojis]")
        resp = api(client, "GET", f"/guilds/{guild_id}/emojis")
        assert resp.status_code == 200
        save_fixture("emojis_list", resp.json())

        # --- Guild Bans ---
        print("[Bans]")
        resp = api(client, "GET", f"/guilds/{guild_id}/bans")
        if resp.status_code == 200:
            save_fixture("bans_list", resp.json())

        # --- Audit Log (bonus) ---
        print("[Audit Log]")
        resp = api(client, "GET", f"/guilds/{guild_id}/audit-logs?limit=5")
        if resp.status_code == 200:
            save_fixture("audit_log", resp.json())

        # --- Error responses ---
        print("[Errors]")
        resp = api(client, "GET", "/channels/000000000000000000")
        save_fixture("error_unknown_channel", resp.json())

        resp = api(client, "GET", f"/channels/{channel_id}/messages/000000000000000000")
        save_fixture("error_unknown_message", resp.json())

        print(f"\n=== Done! Captured fixtures to {FIXTURES_DIR} ===")

    finally:
        # --- Cleanup ---
        print("\n[Cleanup]")

        # Delete test messages in the channel
        resp = api(client, "GET", f"/channels/{channel_id}/messages?limit=10")
        if resp.status_code == 200:
            bot_msgs = [m for m in resp.json() if m["author"]["id"] == bot_user_id]
            for m in bot_msgs:
                api(client, "DELETE", f"/channels/{channel_id}/messages/{m['id']}")
                time.sleep(0.5)
            print(f"  Deleted {len(bot_msgs)} test messages")

        for wh_id in created_webhooks:
            api(client, "DELETE", f"/webhooks/{wh_id}")
            print(f"  Deleted webhook {wh_id}")

        for role_id in created_roles:
            api(client, "DELETE", f"/guilds/{guild_id}/roles/{role_id}")
            print(f"  Deleted role {role_id}")

        for ch_id in created_channels:
            api(client, "DELETE", f"/channels/{ch_id}")
            time.sleep(0.3)
            print(f"  Deleted channel/thread {ch_id}")

        # Delete invites
        resp = api(client, "GET", f"/channels/{channel_id}/invites")
        if resp.status_code == 200:
            for inv in resp.json():
                api(client, "DELETE", f"/invites/{inv['code']}")
            print(f"  Deleted {len(resp.json())} invites")

        client.close()
        print("  Cleanup complete")


def main():
    env = load_env()
    token = env.get("DISCORD_BOT_TOKEN") or os.environ.get("DISCORD_BOT_TOKEN")
    guild_id = env.get("DISCORD_GUILD_ID") or os.environ.get("DISCORD_GUILD_ID")

    if not token or token == "REPLACE_ME_WITH_YOUR_NEW_TOKEN":
        print("Error: Set DISCORD_BOT_TOKEN in .env file first")
        sys.exit(1)
    if not guild_id:
        print("Error: Set DISCORD_GUILD_ID in .env file first")
        sys.exit(1)

    capture_all(token, guild_id)


if __name__ == "__main__":
    main()
