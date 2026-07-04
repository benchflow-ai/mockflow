"""Gymnasium environment for Discord tool-use RL training."""

from __future__ import annotations

import json
import os
import threading
import time
from typing import Any

import httpx

try:
    import gymnasium as gym
    from gymnasium import spaces

    HAS_GYM = True
except ImportError:
    HAS_GYM = False

from mock_discord.models import reset_engine
from mock_discord.seed.generator import seed_database
from mock_discord.tasks import get_task, list_tasks


def _start_server(host: str, port: int, db_path: str):
    """Start FastAPI server in a background thread."""
    import uvicorn

    from mock_discord.server import create_app

    app = create_app(db_path=db_path, enable_mcp=False)
    config = uvicorn.Config(app, host=host, port=port, log_level="warning")
    server = uvicorn.Server(config)
    server.run()


if HAS_GYM:
    class DiscordToolEnv(gym.Env):
        """Gymnasium environment for interacting with the Mock Discord API via tool calls.

        Usage:
            env = DiscordToolEnv(task_name="moderate-spam")
            obs, info = env.reset()
            obs, reward, terminated, truncated, info = env.step({
                "tool_name": "messages_list",
                "tool_args": {"channel_id": "123", "limit": 50}
            })
        """

        metadata = {"render_modes": ["human"]}

        # API tool definitions: name -> (method, path_template)
        TOOLS = {
            # Channels
            "channel_get": ("GET", "/api/v10/channels/{channel_id}"),
            "channel_modify": ("PATCH", "/api/v10/channels/{channel_id}"),
            "channel_delete": ("DELETE", "/api/v10/channels/{channel_id}"),
            # Messages
            "messages_list": ("GET", "/api/v10/channels/{channel_id}/messages"),
            "message_get": ("GET", "/api/v10/channels/{channel_id}/messages/{message_id}"),
            "message_create": ("POST", "/api/v10/channels/{channel_id}/messages"),
            "message_edit": ("PATCH", "/api/v10/channels/{channel_id}/messages/{message_id}"),
            "message_delete": ("DELETE", "/api/v10/channels/{channel_id}/messages/{message_id}"),
            "messages_bulk_delete": ("POST", "/api/v10/channels/{channel_id}/messages/bulk-delete"),
            # Reactions
            "reaction_add": ("PUT", "/api/v10/channels/{channel_id}/messages/{message_id}/reactions/{emoji}/@me"),
            "reaction_remove": ("DELETE", "/api/v10/channels/{channel_id}/messages/{message_id}/reactions/{emoji}/@me"),
            "reactions_get": ("GET", "/api/v10/channels/{channel_id}/messages/{message_id}/reactions/{emoji}"),
            "reactions_delete_all": ("DELETE", "/api/v10/channels/{channel_id}/messages/{message_id}/reactions"),
            # Guilds
            "guild_get": ("GET", "/api/v10/guilds/{guild_id}"),
            "guild_modify": ("PATCH", "/api/v10/guilds/{guild_id}"),
            "guild_channels": ("GET", "/api/v10/guilds/{guild_id}/channels"),
            "guild_channel_create": ("POST", "/api/v10/guilds/{guild_id}/channels"),
            # Members
            "members_list": ("GET", "/api/v10/guilds/{guild_id}/members"),
            "member_get": ("GET", "/api/v10/guilds/{guild_id}/members/{user_id}"),
            "member_modify": ("PATCH", "/api/v10/guilds/{guild_id}/members/{user_id}"),
            "member_kick": ("DELETE", "/api/v10/guilds/{guild_id}/members/{user_id}"),
            "member_role_add": ("PUT", "/api/v10/guilds/{guild_id}/members/{user_id}/roles/{role_id}"),
            "member_role_remove": ("DELETE", "/api/v10/guilds/{guild_id}/members/{user_id}/roles/{role_id}"),
            # Bans
            "ban_create": ("PUT", "/api/v10/guilds/{guild_id}/bans/{user_id}"),
            "ban_remove": ("DELETE", "/api/v10/guilds/{guild_id}/bans/{user_id}"),
            "bans_list": ("GET", "/api/v10/guilds/{guild_id}/bans"),
            # Roles
            "roles_list": ("GET", "/api/v10/guilds/{guild_id}/roles"),
            "role_create": ("POST", "/api/v10/guilds/{guild_id}/roles"),
            "role_modify": ("PATCH", "/api/v10/guilds/{guild_id}/roles/{role_id}"),
            "role_delete": ("DELETE", "/api/v10/guilds/{guild_id}/roles/{role_id}"),
            # Users
            "user_me": ("GET", "/api/v10/users/@me"),
            "user_get": ("GET", "/api/v10/users/{user_id}"),
            "user_guilds": ("GET", "/api/v10/users/@me/guilds"),
            # Webhooks
            "webhook_create": ("POST", "/api/v10/channels/{channel_id}/webhooks"),
            "webhook_get": ("GET", "/api/v10/webhooks/{webhook_id}"),
            "webhook_modify": ("PATCH", "/api/v10/webhooks/{webhook_id}"),
            "webhook_delete": ("DELETE", "/api/v10/webhooks/{webhook_id}"),
            "webhook_execute": ("POST", "/api/v10/webhooks/{webhook_id}/{webhook_token}"),
            # Emoji
            "emojis_list": ("GET", "/api/v10/guilds/{guild_id}/emojis"),
            "emoji_create": ("POST", "/api/v10/guilds/{guild_id}/emojis"),
            "emoji_delete": ("DELETE", "/api/v10/guilds/{guild_id}/emojis/{emoji_id}"),
            # Threads
            "thread_create": ("POST", "/api/v10/channels/{channel_id}/threads"),
            "thread_join": ("PUT", "/api/v10/channels/{channel_id}/thread-members/@me"),
            "thread_leave": ("DELETE", "/api/v10/channels/{channel_id}/thread-members/@me"),
            "threads_active": ("GET", "/api/v10/guilds/{guild_id}/threads/active"),
            # Invites
            "invite_create": ("POST", "/api/v10/channels/{channel_id}/invites"),
            "invites_list": ("GET", "/api/v10/channels/{channel_id}/invites"),
        }

        # Path parameters that can appear in tool paths
        _PATH_PARAMS = [
            "guild_id", "channel_id", "message_id", "user_id",
            "role_id", "webhook_id", "webhook_token", "emoji_id", "emoji",
        ]

        def __init__(
            self,
            task_name: str = "",
            scenario: str | None = None,
            host: str = "127.0.0.1",
            port: int = 8103,
            db_path: str = "gym_discord.db",
            seed: int = 42,
            max_steps: int = 50,
            step_penalty: float = -0.01,
        ):
            super().__init__()

            self.task_name = task_name
            self.host = host
            self.port = port
            self.db_path = db_path
            self.seed_val = seed
            self.max_steps = max_steps
            self.step_penalty = step_penalty
            self.base_url = f"http://{host}:{port}"

            if task_name:
                task = get_task(task_name)
                if not task:
                    raise ValueError(f"Unknown task: {task_name}. Available: {list_tasks()}")
                self.task = task
                self.scenario = scenario or task.scenario
            else:
                self.task = None
                self.scenario = scenario or "default"

            # Spaces
            self.action_space = spaces.Dict(
                {
                    "tool_name": spaces.Text(min_length=1, max_length=100),
                    "tool_args": spaces.Text(min_length=0, max_length=10000),
                }
            )
            self.observation_space = spaces.Dict(
                {
                    "goal": spaces.Text(min_length=0, max_length=10000),
                    "api_response": spaces.Text(min_length=0, max_length=100000),
                    "step": spaces.Discrete(max_steps + 1),
                }
            )

            self._server_thread = None
            self._step_count = 0
            self._client = None

        def reset(self, seed=None, options=None):
            """Reset environment: re-seed DB, start server, return initial observation."""
            if seed is not None:
                self.seed_val = seed

            # Reset DB
            reset_engine()
            if os.path.exists(self.db_path):
                os.unlink(self.db_path)

            seed_database(
                scenario=self.scenario,
                seed=self.seed_val,
                db_path=self.db_path,
            )

            # Start server if not running
            if self._server_thread is None or not self._server_thread.is_alive():
                reset_engine()
                self._server_thread = threading.Thread(
                    target=_start_server,
                    args=(self.host, self.port, self.db_path),
                    daemon=True,
                )
                self._server_thread.start()
                self._wait_for_server()

            self._client = httpx.Client(base_url=self.base_url, timeout=30)
            self._step_count = 0

            # Reset action log
            self._client.post("/_admin/reset")

            goal = self.task.instruction if self.task else "Explore the Discord server"
            obs = {
                "goal": goal,
                "api_response": json.dumps({"status": "ready", "task": self.task_name}),
                "step": 0,
            }
            info = {
                "task_name": self.task_name,
                "scenario": self.scenario,
                "tools": list(self.TOOLS.keys()),
            }
            return obs, info

        def step(self, action: dict[str, Any]):
            """Execute a tool call and return observation."""
            self._step_count += 1

            tool_name = action.get("tool_name", "")
            tool_args_raw = action.get("tool_args", "{}")

            if isinstance(tool_args_raw, str):
                try:
                    tool_args = json.loads(tool_args_raw)
                except json.JSONDecodeError:
                    tool_args = {}
            else:
                tool_args = tool_args_raw

            # Execute tool call
            api_response = self._execute_tool(tool_name, tool_args)

            # Check task completion
            reward = self.step_penalty
            terminated = False
            truncated = self._step_count >= self.max_steps

            if self.task and (truncated or self._should_evaluate(tool_name)):
                state = self._client.get("/_admin/state").json()
                diff = self._client.get("/_admin/diff").json()
                log = self._client.get("/_admin/action_log").json().get("entries", [])

                task_reward, done = self.task.evaluate(state, diff, log)
                reward += task_reward
                terminated = done

            obs = {
                "goal": self.task.instruction if self.task else "",
                "api_response": json.dumps(api_response)
                if isinstance(api_response, dict)
                else str(api_response),
                "step": self._step_count,
            }
            info = {"tool_name": tool_name, "step": self._step_count}

            return obs, reward, terminated, truncated, info

        def _execute_tool(self, tool_name: str, args: dict) -> dict:
            """Execute an API tool call."""
            if tool_name not in self.TOOLS:
                return {
                    "error": f"Unknown tool: {tool_name}. Available: {list(self.TOOLS.keys())}"
                }

            method, path_template = self.TOOLS[tool_name]

            # Substitute path params
            path = path_template
            for key in self._PATH_PARAMS:
                token = "{" + key + "}"
                if token in path:
                    value = args.pop(key, None)
                    if value is None:
                        return {"error": f"Missing required path param: {key}"}
                    path = path.replace(token, str(value))

            try:
                if method == "GET":
                    resp = self._client.get(path, params=args)
                elif method == "POST":
                    resp = self._client.post(path, json=args)
                elif method == "PATCH":
                    resp = self._client.patch(path, json=args)
                elif method == "PUT":
                    resp = self._client.put(path)
                elif method == "DELETE":
                    resp = self._client.delete(path)
                else:
                    return {"error": f"Unsupported method: {method}"}

                if resp.status_code in (200, 201):
                    return resp.json()
                if resp.status_code == 204:
                    return {"status": "no_content"}
                return {"error": resp.text, "status_code": resp.status_code}
            except Exception as exc:
                return {"error": str(exc)}

        def _should_evaluate(self, tool_name: str) -> bool:
            """Heuristic: evaluate after write operations."""
            write_tools = {
                "message_create", "message_edit", "message_delete",
                "messages_bulk_delete", "channel_modify", "channel_delete",
                "guild_channel_create", "guild_modify",
                "member_modify", "member_kick",
                "member_role_add", "member_role_remove",
                "ban_create", "ban_remove",
                "role_create", "role_modify", "role_delete",
                "webhook_create", "webhook_modify", "webhook_delete",
                "webhook_execute",
                "emoji_create", "emoji_delete",
                "reaction_add", "reaction_remove", "reactions_delete_all",
            }
            return tool_name in write_tools

        def _wait_for_server(self, timeout: float = 10.0):
            """Wait for server to be ready."""
            start = time.time()
            while time.time() - start < timeout:
                try:
                    resp = httpx.get(f"{self.base_url}/health", timeout=1)
                    if resp.status_code == 200:
                        return
                except (httpx.ConnectError, httpx.ReadTimeout):
                    pass
                time.sleep(0.2)
            raise TimeoutError(f"Server did not start within {timeout}s")

        def render(self):
            pass

        def close(self):
            if self._client:
                self._client.close()
else:
    class DiscordToolEnv:
        """Stub when gymnasium is not installed."""

        def __init__(self, *args, **kwargs):
            raise ImportError(
                "gymnasium is required for DiscordToolEnv. "
                "Install with: pip install gymnasium"
            )
