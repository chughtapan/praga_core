#!/usr/bin/env python3
"""MCP Server for Google APIs - Gmail & Calendar integration."""

import threading

from dotenv import load_dotenv

from praga_core import ServerContext, get_global_context
from praga_core.integrations.mcp import create_mcp_server
from pragweb.app import setup_global_context

load_dotenv()

_context_ready = threading.Event()
_context = None


def _setup_context() -> None:
    global _context
    import asyncio

    asyncio.run(setup_global_context())
    _context = get_global_context()
    _context_ready.set()


# Run context setup in a thread so module-level mcp can be created synchronously
threading.Thread(target=_setup_context).start()
_context_ready.wait()

assert isinstance(
    _context, ServerContext
), "Global context was not initialized as a ServerContext"
mcp = create_mcp_server(_context)
