"""Main server launcher."""

from __future__ import annotations

import uvicorn

from mock_stripe.api.app import app
from mock_stripe.models import init_db


def create_app(db_path: str | None = None, enable_mcp: bool = True):
    """Initialize the app: create tables, mount MCP."""
    init_db(db_path)

    if enable_mcp:
        from mock_stripe.mcp.server import mount_mcp
        mount_mcp(app)

    return app


def run_server(
    host: str = "0.0.0.0",
    port: int = 9007,  # overridden by cli via config.toml
    db_path: str | None = None,
    enable_mcp: bool = True,
    reload: bool = False,
):
    """Run the server."""
    create_app(db_path=db_path, enable_mcp=enable_mcp)

    uvicorn.run(
        app,
        host=host,
        port=port,
        log_level="info",
    )
