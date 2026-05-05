#!/usr/bin/env python3
"""
Debug script to check if minimized windows appear in list_windows
"""

import os
import json
import time
import subprocess
import asyncio
import threading
from queue import Queue
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

class MCPClient:
    """Manages connection to gnome-desktop-mcp server"""

    def __init__(self):
        self.session = None
        self.read = None
        self.write = None
        self.loop = None
        self.thread = None
        self.command_queue = Queue()
        self.result_queue = Queue()

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
            command="gnome-desktop-mcp",
            args=[],
            env=os.environ.copy()
        )

        async with stdio_client(server_params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                self.session = session
                print("[DEBUG] MCP connected")

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
        """Call MCP tool synchronously"""
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

# Initialize
print("[DEBUG] Starting MCP client...")
mcp_client = MCPClient()
mcp_client.start()

# Launch text editor
print("\n[DEBUG] Launching text editor...")
subprocess.Popen(
    ["gnome-text-editor"],
    stdout=subprocess.DEVNULL,
    stderr=subprocess.DEVNULL,
    stdin=subprocess.DEVNULL,
    start_new_session=True
)
time.sleep(2)

# List windows BEFORE minimize
print("\n" + "="*60)
print("WINDOWS BEFORE MINIMIZE")
print("="*60)
result = mcp_client.call_tool("list_windows", {})
windows_before = json.loads(result)
for w in windows_before:
    if 'text' in w.get('wmClass', '').lower() or 'text' in w.get('title', '').lower():
        print(f"Window: {w.get('title', 'Unknown')}")
        print(f"  wmClass: {w.get('wmClass', 'Unknown')}")
        print(f"  ID: {w.get('id', 'Unknown')}")
        print(f"  State: {w.get('state', {})}")
        text_editor_id = w.get('id')

# Minimize the window
if text_editor_id:
    print(f"\n[DEBUG] Minimizing window ID {text_editor_id}...")
    result = mcp_client.call_tool("minimize_window", {"window_id": text_editor_id})
    print(f"[DEBUG] Minimize result: {result}")
    time.sleep(1)

# List windows AFTER minimize
print("\n" + "="*60)
print("WINDOWS AFTER MINIMIZE")
print("="*60)
result = mcp_client.call_tool("list_windows", {})
windows_after = json.loads(result)

text_editor_found = False
for w in windows_after:
    if 'text' in w.get('wmClass', '').lower() or 'text' in w.get('title', '').lower():
        text_editor_found = True
        print(f"Window: {w.get('title', 'Unknown')}")
        print(f"  wmClass: {w.get('wmClass', 'Unknown')}")
        print(f"  ID: {w.get('id', 'Unknown')}")
        print(f"  State: {w.get('state', {})}")
        print(f"  Minimized: {w.get('state', {}).get('minimized', False)}")

if not text_editor_found:
    print("❌ Text editor NOT found in window list!")
    print("This means minimized windows are excluded from list_windows")
else:
    print("✅ Text editor found in window list")

# Try to unminimize
if text_editor_id:
    print(f"\n[DEBUG] Attempting to unminimize window ID {text_editor_id}...")
    result = mcp_client.call_tool("unminimize_window", {"window_id": text_editor_id})
    print(f"[DEBUG] Unminimize result: {result}")
    time.sleep(1)

# List windows AFTER unminimize
print("\n" + "="*60)
print("WINDOWS AFTER UNMINIMIZE")
print("="*60)
result = mcp_client.call_tool("list_windows", {})
windows_final = json.loads(result)
for w in windows_final:
    if 'text' in w.get('wmClass', '').lower() or 'text' in w.get('title', '').lower():
        print(f"Window: {w.get('title', 'Unknown')}")
        print(f"  wmClass: {w.get('wmClass', 'Unknown')}")
        print(f"  ID: {w.get('id', 'Unknown')}")
        print(f"  State: {w.get('state', {})}")
        print(f"  Minimized: {w.get('state', {}).get('minimized', False)}")

# Cleanup
print("\n[DEBUG] Closing text editor...")
mcp_client.call_tool("close_window", {"window_id": text_editor_id})
print("[DEBUG] Done!")
