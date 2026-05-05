#!/usr/bin/env python3
"""
Query gnome-desktop-mcp for available tools
"""

import asyncio
import os
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

async def list_tools():
    server_params = StdioServerParameters(
        command="gnome-desktop-mcp",
        args=[],
        env=os.environ.copy()
    )

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            # List all available tools
            tools_result = await session.list_tools()

            print("="*60)
            print("GNOME Desktop MCP - Available Tools")
            print("="*60)
            print()

            for tool in tools_result.tools:
                print(f"📦 {tool.name}")
                print(f"   {tool.description}")

                if hasattr(tool, 'inputSchema') and tool.inputSchema:
                    schema = tool.inputSchema
                    if 'properties' in schema:
                        print(f"   Parameters:")
                        for param_name, param_info in schema['properties'].items():
                            param_type = param_info.get('type', 'unknown')
                            param_desc = param_info.get('description', '')
                            required = param_name in schema.get('required', [])
                            req_marker = " (required)" if required else " (optional)"
                            print(f"      - {param_name}: {param_type}{req_marker}")
                            if param_desc:
                                print(f"        → {param_desc}")
                print()

if __name__ == "__main__":
    asyncio.run(list_tools())
