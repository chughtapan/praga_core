"""Configuration for Praga Core MCP integration."""

from typing import Optional

from pydantic import BaseModel, Field


class MCPServerConfig(BaseModel):
    """Configuration for MCP server."""

    name: str = Field(default="Praga Core Server", description="Name of the MCP server")
    description: Optional[str] = Field(
        default=None, description="Server description (auto-generated if None)"
    )
    include_schemas_in_description: bool = Field(
        default=True, description="Include schema info in server description"
    )
    max_search_results: int = Field(
        default=50, description="Maximum number of search results to return"
    )
    enable_detailed_logging: bool = Field(
        default=True, description="Enable detailed MCP operation logging"
    )


# Default server configuration
DEFAULT_CONFIG = MCPServerConfig()
