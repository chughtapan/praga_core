#!/usr/bin/env python3
"""MCP Server for Google APIs - Gmail & Calendar integration."""

from dotenv import load_dotenv

from praga_core import get_global_context
from praga_core.integrations.mcp import create_mcp_server
from pragweb.app import setup_global_context

load_dotenv()

setup_global_context()

context = get_global_context()
mcp = create_mcp_server(context)
