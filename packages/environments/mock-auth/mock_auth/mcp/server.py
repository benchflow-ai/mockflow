"""Optional MCP mount (fastapi-mcp); the server works fine without it."""

from __future__ import annotations

import warnings


def mount_mcp(app):
    try:
        from fastapi_mcp import FastApiMCP
    except ImportError:
        warnings.warn(
            "fastapi-mcp is not installed; MCP endpoint disabled. "
            "Install with `pip install auth[mcp]`.",
            stacklevel=2,
        )
        return None
    mcp = FastApiMCP(
        app,
        name="auth",
        description="Mock OAuth2/OIDC authorization server for AI agents",
    )
    mcp.mount_http()
    return mcp
