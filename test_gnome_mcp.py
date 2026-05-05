#!/usr/bin/env python3
"""
Simple test script to verify gnome-desktop-mcp server works
"""
import asyncio
import json
import os
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

async def test_gnome_mcp():
    """Test the gnome-desktop-mcp server"""

    # Create server parameters for gnome-desktop-mcp
    # Pass the current environment so D-Bus connection works
    server_params = StdioServerParameters(
        command="gnome-desktop-mcp",
        args=[],
        env=os.environ.copy()
    )

    print("🔌 Connecting to gnome-desktop-mcp server...")

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            # Initialize the connection
            await session.initialize()
            print("✅ Connected successfully!")

            # List available tools
            print("\n📋 Available tools from gnome-desktop-mcp:")
            tools = await session.list_tools()

            if tools and hasattr(tools, 'tools'):
                for tool in tools.tools:
                    print(f"\n  🔧 {tool.name}")
                    print(f"     Description: {tool.description[:80]}...")
            else:
                print("  No tools found!")

            # Test 1: Ping
            print("\n🧪 Test 1: Ping the extension...")
            try:
                result = await session.call_tool("ping", arguments={})
                print(f"✅ Ping result: {result.content[0].text}")
            except Exception as e:
                print(f"❌ Error: {e}")

            # Test 2: List windows
            print("\n🧪 Test 2: List open windows...")
            try:
                result = await session.call_tool("list_windows", arguments={})
                windows_data = json.loads(result.content[0].text)
                print(f"✅ Found {len(windows_data)} open windows:")
                for w in windows_data[:5]:  # Show first 5
                    print(f"   • {w.get('title', 'Untitled')} ({w.get('wmClass', 'unknown')})")
            except Exception as e:
                print(f"❌ Error: {e}")

            # Test 3: Get monitors
            print("\n🧪 Test 3: Get monitor information...")
            try:
                result = await session.call_tool("get_monitors", arguments={})
                monitors = json.loads(result.content[0].text)
                print(f"✅ Found {len(monitors)} monitor(s):")
                for m in monitors:
                    print(f"   • {m.get('width')}x{m.get('height')} at scale {m.get('scale')}")
            except Exception as e:
                print(f"❌ Error: {e}")

            print("\n🎉 All tests complete! gnome-desktop-mcp is working perfectly!")

if __name__ == "__main__":
    asyncio.run(test_gnome_mcp())
