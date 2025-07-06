"""Main MCP server implementation for Praga Core."""

import json
import logging
from typing import Any, Dict, List, Optional

from fastmcp import Context, FastMCP

from praga_core.context import ServerContext
from praga_core.integrations.mcp.descriptions import (
    get_action_tool_description,
    get_pages_tool_description,
    get_search_tool_description,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def create_mcp_server(
    context: ServerContext,
    name: str = "Praga Core Server",
    **kwargs: Any,
) -> FastMCP:  # type: ignore[type-arg]
    """Create a FastMCP server that exposes ServerContext functionality.

    Args:
        context: ServerContext instance with registered page handlers
        name: Name of the MCP server
        **kwargs: Additional arguments passed to FastMCP constructor

    Returns:
        Configured FastMCP server instance
    """
    # Create FastMCP server without verbose instructions
    mcp: FastMCP = FastMCP(name, **kwargs)  # type: ignore[type-arg]

    # Setup tools and resources with the server context
    setup_mcp_tools(mcp, context)
    return mcp


def setup_mcp_tools(
    mcp: FastMCP,  # type: ignore[type-arg]
    server_context: ServerContext,
) -> None:
    """Setup MCP tools for search operations and actions.

    Args:
        mcp: FastMCP server instance
        server_context: ServerContext with registered handlers and actions
    """

    # Get available page types for tool description
    type_names = list(server_context._router._handlers.keys())

    @mcp.tool(description=get_search_tool_description(type_names))
    async def search_pages(
        instruction: str, resolve_references: bool = True, ctx: Optional[Context] = None
    ) -> str:
        """Search for pages using natural language instructions.

        Args:
            instruction: Natural language search instruction
            resolve_references: Whether to resolve page content in results
            ctx: MCP context for logging

        Returns:
            JSON string containing search results with page references and resolved content
        """
        try:
            if ctx:
                await ctx.info(f"Searching for: {instruction}")
                await ctx.info(f"Resolve references: {resolve_references}")

            # Perform the search
            search_response = await server_context.search(
                instruction, resolve_references=resolve_references
            )

            if ctx:
                await ctx.info(f"Found {len(search_response.results)} results")

            return search_response.model_dump_json(indent=2)

        except Exception as e:
            error_msg = f"Search failed: {str(e)}"
            if ctx:
                await ctx.error(error_msg)
            raise RuntimeError(error_msg)

    @mcp.tool(description=get_pages_tool_description(type_names))
    async def get_pages(
        page_uris: List[str], ctx: Optional[Context] = None, allow_stale: bool = False
    ) -> str:
        """Get specific pages by their type and IDs.

        Args:
            page_uris: List of unique identifiers for the pages (supports single or multiple IDs)
            ctx: MCP context for logging
            allow_stale: Whether to allow stale data

        Returns:
            JSON string containing the complete page data for all requested pages
        """
        try:
            if ctx:
                await ctx.info(f"Getting {len(page_uris)} pages")
                await ctx.info(f"Page URIs: {page_uris}")

            # Use the batch get_pages method
            try:
                pages = await server_context.get_pages(
                    page_uris, allow_stale=allow_stale
                )
            except Exception as e:
                # If the whole batch fails, return error for all
                error_msg = f"Failed to get pages: {str(e)}"
                if ctx:
                    await ctx.error(error_msg)
                response = {
                    "requested_count": len(page_uris),
                    "successful_count": 0,
                    "error_count": len(page_uris),
                    "pages": [],
                    "errors": [
                        {"uri": uri, "status": "error", "error": error_msg}
                        for uri in page_uris
                    ],
                }
                return json.dumps(response, indent=2)

            pages_data = []
            errors = []
            for page_uri, page in zip(page_uris, pages):
                if isinstance(page, Exception):
                    errors.append(
                        {
                            "uri": page_uri,
                            "status": "error",
                            "error": str(page),
                        }
                    )
                    if ctx:
                        await ctx.error(f"Failed to get page {page_uri}: {str(page)}")
                else:
                    pages_data.append(
                        {
                            "uri": page_uri,
                            "content": page.model_dump(mode="json"),
                            "status": "success",
                        }
                    )
                    if ctx:
                        await ctx.info(f"Successfully retrieved page: {page_uri}")

            response = {
                "requested_count": len(page_uris),
                "successful_count": len(pages_data),
                "error_count": len(errors),
                "pages": pages_data,
            }
            if errors:
                response["errors"] = errors
            return json.dumps(response, indent=2)

        except Exception as e:
            error_msg = f"Failed to get pages {page_uris}: {str(e)}"
            if ctx:
                await ctx.error(error_msg)
            raise RuntimeError(error_msg)

    # Setup action tools dynamically
    setup_action_tools(mcp, server_context)


def setup_action_tools(
    mcp: FastMCP,  # type: ignore[type-arg]
    server_context: ServerContext,
) -> None:
    """Setup MCP tools for registered actions.

    Args:
        mcp: FastMCP server instance
        server_context: ServerContext with registered actions
    """
    # Get all registered actions
    actions = server_context.actions
    
    for action_name, action_func in actions.items():
        # Create a tool for each action with proper closure
        def create_action_tool(name: str, func: object):
            # Generate description for this specific action
            description = get_action_tool_description(name, func)
            
            @mcp.tool(description=description)
            async def action_tool(action_input: Dict[str, Any], ctx: Optional[Context] = None) -> str:
                """Execute an action on a page.

                Args:
                    action_input: Dictionary containing the action parameters
                    ctx: MCP context for logging

                Returns:
                    JSON string containing action result with success status
                """
                try:
                    if ctx:
                        await ctx.info(f"Executing action: {name}")
                        await ctx.info(f"Action input: {action_input}")

                    # Invoke the action through the server context
                    result = server_context.invoke_action(name, action_input)

                    if ctx:
                        await ctx.info(f"Action result: {result}")

                    return json.dumps(result, indent=2)

                except Exception as e:
                    error_msg = f"Action '{name}' failed: {str(e)}"
                    if ctx:
                        await ctx.error(error_msg)
                    
                    return json.dumps({"success": False, "error": str(e)}, indent=2)
            
            # Set the function name dynamically for better MCP tool naming
            action_tool.__name__ = f"action_{name}"
            return action_tool
        
        # Create and register the tool - the @mcp.tool decorator registers it
        create_action_tool(action_name, action_func)
