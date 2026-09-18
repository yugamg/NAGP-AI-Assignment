"""
Loads the live-data MCP server's tools as LangChain tools, over the real MCP
stdio protocol via `langchain-mcp-adapters`. We deliberately do not import
`app.mcp_server.server` directly — the point of this project is the
client/server handshake, not a shortcut around it.
"""

import sys

from langchain_mcp_adapters.client import MultiServerMCPClient

from app.config import MCP_SERVER_SCRIPT


def _server_config() -> dict:
    return {
        "travel-live-data": {
            "command": sys.executable,
            "args": [str(MCP_SERVER_SCRIPT)],
            "transport": "stdio",
        }
    }


async def load_mcp_tools() -> list:
    """Spawn the MCP server and return its tools as LangChain BaseTool objects."""
    client = MultiServerMCPClient(_server_config())
    return await client.get_tools()
