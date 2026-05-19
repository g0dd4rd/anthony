#!/usr/bin/env python3
"""
Simple MCP client for testing anthony-mcp tools
"""

import os
import asyncio
import threading
import time
from queue import Queue

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


class MCPClient:
    """Manages connection to anthony-mcp server"""

    def __init__(self, server_command="anthony-mcp"):
        """Initialize MCP client.

        Args:
            server_command: Command to start the MCP server (default: anthony-mcp)
        """
        self.server_command = server_command
        self.session = None
        self.read = None
        self.write = None
        self.loop = None
        self.thread = None
        self.command_queue = Queue()
        self.result_queue = Queue()
        self.start()

    def start(self):
        """Start MCP client in background thread"""
        self.thread = threading.Thread(target=self._run_loop, daemon=True)
        self.thread.start()
        time.sleep(2)

    def _run_loop(self):
        """Run async event loop in background thread"""
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        self.loop.run_until_complete(self._connect_and_process())

    async def _connect_and_process(self):
        """Connect to MCP server and process commands"""
        server_params = StdioServerParameters(
            command=self.server_command,
            args=[],
            env=os.environ.copy()
        )

        async with stdio_client(server_params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                self.session = session
                print(f"[MCP] Connected to {self.server_command}")

                while True:
                    if not self.command_queue.empty():
                        tool_name, arguments = self.command_queue.get()
                        try:
                            result = await session.call_tool(tool_name, arguments=arguments)
                            result_text = result.content[0].text
                            self.result_queue.put(("success", result_text))
                        except Exception as e:
                            self.result_queue.put(("error", str(e)))
                    await asyncio.sleep(0.01)

    def call_tool(self, tool_name: str, arguments: dict, timeout: float = 10.0) -> str:
        """Call MCP tool synchronously (blocks until result)

        Args:
            tool_name: Name of the MCP tool to call
            arguments: Dictionary of arguments for the tool
            timeout: Maximum time to wait for result in seconds

        Returns:
            Result text from the tool
        """
        self.command_queue.put((tool_name, arguments))

        start_time = time.time()
        while self.result_queue.empty():
            if time.time() - start_time > timeout:
                return f"Error: Tool call timed out after {timeout}s"
            time.sleep(0.01)

        status, result = self.result_queue.get()
        if status == "error":
            return f"Error: {result}"
        return result
