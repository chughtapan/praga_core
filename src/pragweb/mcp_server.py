#!/usr/bin/env python3
"""MCP Server for Google APIs - Gmail & Calendar integration."""

from dotenv import load_dotenv

from praga_core.integrations.mcp import create_mcp_server
from pragweb.app import setup_context

load_dotenv()
ctx = setup_context()
mcp = create_mcp_server(
    ctx,
    name="Google APIs - Gmail & Calendar Server",
)


if __name__ == "__main__":
    # Run directly if executed as script
    import asyncio

    asyncio.run(mcp.run_async())
