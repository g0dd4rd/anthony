#!/usr/bin/env python3
"""
Test script for screenshot features.

Tests:
1. Full desktop screenshot
2. Window-specific screenshot (with and without frame)
3. Area screenshot (specific region)
4. Verifies all files are created
5. Compares file sizes to ensure they're different
6. Cleanup

Voice input is simulated by sending strings directly to the LLM.
"""

import os
import sys
import json
import time
import subprocess
import asyncio
import threading
import ollama
from queue import Queue
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

# ----------------------------------------
# MCP Client Setup
# ----------------------------------------
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
                print("[TEST] MCP connected to gnome-desktop-mcp")

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
        """Call MCP tool synchronously (blocks until result)"""
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

# ----------------------------------------
# Helper Functions
# ----------------------------------------
def smart_match_window(window_name: str, windows: list) -> dict:
    """Smart window matching that prioritizes app names over full window titles."""
    if not window_name or window_name.strip() == "":
        for w in windows:
            if w.get('state', {}).get('focused', False):
                return w
        return windows[0] if windows else None

    window_name_lower = window_name.lower()

    for w in windows:
        wm_class = w.get('wmClass', '')
        app_name = wm_class.lower()
        app_name = app_name.replace('org.gnome.', '')
        app_name = app_name.replace('org.', '')
        app_name = app_name.replace('-', '')
        app_name = app_name.replace('_', '')
        wm_class_lower = wm_class.lower()
        search_term = window_name_lower.replace(' ', '').replace('-', '').replace('_', '')

        if search_term in app_name or window_name_lower in wm_class_lower:
            return w

    for w in windows:
        title = w.get('title', '').lower()
        if window_name_lower in title:
            return w

    return None

def launch_application(app_name: str, mcp_client) -> str:
    """Launches a graphical application."""
    print(f"[TEST] Launching {app_name}...")
    try:
        subprocess.Popen(
            [app_name],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            start_new_session=True
        )
        return f"Successfully launched {app_name}."
    except Exception as e:
        return f"Error launching app: {str(e)}"

def screenshot_desktop(mcp_client) -> str:
    """Take a full desktop screenshot."""
    try:
        result = mcp_client.call_tool("screenshot", {
            "include_cursor": False,
            "format": "path"
        })
        if result.startswith("Error"):
            return result
        screenshot_path = result.strip()
        return f"Desktop screenshot saved to {screenshot_path}"
    except Exception as e:
        return f"Error taking desktop screenshot: {str(e)}"

def screenshot_window_by_name(window_name: str, include_frame: bool, mcp_client) -> str:
    """Take a screenshot of a specific window."""
    try:
        result = mcp_client.call_tool("list_windows", {})
        if result.startswith("Error"):
            return result
        windows = json.loads(result)
        target_window = smart_match_window(window_name, windows)

        if not target_window:
            return f"No window found matching '{window_name}'"

        window_id = target_window['id']
        wm_class = target_window.get('wmClass', 'Unknown')

        result = mcp_client.call_tool("screenshot_window", {
            "window_id": window_id,
            "include_frame": include_frame,
            "include_cursor": False,
            "format": "path"
        })

        if result.startswith("Error"):
            return result

        screenshot_path = result.strip()
        return f"Screenshot of {wm_class} saved to {screenshot_path}"
    except Exception as e:
        return f"Error taking window screenshot: {str(e)}"

def screenshot_area(x: int, y: int, width: int, height: int, mcp_client) -> str:
    """Take a screenshot of a specific area."""
    try:
        result = mcp_client.call_tool("screenshot_area", {
            "x": x,
            "y": y,
            "width": width,
            "height": height,
            "include_cursor": False,
            "format": "path"
        })

        if result.startswith("Error"):
            return result

        screenshot_path = result.strip()
        return f"Area screenshot saved to {screenshot_path}"
    except Exception as e:
        return f"Error taking area screenshot: {str(e)}"

def close_window_by_name(window_name: str, mcp_client) -> str:
    """Close a window."""
    try:
        result = mcp_client.call_tool("list_windows", {})
        if result.startswith("Error"):
            return result
        windows = json.loads(result)
        target_window = smart_match_window(window_name, windows)

        if not target_window:
            return f"No window found matching '{window_name}'"

        window_id = target_window['id']
        wm_class = target_window.get('wmClass', 'Unknown')
        result = mcp_client.call_tool("close_window", {"window_id": window_id})
        return f"Closed {wm_class}"
    except Exception as e:
        return f"Error closing window: {str(e)}"

