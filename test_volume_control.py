#!/usr/bin/env python3
"""
Test volume control feature
"""

import os
import time
import asyncio
import threading
import json
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

# Enable automation first
print("[TEST] Enabling automation...")
result = mcp_client.call_tool("set_enabled", {"enabled": True})
print(f"[TEST] Automation enabled: {result}")

print("\n[TEST] Test 1: Get current volume")
result = mcp_client.call_tool("get_volume", {})
print(f"[TEST] Result: {result}")
volume_info = json.loads(result)
print(f"[TEST] Current volume: {volume_info['volume']}%")
print(f"[TEST] Muted: {volume_info['muted']}")
original_volume = volume_info['volume']

print("\n[TEST] Test 2: Set absolute volume to 50%")
result = mcp_client.call_tool("set_volume", {
    "volume": 50,
    "relative": False
})
print(f"[TEST] Result: {result}")
time.sleep(1)

print("\n[TEST] Test 3: Verify volume is at 50%")
result = mcp_client.call_tool("get_volume", {})
volume_info = json.loads(result)
print(f"[TEST] Current volume: {volume_info['volume']}%")
assert 48 <= volume_info['volume'] <= 52, "Volume should be around 50%"

print("\n[TEST] Test 4: Increase volume by 10% (relative)")
result = mcp_client.call_tool("set_volume", {
    "volume": 10,
    "relative": True
})
print(f"[TEST] Result: {result}")
time.sleep(1)

print("\n[TEST] Test 5: Verify volume increased")
result = mcp_client.call_tool("get_volume", {})
volume_info = json.loads(result)
print(f"[TEST] Current volume: {volume_info['volume']}%")
assert 58 <= volume_info['volume'] <= 62, "Volume should be around 60%"

print("\n[TEST] Test 6: Decrease volume by 20% (relative)")
result = mcp_client.call_tool("set_volume", {
    "volume": -20,
    "relative": True
})
print(f"[TEST] Result: {result}")
time.sleep(1)

print("\n[TEST] Test 7: Verify volume decreased")
result = mcp_client.call_tool("get_volume", {})
volume_info = json.loads(result)
print(f"[TEST] Current volume: {volume_info['volume']}%")
assert 38 <= volume_info['volume'] <= 42, "Volume should be around 40%"

print("\n[TEST] Test 8: Mute volume")
result = mcp_client.call_tool("mute_volume", {
    "mute": True
})
print(f"[TEST] Result: {result}")
time.sleep(1)

print("\n[TEST] Test 9: Verify volume is muted")
result = mcp_client.call_tool("get_volume", {})
volume_info = json.loads(result)
print(f"[TEST] Muted: {volume_info['muted']}")
assert volume_info['muted'] == True, "Volume should be muted"

print("\n[TEST] Test 10: Unmute volume")
result = mcp_client.call_tool("mute_volume", {
    "mute": False
})
print(f"[TEST] Result: {result}")
time.sleep(1)

print("\n[TEST] Test 11: Verify volume is unmuted")
result = mcp_client.call_tool("get_volume", {})
volume_info = json.loads(result)
print(f"[TEST] Muted: {volume_info['muted']}")
assert volume_info['muted'] == False, "Volume should be unmuted"

print("\n[TEST] Test 12: Restore original volume")
result = mcp_client.call_tool("set_volume", {
    "volume": original_volume,
    "relative": False
})
print(f"[TEST] Result: {result}")
print(f"[TEST] Restored volume to {original_volume}%")

print("\n[TEST] ✅ All tests passed!")
