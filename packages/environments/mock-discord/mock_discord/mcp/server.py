"""MCP (Model Context Protocol) endpoint (optional)."""

from __future__ import annotations


def mount_mcp(app):
    """Mount MCP endpoint on the FastAPI app."""
    try:
        from fastapi_mcp import FastApiMCP

        mcp = FastApiMCP(app)
        mcp.mount()
    except ImportError:
        pass
    except Exception:
        # MCP mounting can fail (e.g., recursion in schema resolution)
        pass
