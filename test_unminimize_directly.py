#!/usr/bin/env python3
"""
Direct test of unminimize functionality
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

print("\n[TEST] Please manually:")
print("1. Open text editor")
print("2. Minimize it")
print("3. Press Enter when ready")
input()

# Find the text editor window
print("\n[TEST] Looking for text editor window...")
result = mcp_client.call_tool("list_windows", {})
windows = json.loads(result)

text_editor_window = None
for w in windows:
    wm_class = w.get('wmClass', '').lower()
    title = w.get('title', '').lower()
    if 'texteditor' in wm_class or 'text-editor' in wm_class or 'text editor' in title:
        text_editor_window = w
        break

if not text_editor_window:
    print("[TEST] ❌ Text editor window not found!")
    print("[TEST] Available windows:")
    for w in windows:
        print(f"  - {w.get('wmClass', 'Unknown')}: {w.get('title', 'Unknown')}")
    exit(1)

window_id = text_editor_window['id']
wm_class = text_editor_window.get('wmClass', 'Unknown')
print(f"\n[TEST] Found window: {wm_class}")
print(f"[TEST] Window ID: {window_id}")
print(f"[TEST] Window state: {text_editor_window.get('state', {})}")

# Try to unminimize
print(f"\n[TEST] Calling unminimize_window with ID {window_id}...")
result = mcp_client.call_tool("unminimize_window", {"window_id": window_id})
print(f"[TEST] Result: {result}")

time.sleep(1)

# Try to also focus the window
print(f"\n[TEST] Also calling focus_window to bring it to front...")
result = mcp_client.call_tool("focus_window", {"window_id": window_id})
print(f"[TEST] Result: {result}")

time.sleep(1)

# Check if it worked
print(f"\n[TEST] Checking window state after unminimize...")
result = mcp_client.call_tool("list_windows", {})
windows = json.loads(result)

for w in windows:
    if w.get('id') == window_id:
        print(f"[TEST] Window state now: {w.get('state', {})}")
        print(f"[TEST] Focused: {w.get('state', {}).get('focused', False)}")
        break

print("\n[TEST] Did the window appear? (y/n)")
appeared = input().lower()

if appeared == 'y':
    print("[TEST] ✅ Success! Unminimize works when combined with focus")
else:
    print("[TEST] ❌ Failed. Window didn't appear even after unminimize + focus")
