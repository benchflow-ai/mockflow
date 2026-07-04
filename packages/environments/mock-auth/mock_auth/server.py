"""Server assembly: create_app() + run_server() (uvicorn)."""

from __future__ import annotations

import uvicorn

from mock_auth.api.app import app
from mock_auth.models import init_db


def create_app(db_path: str | None = None, enable_mcp: bool = True):
    """Initialize the app: create tables, mount MCP."""
    init_db(db_path)
    if enable_mcp:
        from mock_auth.mcp.server import mount_mcp
        mount_mcp(app)
    return app


def run_server(
    host: str = "0.0.0.0",
    port: int = 9000,  # overridden by cli via config.toml; 9000 is the fallback
    db_path: str | None = None,
    enable_mcp: bool = True,
):
    create_app(db_path=db_path, enable_mcp=enable_mcp)
    uvicorn.run(app, host=host, port=port, log_level="info")
