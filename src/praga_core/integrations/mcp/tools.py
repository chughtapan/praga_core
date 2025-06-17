"""MCP tools for Praga Core search operations."""

import json
from typing import List, Optional

from fastmcp import Context, FastMCP

from praga_core.context import ServerContext
from praga_core.integrations.mcp.config import MCPServerConfig
from praga_core.integrations.mcp.descriptions import (
    get_pages_tool_description,
    get_search_tool_description,
)
from praga_core.types import SearchResponse


def setup_search_tools(
    mcp: FastMCP,  # type: ignore[type-arg]
    server_context: ServerContext,
    config: MCPServerConfig,
) -> None:
    """Setup MCP tools for search operations.

    Args:
        mcp: FastMCP server instance
        server_context: ServerContext with registered handlers
        config: Configuration for the MCP server
    """

    # Get available page types for tool description
    available_types = list(server_context._page_handlers.keys())
    type_names = [t.__name__ for t in available_types]

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
            if ctx and config.enable_detailed_logging:
                await ctx.info(f"Searching for: {instruction}")
                await ctx.info(f"Resolve references: {resolve_references}")

            # Perform the search
            results = server_context.search(
                instruction, resolve_references=resolve_references
            )

            # Create SearchResponse and serialize to JSON
            search_response = SearchResponse(results=results)

            if ctx and config.enable_detailed_logging:
                await ctx.info(f"Found {len(results)} results")

            return search_response.model_dump_json(indent=2)

        except Exception as e:
            error_msg = f"Search failed: {str(e)}"
            if ctx:
                await ctx.error(error_msg)
            raise RuntimeError(error_msg)

    @mcp.tool(description=get_pages_tool_description(type_names))
    async def get_pages(
        page_type: str, page_ids: List[str], ctx: Optional[Context] = None
    ) -> str:
        """Get specific pages by their type and IDs.

        Args:
            page_type: The type of pages to retrieve (e.g., "EmailPage", "CalendarEventPage", or aliases)
            page_ids: List of unique identifiers for the pages (supports single or multiple IDs)
            ctx: MCP context for logging

        Returns:
            JSON string containing the complete page data for all requested pages
        """
        try:
            if ctx and config.enable_detailed_logging:
                await ctx.info(f"Getting {len(page_ids)} pages of type {page_type}")
                await ctx.info(f"Page IDs: {page_ids}")

            pages_data = []
            errors = []

            # Process each page ID
            for page_id in page_ids:
                try:
                    # Create page URI and get the page
                    page_uri = server_context.get_page_uri(page_id, page_type)
                    page = server_context.get_page(page_uri)

                    # Serialize the page to JSON
                    page_data = {
                        "type": page_type,
                        "id": page_id,
                        "uri": page_uri,
                        "content": page.model_dump(mode="json"),
                        "status": "success",
                    }
                    pages_data.append(page_data)

                    if ctx and config.enable_detailed_logging:
                        await ctx.info(
                            f"Successfully retrieved page: {page_type}:{page_id}"
                        )

                except Exception as e:
                    error_data = {
                        "type": page_type,
                        "id": page_id,
                        "status": "error",
                        "error": str(e),
                    }
                    errors.append(error_data)

                    if ctx:
                        await ctx.error(
                            f"Failed to get page {page_type}:{page_id}: {str(e)}"
                        )

            # Prepare response
            response = {
                "requested_count": len(page_ids),
                "successful_count": len(pages_data),
                "error_count": len(errors),
                "pages": pages_data,
            }

            # Include errors if any occurred
            if errors:
                response["errors"] = errors

            return json.dumps(response, indent=2)

        except Exception as e:
            error_msg = f"Failed to get pages {page_type}: {str(e)}"
            if ctx:
                await ctx.error(error_msg)
            raise RuntimeError(error_msg)
