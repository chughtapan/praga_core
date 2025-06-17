"""Main MCP server implementation for Praga Core."""

import logging
from typing import Any, Optional

from fastmcp import FastMCP

from praga_core.context import ServerContext
from praga_core.integrations.mcp.config import DEFAULT_CONFIG, MCPServerConfig
from praga_core.integrations.mcp.resources import setup_page_resources
from praga_core.integrations.mcp.tools import setup_search_tools

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def create_mcp_server(
    context: ServerContext,
    name: str = "Praga Core Server",
    config: Optional[MCPServerConfig] = None,
    **kwargs: Any,
) -> FastMCP:  # type: ignore[type-arg]
    """Create a FastMCP server that exposes ServerContext functionality.

    Args:
        context: ServerContext instance with registered page handlers
        name: Name of the MCP server
        config: Configuration for the MCP server
        **kwargs: Additional arguments passed to FastMCP constructor

    Returns:
        Configured FastMCP server instance
    """
    if config is None:
        config = DEFAULT_CONFIG

    # Create FastMCP server without verbose instructions
    mcp: FastMCP = FastMCP(name, **kwargs)  # type: ignore[type-arg]

    # Setup tools and resources with the server context
    setup_search_tools(mcp, context, config)
    setup_page_resources(mcp, context, config)

    return mcp