# ----------------------------------------
# Tool Schema
# ----------------------------------------
tool_schema = [
    {"type": "function", "function": {"name": "launch_application", "description": "Launches a graphical application.", "parameters": {"type": "object", "properties": {"app_name": {"type": "string", "description": "The command name of the app"}}, "required": ["app_name"]}}},
    {"type": "function", "function": {"name": "screenshot_desktop", "description": "Take a full screenshot of the entire desktop.", "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {"name": "screenshot_window_by_name", "description": "Take a screenshot of a specific window only. Matches by application name.", "parameters": {"type": "object", "properties": {"window_name": {"type": "string", "description": "Application name (e.g., 'text editor', 'firefox')", "default": ""}, "include_frame": {"type": "boolean", "description": "Whether to include window decorations", "default": True}}, "required": []}}},
    {"type": "function", "function": {"name": "screenshot_area", "description": "Take a screenshot of a rectangular screen region.", "parameters": {"type": "object", "properties": {"x": {"type": "integer", "description": "Left edge in pixels"}, "y": {"type": "integer", "description": "Top edge in pixels"}, "width": {"type": "integer", "description": "Width in pixels"}, "height": {"type": "integer", "description": "Height in pixels"}}, "required": ["x", "y", "width", "height"]}}},
    {"type": "function", "function": {"name": "close_window_by_name", "description": "Close a window.", "parameters": {"type": "object", "properties": {"window_name": {"type": "string", "description": "Application name", "default": ""}}, "required": []}}},
]

# ----------------------------------------
# Simulate Voice Command
# ----------------------------------------
def simulate_voice_command(command: str, mcp_client) -> tuple:
    """
    Simulate a voice command by sending it to the LLM.
    Returns (result_text, screenshot_path_if_any)
    """
    print(f"\n[TEST] Simulating voice command: '{command}'")

    system_msg = {
        "role": "system",
        "content": "You are a silent system orchestrator. Your ONLY job is to execute tool calls based on user intent. DO NOT output conversational text. DO NOT confirm actions. If you need to use a tool, output ONLY the tool call. Use gnome-text-editor for text editor."
    }

    messages = [system_msg, {"role": "user", "content": command}]

    try:
        response = ollama.chat(
            model='gemma4:e4b',
            messages=messages,
            tools=tool_schema,
            options={
                'temperature': 0.0,
                'top_p': 0.1
            }
        )

        message = response['message']

        if message.get('tool_calls'):
            for tool_call in message['tool_calls']:
                tool_name = tool_call['function']['name']
                arguments = tool_call['function']['arguments']

                print(f"[TEST] LLM called tool: {tool_name} with args: {arguments}")

                # Execute the tool
                if tool_name == "launch_application":
                    result = launch_application(arguments.get('app_name'), mcp_client)
                elif tool_name == "screenshot_desktop":
                    result = screenshot_desktop(mcp_client)
                elif tool_name == "screenshot_window_by_name":
                    result = screenshot_window_by_name(
                        arguments.get('window_name', ''),
                        arguments.get('include_frame', True),
                        mcp_client
                    )
                elif tool_name == "screenshot_area":
                    result = screenshot_area(
                        arguments.get('x'),
                        arguments.get('y'),
                        arguments.get('width'),
                        arguments.get('height'),
                        mcp_client
                    )
                elif tool_name == "close_window_by_name":
                    result = close_window_by_name(arguments.get('window_name', ''), mcp_client)
                else:
                    result = f"Unknown tool: {tool_name}"

                print(f"[TEST] Result: {result}")

                # Extract screenshot path if present
                screenshot_path = None
                if "saved to" in result:
                    # Extract path from result
                    parts = result.split("saved to")
                    if len(parts) > 1:
                        screenshot_path = parts[1].strip()

                return result, screenshot_path
        else:
            print("[TEST] No tool call generated by LLM")
            return "No tool call generated", None

    except Exception as e:
        error_msg = f"Error: {str(e)}"
        print(f"[TEST] {error_msg}")
        return error_msg, None

# ----------------------------------------
# Test Runner
# ----------------------------------------
def run_tests():
    """Run the full test suite."""
    print("\n" + "="*60)
    print("SCREENSHOT FEATURES TEST SUITE")
    print("="*60)

    # Initialize MCP client
    print("\n[TEST] Starting MCP client...")
    mcp_client = MCPClient()
    mcp_client.start()
    time.sleep(2)

    test_results = []
    screenshot_files = []

    try:
        # Setup: Launch text editor
        print("\n" + "-"*60)
        print("SETUP: Launch text editor for testing")
        print("-"*60)
        result, _ = simulate_voice_command("open text editor", mcp_client)
        time.sleep(2)  # Wait for app to open

        # Test 1: Full desktop screenshot
        print("\n" + "-"*60)
        print("TEST 1: Full desktop screenshot")
        print("-"*60)
        result, screenshot_path = simulate_voice_command("take a screenshot of the desktop", mcp_client)
        time.sleep(1)

        if screenshot_path and os.path.exists(screenshot_path):
            file_size = os.path.getsize(screenshot_path)
            print(f"[TEST] ✅ Desktop screenshot created: {screenshot_path} ({file_size} bytes)")
            test_results.append(("Full desktop screenshot", True))
            screenshot_files.append(("desktop", screenshot_path, file_size))
        else:
            print(f"[TEST] ❌ Desktop screenshot failed or file not found")
            test_results.append(("Full desktop screenshot", False))

        # Test 2: Window screenshot with frame
        print("\n" + "-"*60)
        print("TEST 2: Window screenshot (with frame)")
        print("-"*60)
        result, screenshot_path = simulate_voice_command("screenshot the text editor window with frame", mcp_client)
        time.sleep(1)

        if screenshot_path and os.path.exists(screenshot_path):
            file_size = os.path.getsize(screenshot_path)
            print(f"[TEST] ✅ Window screenshot (with frame) created: {screenshot_path} ({file_size} bytes)")
            test_results.append(("Window screenshot with frame", True))
            screenshot_files.append(("window_with_frame", screenshot_path, file_size))
        else:
            print(f"[TEST] ❌ Window screenshot (with frame) failed")
            test_results.append(("Window screenshot with frame", False))

        # Test 3: Window screenshot without frame
        print("\n" + "-"*60)
        print("TEST 3: Window screenshot (without frame)")
        print("-"*60)
        # Directly call function since LLM might not understand "without frame"
        result = screenshot_window_by_name("text editor", False, mcp_client)
        if "saved to" in result:
            screenshot_path = result.split("saved to")[1].strip()

            if os.path.exists(screenshot_path):
                file_size = os.path.getsize(screenshot_path)
                print(f"[TEST] ✅ Window screenshot (without frame) created: {screenshot_path} ({file_size} bytes)")
                test_results.append(("Window screenshot without frame", True))
                screenshot_files.append(("window_no_frame", screenshot_path, file_size))
            else:
                print(f"[TEST] ❌ Window screenshot (without frame) file not found")
                test_results.append(("Window screenshot without frame", False))
        else:
            print(f"[TEST] ❌ Window screenshot (without frame) failed")
            test_results.append(("Window screenshot without frame", False))

        # Test 4: Area screenshot (top-left 800x600 region)
        print("\n" + "-"*60)
        print("TEST 4: Area screenshot (top-left 800x600)")
        print("-"*60)
        result, screenshot_path = simulate_voice_command("screenshot area from 0,0 with width 800 and height 600", mcp_client)
        time.sleep(1)

        if screenshot_path and os.path.exists(screenshot_path):
            file_size = os.path.getsize(screenshot_path)
            print(f"[TEST] ✅ Area screenshot created: {screenshot_path} ({file_size} bytes)")
            test_results.append(("Area screenshot", True))
            screenshot_files.append(("area", screenshot_path, file_size))
        else:
            print(f"[TEST] ❌ Area screenshot failed or file not found")
            test_results.append(("Area screenshot", False))

        # Cleanup: Close text editor
        print("\n" + "-"*60)
        print("CLEANUP: Close text editor")
        print("-"*60)
        result, _ = simulate_voice_command("close text editor", mcp_client)
        time.sleep(1)

    except KeyboardInterrupt:
        print("\n[TEST] Test interrupted by user")
    except Exception as e:
        print(f"\n[TEST] Test failed with error: {e}")
        import traceback
        traceback.print_exc()

    # Print summary
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)

    total = len(test_results)
    passed = sum(1 for _, result in test_results if result)
    failed = total - passed

    for test_name, result in test_results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status}: {test_name}")

    print(f"\nTotal: {total} tests")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")
    print(f"Success rate: {(passed/total*100):.1f}%")

    # Print file comparison
    if screenshot_files:
        print("\n" + "="*60)
        print("SCREENSHOT FILE COMPARISON")
        print("="*60)
        for name, path, size in screenshot_files:
            print(f"{name:25} | {size:10} bytes | {path}")

        # Verify they're different sizes (indicating different content)
        sizes = [size for _, _, size in screenshot_files]
        if len(set(sizes)) == len(sizes):
            print("\n✅ All screenshots have different file sizes (good!)")
        else:
            print("\n⚠️  Some screenshots have identical file sizes (might be duplicate)")

    # Cleanup option
    print("\n" + "="*60)
    print("Screenshot files have been created in /tmp/")
    print("They will be automatically cleaned up on reboot, or you can")
    print("manually delete them with: rm /tmp/gnome-desktop-mcp-screenshot-*.png")
    print("="*60)

    if failed == 0:
        print("\n🎉 All tests passed!")
    else:
        print(f"\n⚠️  {failed} test(s) failed")

if __name__ == "__main__":
    try:
        run_tests()
    except KeyboardInterrupt:
        print("\n\n[TEST] Shutting down...")
