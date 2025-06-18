"""Main MCP server implementation for Praga Core."""

import json
import logging
from typing import Any, List, Optional

from fastmcp import Context, FastMCP

from praga_core.context import ServerContext
from praga_core.integrations.mcp.descriptions import (
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
    """Setup MCP tools for search operations.

    Args:
        mcp: FastMCP server instance
        server_context: ServerContext with registered handlers
        config: Configuration for the MCP server
    """

    # Get available page types for tool description
    type_names = list(server_context._page_handlers.keys())

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
            search_response = server_context.search(
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
    async def get_pages(page_uris: List[str], ctx: Optional[Context] = None) -> str:
        """Get specific pages by their type and IDs.

        Args:
            page_uris: List of unique identifiers for the pages (supports single or multiple IDs)
            ctx: MCP context for logging

        Returns:
            JSON string containing the complete page data for all requested pages
        """
        try:
            if ctx:
                await ctx.info(f"Getting {len(page_uris)} pages")
                await ctx.info(f"Page URIs: {page_uris}")

            pages_data = []
            errors = []

            # Process each page ID
            for page_uri in page_uris:
                try:
                    # Create page URI and get the page
                    page = server_context.get_page(page_uri)

                    # Serialize the page to JSON
                    page_data = {
                        "uri": page_uri,
                        "content": page.model_dump(mode="json"),
                        "status": "success",
                    }
                    pages_data.append(page_data)

                    if ctx:
                        await ctx.info(f"Successfully retrieved page: {page_uri}")

                except Exception as e:
                    error_data = {
                        "uri": page_uri,
                        "status": "error",
                        "error": str(e),
                    }
                    errors.append(error_data)

                    if ctx:
                        await ctx.error(f"Failed to get page {page_uri}: {str(e)}")

            # Prepare response
            response = {
                "requested_count": len(page_uris),
                "successful_count": len(pages_data),
                "error_count": len(errors),
                "pages": pages_data,
            }

            # Include errors if any occurred
            if errors:
                response["errors"] = errors

            return json.dumps(response, indent=2)

        except Exception as e:
            error_msg = f"Failed to get pages {page_uris}: {str(e)}"
            if ctx:
                await ctx.error(error_msg)
            raise RuntimeError(error_msg)
