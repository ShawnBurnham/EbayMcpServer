import asyncio
from mcp.server.models import InitializationOptions
import mcp.types as types
from mcp.server import NotificationOptions, Server
import mcp.server.stdio
from pydantic import AnyUrl
import logging
import os

from ebayAPItool import (
    get_access_token,
    make_ebay_api_request,
    make_ebay_rest_request,
)

server = Server("mcp-ebay-server")
logger = logging.getLogger("mcp-ebay-server")
logger.setLevel(logging.INFO)


## Logging
@server.set_logging_level()
async def set_logging_level(level: types.LoggingLevel) -> types.EmptyResult:
    logger.setLevel(level.upper())
    await server.request_context.session.send_log_message(
        level="info", data=f"Log level set to {level}", logger="mcp-ebay-server"
    )
    return types.EmptyResult()


## Tools
@server.list_tools()
async def handle_list_tools() -> list[types.Tool]:
    """
    List available search tools.
    """
    return [
        types.Tool(
            name="list-auction",
            description="Scan ebay for auctions. This tool is helpful for finding auctions on ebay.",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The query to search on ebay. This should just be a name not a description.",
                    },
                    "ammount": {
                        "type": "integer",
                        "description": "The ammount of results to fetch. This should be a whole non negative number.",

                    },
                    "buying_options": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Buying options to include (e.g., AUCTION, FIXED_PRICE). Defaults to both.",
                    },
                    "category_ids": {
                        "type": "array",
                        "items": {"type": "integer"},
                        "description": "Optional category IDs to restrict search results.",
                    },
                },
                "required": ["query", "ammount"],
            },
        ),
        types.Tool(
            name="ebay-api-request",
            description=(
                "Call any eBay REST API endpoint (Browse, Buy, Order, Inventory, etc.). "
                "Provide the path starting after the base URL, e.g. "
                "`/buy/browse/v1/item_summary/search`."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "method": {
                        "type": "string",
                        "description": "HTTP method to use (GET, POST, PUT, PATCH, DELETE).",
                    },
                    "path": {
                        "type": "string",
                        "description": "API path, e.g. /buy/browse/v1/item_summary/search.",
                    },
                    "params": {
                        "type": "object",
                        "description": "Query parameters for the request.",
                    },
                    "json_body": {
                        "type": "object",
                        "description": "JSON request body for POST/PUT/PATCH requests.",
                    },
                },
                "required": ["method", "path"],
            },
        ),
    ]


@server.call_tool()
async def handle_call_tool(
    name: str, arguments: dict | None
) -> list[types.TextContent | types.ImageContent | types.EmbeddedResource]:
    """
    Handle search tool execution requests.
    """
    if name not in {"list-auction", "ebay-api-request"}:
        raise ValueError(f"Unknown tool: {name}")

    if not arguments:
        raise ValueError("Missing arguments")

    CLIENT_ID = os.getenv("CLIENT_ID")
    CLIENT_SECRET = os.getenv("CLIENT_SECRET")

    try:
        access_token = get_access_token(CLIENT_ID, CLIENT_SECRET)

        if name == "list-auction":
            query = arguments.get("query")
            ammount = arguments.get("ammount")
            buying_options = arguments.get("buying_options")
            category_ids = arguments.get("category_ids")

            if not query:
                raise ValueError("Missing query")

            if not ammount:
                ammount = 1

            search_response = make_ebay_api_request(
                access_token,
                query,
                ammount,
                buying_options=buying_options,
                category_ids=category_ids,
            )
            response_payload = search_response
        else:
            method = arguments.get("method")
            path = arguments.get("path")
            params = arguments.get("params")
            json_body = arguments.get("json_body")

            if not method:
                raise ValueError("Missing method")
            if not path:
                raise ValueError("Missing path")

            response_payload = make_ebay_rest_request(
                access_token=access_token,
                method=method,
                path=path,
                params=params,
                json_body=json_body,
            )

        return [
            types.TextContent(
                type="text",
                text=str(response_payload),
            )
        ]
    except Exception as exc:
        logger.exception("eBay API call failed")
        return [
            types.TextContent(
                type="text",
                text=f"Error: {exc}",
            )
        ]


async def main():
    # Run the server using stdin/stdout streams
    async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="mcp-ebay-server",
                server_version="0.1.0",
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        )


if __name__ == "__main__":
    asyncio.run(main())
