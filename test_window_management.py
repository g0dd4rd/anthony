#!/usr/bin/env python3
"""
Test script for window management features.

Tests:
1. Opens text editor
2. Maximizes the window and verifies state
3. Restores the window and verifies state
4. Minimizes the window and verifies state
5. Closes the text editor

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
# MCP Client Setup (from orchestrator)
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
# Tool Functions (from orchestrator)
# ----------------------------------------
def smart_match_window(window_name: str, windows: list) -> dict:
    """Smart window matching that prioritizes app names over full window titles."""
    if not window_name or window_name.strip() == "":
        # Find focused window
        for w in windows:
            if w.get('state', {}).get('focused', False):
                return w
        return windows[0] if windows else None

    window_name_lower = window_name.lower()

    # Try app name matching first (from wmClass)
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

    # Fall back to title matching
    for w in windows:
        title = w.get('title', '').lower()
        if window_name_lower in title:
            return w

    return None

def launch_application(app_name: str, mcp_client) -> str:
    """Launches a graphical application in the background."""
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

def maximize_window_by_name(window_name: str, mcp_client) -> str:
    """Toggle maximize/restore for a window."""
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
        state = target_window.get('state', {})
        is_maximized = state.get('maximized', False)

        if is_maximized:
            result = mcp_client.call_tool("unmaximize_window", {"window_id": window_id})
            return f"Restored {wm_class}"
        else:
            result = mcp_client.call_tool("maximize_window", {"window_id": window_id})
            return f"Maximized {wm_class}"
    except Exception as e:
        return f"Error toggling window maximize: {str(e)}"

def minimize_window_by_name(window_name: str, mcp_client) -> str:
    """Minimize a window."""
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
        result = mcp_client.call_tool("minimize_window", {"window_id": window_id})
        return f"Minimized {wm_class}"
    except Exception as e:
        return f"Error minimizing window: {str(e)}"

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

def get_window_state(window_name: str, mcp_client) -> dict:
    """Get the current state of a window."""
    try:
        result = mcp_client.call_tool("list_windows", {})
        if result.startswith("Error"):
            return None
        windows = json.loads(result)
        target_window = smart_match_window(window_name, windows)

        if not target_window:
            return None

        return target_window.get('state', {})
    except Exception as e:
        print(f"[TEST] Error getting window state: {e}")
        return None

# ----------------------------------------
# Tool Schema (from orchestrator)
# ----------------------------------------
tool_schema = [
    {"type": "function", "function": {"name": "launch_application", "description": "Launches a graphical application on the Linux desktop.", "parameters": {"type": "object", "properties": {"app_name": {"type": "string", "description": "The command name of the app"}}, "required": ["app_name"]}}},
    {"type": "function", "function": {"name": "maximize_window_by_name", "description": "Toggle maximize/restore for a window. Matches by application name (e.g., 'text editor'). If window_name is empty, uses the current window.", "parameters": {"type": "object", "properties": {"window_name": {"type": "string", "description": "Application name (e.g., 'text editor', 'firefox'). Leave empty to use current window.", "default": ""}}, "required": []}}},
    {"type": "function", "function": {"name": "minimize_window_by_name", "description": "Minimize (hide) a window. Matches by application name (e.g., 'text editor').", "parameters": {"type": "object", "properties": {"window_name": {"type": "string", "description": "Application name", "default": ""}}, "required": []}}},
    {"type": "function", "function": {"name": "close_window_by_name", "description": "Close a window by application name.", "parameters": {"type": "object", "properties": {"window_name": {"type": "string", "description": "Application name", "default": ""}}, "required": []}}},
]

# ----------------------------------------
# Simulate Voice Command
# ----------------------------------------
def simulate_voice_command(command: str, mcp_client) -> str:
    """
    Simulate a voice command by sending it to the LLM.
    Returns the result of executing the tool call.
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
                elif tool_name == "maximize_window_by_name":
                    result = maximize_window_by_name(arguments.get('window_name', ''), mcp_client)
                elif tool_name == "minimize_window_by_name":
                    result = minimize_window_by_name(arguments.get('window_name', ''), mcp_client)
                elif tool_name == "close_window_by_name":
                    result = close_window_by_name(arguments.get('window_name', ''), mcp_client)
                else:
                    result = f"Unknown tool: {tool_name}"

                print(f"[TEST] Result: {result}")
                return result
        else:
            print("[TEST] No tool call generated by LLM")
            return "No tool call generated"

    except Exception as e:
        error_msg = f"Error: {str(e)}"
        print(f"[TEST] {error_msg}")
        return error_msg

