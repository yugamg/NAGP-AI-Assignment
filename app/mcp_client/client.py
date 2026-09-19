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
    client = MultiServerMCPClient(_server_config())
    return await client.get_tools()
