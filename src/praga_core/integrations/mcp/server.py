"""Main MCP server implementation for Praga Core."""

import inspect
import json
import logging
from typing import (
    Any,
    List,
    Optional,
    Union,
    get_args,
    get_origin,
    get_type_hints,
)

from fastmcp import Context, FastMCP

from praga_core.action_executor import ActionFunction
from praga_core.context import ServerContext
from praga_core.integrations.mcp.descriptions import (
    get_action_tool_description,
    get_pages_tool_description,
    get_search_tool_description,
)
from praga_core.types import Page, PageURI

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
    type_names = list(server_context._handlers.keys())

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
        # Create a unique tool for each action
        _create_individual_action_tool(mcp, server_context, action_name, action_func)


def _create_individual_action_tool(
    mcp: FastMCP,  # type: ignore[type-arg]
    server_context: ServerContext,
    action_name: str,
    action_func: ActionFunction,
) -> None:
    """Create an individual MCP tool for a specific action.

    Args:
        mcp: FastMCP server instance
        server_context: ServerContext with registered actions
        action_name: Name of the action
        action_func: Action function
    """
    # Generate description for this specific action
    description = get_action_tool_description(action_name, action_func)

    # Get the transformed signature (Page -> PageURI) from the action function
    sig = inspect.signature(action_func)

    # Create parameter list for the dynamic function
    param_names = list(sig.parameters.keys())

    # Create a dynamic function with proper parameter signature
    async def dynamic_action_tool(
        *args: Any, ctx: Optional[Context] = None, **kwargs: Any
    ) -> str:
        """Execute an action on a page.

        Args:
            *args: Positional arguments based on action signature
            ctx: MCP context for logging
            **kwargs: Keyword arguments based on action signature

        Returns:
            JSON string containing action result with success status
        """
        try:
            # Build action_input dict from args and kwargs
            action_input = {}

            # Map positional args to parameter names
            for i, arg in enumerate(args):
                if i < len(param_names):
                    action_input[param_names[i]] = arg

            # Add keyword arguments
            action_input.update(kwargs)

            if ctx:
                await ctx.info(f"Executing action: {action_name}")
                await ctx.info(f"Action input: {action_input}")

            # Invoke the action through the server context
            result = await server_context.invoke_action(action_name, action_input)

            if ctx:
                await ctx.info(f"Action result: {result}")

            return json.dumps(result, indent=2)

        except Exception as e:
            error_msg = f"Action '{action_name}' failed: {str(e)}"
            if ctx:
                await ctx.error(error_msg)

            return json.dumps({"success": False, "error": str(e)}, indent=2)

    # Set the proper signature on the dynamic function
    _set_dynamic_function_signature(dynamic_action_tool, action_func, action_name)

    # Register the tool with the MCP server
    mcp.tool(description=description)(dynamic_action_tool)


def _set_dynamic_function_signature(
    dynamic_func: Any,
    original_func: ActionFunction,
    action_name: str,
) -> None:
    """Set the proper signature on a dynamic function based on the original action function.

    This transforms Page types to PageURI types and creates explicit parameters.
    """
    try:
        # Get original signature and type hints
        original_sig = inspect.signature(original_func)
        original_type_hints = get_type_hints(original_func)

        # Create new parameters with transformed types
        new_params = []
        for param_name, param in original_sig.parameters.items():
            # Get the type annotation
            param_type = original_type_hints.get(param_name, param.annotation)

            # Transform Page types to PageURI types
            transformed_type = _convert_page_type_to_uri_type(param_type)

            # Create new parameter with transformed type
            new_param = param.replace(annotation=transformed_type)
            new_params.append(new_param)

        # Add the ctx parameter for MCP context
        ctx_param = inspect.Parameter(
            "ctx",
            inspect.Parameter.KEYWORD_ONLY,
            default=None,
            annotation=Optional[Context],
        )
        new_params.append(ctx_param)

        # Create new signature
        new_sig = inspect.Signature(
            parameters=new_params, return_annotation=str  # MCP tools return strings
        )

        # Set the signature and name on the dynamic function
        dynamic_func.__signature__ = new_sig
        dynamic_func.__name__ = f"{action_name}_tool"
        dynamic_func.__qualname__ = f"{action_name}_tool"

        # Set type annotations for better introspection
        dynamic_func.__annotations__ = {
            param.name: param.annotation for param in new_params
        }
        dynamic_func.__annotations__["return"] = str

    except Exception as e:
        logger.warning(f"Failed to set signature for action {action_name}: {e}")
        # Fallback to basic naming
        dynamic_func.__name__ = f"{action_name}_tool"
        dynamic_func.__qualname__ = f"{action_name}_tool"


def _convert_page_type_to_uri_type(param_type: Any) -> Any:
    """Convert Page-related type annotations to PageURI equivalents.

    This is similar to the logic in ActionExecutorMixin but adapted for MCP.
    """
    # Direct Page type -> PageURI
    if _is_page_type(param_type):
        return PageURI

    # Handle generic types like List[Page], Optional[Page], etc.
    origin = get_origin(param_type)
    args = get_args(param_type)

    if origin in (list, List) and args and _is_page_type(args[0]):
        return List[PageURI]

    if _is_optional_page_type(param_type):
        return Union[PageURI, None]

    # For non-Page types, return unchanged
    return param_type


def _is_page_type(param_type: Any) -> bool:
    """Check if a type is Page or a subclass of Page."""
    return param_type is Page or (
        isinstance(param_type, type) and issubclass(param_type, Page)
    )


def _is_optional_page_type(param_type: Any) -> bool:
    """Check if a type is Optional[Page] or similar union with None."""
    origin = get_origin(param_type)
    args = get_args(param_type)

    if origin is Union and len(args) == 2 and type(None) in args:
        non_none_type = args[0] if args[1] is type(None) else args[1]
        return _is_page_type(non_none_type)

    return False