# ----------------------------------------
# Test Runner
# ----------------------------------------
def run_tests():
    """Run the full test suite."""
    print("\n" + "="*60)
    print("WINDOW MANAGEMENT TEST SUITE")
    print("="*60)

    # Initialize MCP client
    print("\n[TEST] Starting MCP client...")
    mcp_client = MCPClient()
    mcp_client.start()
    time.sleep(2)

    test_results = []

    try:
        # Test 1: Launch text editor
        print("\n" + "-"*60)
        print("TEST 1: Launch text editor")
        print("-"*60)
        result = simulate_voice_command("open text editor", mcp_client)
        time.sleep(2)  # Wait for app to open

        # Verify window opened
        state = get_window_state("text editor", mcp_client)
        if state is not None:
            print("[TEST] ✅ Text editor opened successfully")
            test_results.append(("Launch text editor", True))
        else:
            print("[TEST] ❌ Text editor failed to open")
            test_results.append(("Launch text editor", False))
            return  # Can't continue if app didn't open

        # Test 2: Maximize window
        print("\n" + "-"*60)
        print("TEST 2: Maximize text editor window")
        print("-"*60)
        result = simulate_voice_command("maximize text editor", mcp_client)
        time.sleep(1)

        # Verify maximized
        state = get_window_state("text editor", mcp_client)
        if state and state.get('maximized', False):
            print("[TEST] ✅ Window maximized successfully")
            test_results.append(("Maximize window", True))
        else:
            print(f"[TEST] ❌ Window not maximized. State: {state}")
            test_results.append(("Maximize window", False))

        # Test 3: Restore window (unmaximize)
        print("\n" + "-"*60)
        print("TEST 3: Restore text editor window")
        print("-"*60)
        result = simulate_voice_command("restore text editor", mcp_client)
        time.sleep(1)

        # Verify restored (not maximized)
        state = get_window_state("text editor", mcp_client)
        if state and not state.get('maximized', False):
            print("[TEST] ✅ Window restored successfully")
            test_results.append(("Restore window", True))
        else:
            print(f"[TEST] ❌ Window still maximized. State: {state}")
            test_results.append(("Restore window", False))

        # Test 4: Minimize window
        print("\n" + "-"*60)
        print("TEST 4: Minimize text editor window")
        print("-"*60)
        result = simulate_voice_command("minimize text editor", mcp_client)
        time.sleep(1)

        # Verify minimized
        state = get_window_state("text editor", mcp_client)
        if state and state.get('minimized', False):
            print("[TEST] ✅ Window minimized successfully")
            test_results.append(("Minimize window", True))
        else:
            print(f"[TEST] ❌ Window not minimized. State: {state}")
            test_results.append(("Minimize window", False))

        # Test 5: Close window
        print("\n" + "-"*60)
        print("TEST 5: Close text editor window")
        print("-"*60)
        result = simulate_voice_command("close text editor", mcp_client)
        time.sleep(1)

        # Verify closed (window should not exist)
        state = get_window_state("text editor", mcp_client)
        if state is None:
            print("[TEST] ✅ Window closed successfully")
            test_results.append(("Close window", True))
        else:
            print(f"[TEST] ❌ Window still exists. State: {state}")
            test_results.append(("Close window", False))

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

    if failed == 0:
        print("\n🎉 All tests passed!")
    else:
        print(f"\n⚠️  {failed} test(s) failed")

if __name__ == "__main__":
    try:
        run_tests()
    except KeyboardInterrupt:
        print("\n\n[TEST] Shutting down...")
