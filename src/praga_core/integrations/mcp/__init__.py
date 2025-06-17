"""MCP (Model Context Protocol) integration for Praga Core."""

from typing import Any

from fastmcp import FastMCP

from praga_core.context import ServerContext
from praga_core.integrations.mcp.server import create_mcp_server


def create_praga_mcp_server(context: ServerContext, **kwargs: Any) -> FastMCP:  # type: ignore[type-arg]
    """Create and configure a Praga Core MCP server.

    Args:
        context: ServerContext instance with registered page handlers
        **kwargs: Additional arguments passed to FastMCP constructor

    Returns:
        FastMCP server instance ready to run
    """
    return create_mcp_server(context, **kwargs)


__all__ = ["create_praga_mcp_server"]
