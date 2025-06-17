"""MCP resources for Praga Core page access and schema discovery."""

import json

from fastmcp import FastMCP

from praga_core.context import ServerContext
from praga_core.integrations.mcp.config import MCPServerConfig
from praga_core.integrations.mcp.descriptions import (
    PAGE_SCHEMA_RESOURCE_DESCRIPTION,
    PAGE_TYPE_RESOURCE_DESCRIPTION,
    get_page_list_resource_description,
)


def setup_page_resources(
    mcp: FastMCP,  # type: ignore[type-arg]
    server_context: ServerContext,
    config: MCPServerConfig,
) -> None:
    """Setup MCP resources for page access and schema discovery.

    Args:
        mcp: FastMCP server instance
        server_context: ServerContext with registered handlers
        config: Configuration for the MCP server
    """

    # Get available page types for resource descriptions
    available_types = list(server_context._page_handlers.keys())
    type_names = [t.__name__ for t in available_types]

    @mcp.resource(
        uri="pages://list",
        name="Page List",
        description=get_page_list_resource_description(type_names),
        mime_type="application/json",
    )
    async def get_page_list() -> str:
        """Get information about available page types and their structure.

        Returns:
            JSON string containing page type information and usage guidance
        """
        try:
            page_type_info = []

            # Get information about each registered page type
            for page_type in available_types:
                handler = server_context._page_handlers.get(page_type)
                aliases = []

                # Check for type aliases
                for alias, aliased_type in server_context._type_aliases.items():
                    if aliased_type == page_type:
                        aliases.append(alias)

                page_type_info.append(
                    {
                        "class_name": page_type.__name__,
                        "module": page_type.__module__,
                        "aliases": aliases,
                        "has_handler": handler is not None,
                        "uri_pattern": f"{page_type.__name__}:{{page_id}}",
                    }
                )

            return json.dumps(
                {
                    "page_types": page_type_info,
                    "total_types": len(page_type_info),
                    "usage": {
                        "search": "Use search_pages tool to find pages with natural language",
                        "retrieve": "Use get_pages tool with specific page_type and page_ids",
                        "discover_schemas": "Use pages://schema resource for detailed schemas",
                        "discover_types": "Use pages://types resource for type information",
                    },
                },
                indent=2,
            )

        except Exception as e:
            error_msg = f"Failed to get page list: {str(e)}"
            raise RuntimeError(error_msg)

    @mcp.resource(
        uri="pages://schema",
        name="Page Schemas",
        description=PAGE_SCHEMA_RESOURCE_DESCRIPTION,
        mime_type="application/json",
    )
    async def get_page_schemas() -> str:
        """Get JSON schemas for all page types.

        Returns:
            JSON string containing schema definitions for all page types
        """
        try:
            schemas = {}

            for page_type in available_types:
                try:
                    # Get the Pydantic model schema
                    schema = page_type.model_json_schema()
                    schemas[page_type.__name__] = schema

                except Exception as e:
                    # Log error but continue with other page types
                    if config.enable_detailed_logging:
                        print(
                            f"Error getting schema for type {page_type.__name__}: {e}"
                        )

            return json.dumps(
                {"schemas": schemas, "available_types": type_names}, indent=2
            )

        except Exception as e:
            error_msg = f"Failed to get page schemas: {str(e)}"
            raise RuntimeError(error_msg)

    @mcp.resource(
        uri="pages://types",
        name="Page Types",
        description=PAGE_TYPE_RESOURCE_DESCRIPTION,
        mime_type="application/json",
    )
    async def get_page_types() -> str:
        """Get information about available page types.

        Returns:
            JSON string containing page type information and aliases
        """
        try:
            type_info = []

            for page_type in available_types:
                # Get handler info
                handler = server_context._page_handlers.get(page_type)
                aliases = []

                # Check for type aliases in the handler registry
                for (
                    registered_type,
                    registered_handler,
                ) in server_context._page_handlers.items():
                    if (
                        registered_handler == handler
                        and registered_type != page_type
                        and registered_type.__name__ != page_type.__name__
                    ):
                        aliases.append(registered_type.__name__)

                # Also check the explicit type aliases
                for alias, aliased_type in server_context._type_aliases.items():
                    if aliased_type == page_type:
                        aliases.append(alias)

                type_info.append(
                    {
                        "class_name": page_type.__name__,
                        "module": page_type.__module__,
                        "aliases": list(set(aliases)),  # Remove duplicates
                        "has_handler": handler is not None,
                    }
                )

            return json.dumps(
                {"page_types": type_info, "total_types": len(type_info)}, indent=2
            )

        except Exception as e:
            error_msg = f"Failed to get page types: {str(e)}"
            raise RuntimeError(error_msg)
