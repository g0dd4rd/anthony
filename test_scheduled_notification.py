#!/usr/bin/env python3
"""
Test scheduled notification feature
"""

import os
import time
import asyncio
import threading
from queue import Queue
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

class MCPClient:
    def __init__(self):
        self.session = None
        self.read = None
        self.write = None
        self.loop = None
        self.thread = None
        self.command_queue = Queue()
        self.result_queue = Queue()

    def start(self):
        self.thread = threading.Thread(target=self._run_loop, daemon=True)
        self.thread.start()
        time.sleep(2)

    def _run_loop(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        self.loop.run_until_complete(self._connect_and_process())

    async def _connect_and_process(self):
        server_params = StdioServerParameters(
            command="gnome-desktop-mcp",
            args=[],
            env=os.environ.copy()
        )
        async with stdio_client(server_params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                self.session = session
                print("[TEST] MCP connected")
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

print("[TEST] Starting MCP client...")
mcp_client = MCPClient()
mcp_client.start()

print("\n[TEST] Test 1: Immediate notification (no delay)")
result = mcp_client.call_tool("send_notification", {
    "summary": "Immediate Test",
    "body": "This should appear right away"
})
print(f"[TEST] Result: {result}")
print("[TEST] Did you see the notification immediately? Check your desktop.")
time.sleep(2)

print("\n[TEST] Test 2: Scheduled notification in 10 seconds")
result = mcp_client.call_tool("send_notification", {
    "summary": "10 Second Test",
    "body": "This should appear in 10 seconds",
    "delay": "10 seconds"
})
print(f"[TEST] Result: {result}")
print("[TEST] Waiting for notification in 10 seconds...")
time.sleep(12)
print("[TEST] Did you see the notification after 10 seconds?")

print("\n[TEST] Test 3: Scheduled notification in 30 seconds")
result = mcp_client.call_tool("send_notification", {
    "summary": "30 Second Test",
    "body": "This should appear in 30 seconds",
    "delay": "30 seconds"
})
print(f"[TEST] Result: {result}")
print("[TEST] Waiting for notification in 30 seconds...")
time.sleep(32)
print("[TEST] Did you see the notification after 30 seconds?")

print("\n[TEST] Test 4: Scheduled notification in 1 minute")
result = mcp_client.call_tool("send_notification", {
    "summary": "1 Minute Test",
    "body": "This should appear in 1 minute",
    "delay": "1 minute"
})
print(f"[TEST] Result: {result}")
print("[TEST] This one is scheduled for 1 minute from now.")
print("[TEST] Wait 1 minute and check if notification appears.")
print("[TEST] (Script will exit, but notification will still fire)")

print("\n[TEST] ✅ All tests scheduled successfully!")
print("[TEST] Keep the script running to see all notifications.")

# Keep script alive to see the 1 minute notification
time.sleep(70)
print("\n[TEST] Tests complete!")
