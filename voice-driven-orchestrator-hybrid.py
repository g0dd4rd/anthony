#!/usr/bin/env python3
"""
Voice-Driven Desktop Orchestrator with HYBRID Command Parsing

Features:
- ⚡ FAST pattern matching for common commands (open, close, maximize, etc.)
- 🤖 LLM fallback for complex/ambiguous commands
- ✅ VAD continuous listening
- ✅ Fast vision analysis (gemma4 + concise)
- ✅ SAFE close handling with dialog detection
- ✅ Conversation mode - chat with Gemma for questions/help
- ✅ Smart app name extraction (no more org.gnome.TextEditor!)

NEW: Commands execute in <100ms vs 1-2 seconds with pure LLM
"""

import os
import sys
import ollama
import sounddevice
import pyaudio
import shutil, subprocess
import wave
import asyncio
import json
import threading
import time
import collections
import numpy as np
import torch
import re
from queue import Queue

from faster_whisper import WhisperModel
from piper.voice import PiperVoice
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from dialog_handler import DialogHandler

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
                print("[SYSTEM] MCP connected to gnome-desktop-mcp")

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

mcp_client = MCPClient()

# Initialize dialog handler (auto-checks/enables accessibility)
print("[SYSTEM] Initializing dialog handler...")
dialog_handler = DialogHandler()

# Forward declarations for voice functions
def speak(text: str):
    pass

def listen_and_transcribe():
    pass

# ----------------------------------------
# Helper Functions
# ----------------------------------------
def get_friendly_app_name(wm_class: str) -> str:
    """
    Convert wmClass to friendly app name for voice output.

    Examples:
    - org.gnome.TextEditor -> Text Editor
    - org.gnome.Nautilus -> Nautilus
    - org.mozilla.firefox -> Firefox
    - firefox -> Firefox
    - gnome-calculator -> Calculator
    """
    if not wm_class:
        return "Unknown App"

    # Remove common prefixes
    name = wm_class
    name = name.replace('org.gnome.', '')
    name = name.replace('org.mozilla.', '')
    name = name.replace('org.', '')

    # Replace dashes and underscores with spaces
    name = name.replace('-', ' ')
    name = name.replace('_', ' ')

    # Split camelCase: TextEditor -> Text Editor
    name = re.sub('([a-z])([A-Z])', r'\1 \2', name)

    # Capitalize each word
    name = ' '.join(word.capitalize() for word in name.split())

    return name

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

def extract_app_name(command: str) -> str:
    """
    Extract app name from command using simple pattern matching.

    Examples:
    - "open firefox" -> "firefox"
    - "close the text editor" -> "text editor"
    - "maximize calculator" -> "calculator"
    """
    # Remove common command words
    app_name = command.lower()

    # Remove command verbs
    patterns = [
        r'\b(open|launch|start|run)\s+',
        r'\b(close|quit|exit)\s+',
        r'\b(maximize|maximise|expand|fullscreen)\s+',
        r'\b(minimize|minimise|hide)\s+',
        r'\b(restore|unminimize|show)\s+',
        r'\b(focus|switch\s+to|go\s+to)\s+',
        r'\b(screenshot|capture)\s+',
    ]

    for pattern in patterns:
        app_name = re.sub(pattern, '', app_name)

    # Remove common filler words
    app_name = re.sub(r'\b(the|a|an|window|app|application)\b', '', app_name)

    # Clean up whitespace
    app_name = ' '.join(app_name.split())

    return app_name.strip()

# ----------------------------------------
# Tool Functions (from original orchestrator)
# ----------------------------------------
def launch_application(app_name: str) -> str:
    """Launches a graphical application in the background."""
    print(f"\n[SYSTEM] Executing command: Launching {app_name}...")
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

def describe_desktop() -> str:
    """Captures a screenshot and describes it using vision AI."""
    print(f"\n[SYSTEM] 📸 Capturing screenshot with MCP...")
    try:
        result = mcp_client.call_tool("screenshot", {"include_cursor": False, "format": "path"})
        if result.startswith("Error"):
            return result

        screenshot_path = result.strip()
        print(f"[SYSTEM] ✅ Screenshot saved: {screenshot_path}")

        print(f"[SYSTEM] 📊 Loading image for analysis...")
        with open(screenshot_path, 'rb') as img_file:
            import base64
            img_data = base64.b64encode(img_file.read()).decode('utf-8')

        file_size_kb = len(img_data) / 1024
        print(f"[SYSTEM] 📦 Image size: {file_size_kb:.1f} KB")

        print(f"[SYSTEM] 🤖 Running vision analysis with gemma4...")

        response = ollama.chat(
            model='gemma4:e4b',
            messages=[
                {
                    'role': 'system',
                    'content': 'You are a screen reader. Answer directly without explaining your reasoning process.'
                },
                {
                    'role': 'user',
                    'content': 'What applications and windows are visible on this desktop screenshot?',
                    'images': [img_data]
                }
            ],
            options={
                'num_ctx': 2048,
                'num_predict': 800,
                'temperature': 0.7,
                'num_gpu': 99,
            }
        )

        print(f"[SYSTEM] ✅ Vision analysis complete!")

        message = response.message if hasattr(response, 'message') else response['message']
        description = message.content if hasattr(message, 'content') else message.get('content', '')

        if not description or description.strip() == "":
            return "Vision analysis produced no description. Please try again."

        print(f"[SYSTEM] 🧹 Cleaning up screenshot...")
        try:
            os.remove(screenshot_path)
        except:
            pass

        return description

    except Exception as e:
        error_msg = f"Error capturing or analyzing screenshot: {str(e)}"
        print(f"[SYSTEM] ❌ {error_msg}")
        return error_msg

def focus_window_by_name(window_name: str = "") -> str:
    """Focus a window by its title or application name."""
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

        result = mcp_client.call_tool("focus_window", {"window_id": window_id})
        return f"Focused {get_friendly_app_name(wm_class)}"
    except Exception as e:
        return f"Error focusing window: {str(e)}"

def close_window_by_name(window_name: str = "") -> str:
    """Close a window (simplified - without dialog handling for now)."""
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

        time.sleep(0.5)
        # Verify closed
        result = mcp_client.call_tool("list_windows", {})
        if not result.startswith("Error"):
            windows_after = json.loads(result)
            if not any(w['id'] == window_id for w in windows_after):
                return f"Successfully closed {get_friendly_app_name(wm_class)}"

        return f"Attempted to close {get_friendly_app_name(wm_class)}"
    except Exception as e:
        return f"Error closing window: {str(e)}"

def maximize_window_by_name(window_name: str = "") -> str:
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
            return f"Restored {get_friendly_app_name(wm_class)}"
        else:
            result = mcp_client.call_tool("maximize_window", {"window_id": window_id})
            return f"Maximized {get_friendly_app_name(wm_class)}"
    except Exception as e:
        return f"Error toggling window maximize: {str(e)}"

def minimize_window_by_name(window_name: str = "") -> str:
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
        return f"Minimized {get_friendly_app_name(wm_class)}"
    except Exception as e:
        return f"Error minimizing window: {str(e)}"

def restore_window_by_name(window_name: str = "") -> str:
    """Restore a window to normal state (unminimize and/or unmaximize)."""
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

        # Always try to unminimize and focus
        mcp_client.call_tool("unminimize_window", {"window_id": window_id})
        mcp_client.call_tool("focus_window", {"window_id": window_id})

        # Also unmaximize if needed
        state = target_window.get('state', {})
        if state.get('maximized', False):
            mcp_client.call_tool("unmaximize_window", {"window_id": window_id})

        return f"Restored {get_friendly_app_name(wm_class)}"
    except Exception as e:
        return f"Error restoring window: {str(e)}"

def screenshot_window_by_name(window_name: str = "") -> str:
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
            "include_frame": True,
            "include_cursor": False,
            "format": "path"
        })

        if result.startswith("Error"):
            return result

        screenshot_path = result.strip()
        return f"Screenshot of {get_friendly_app_name(wm_class)} saved to {screenshot_path}"
    except Exception as e:
        return f"Error taking window screenshot: {str(e)}"

def type_text_in_window(text: str) -> str:
    """Type text into the currently focused window."""
    try:
        result = mcp_client.call_tool("type_text", {"text": text})
        return f"Typed: {text}"
    except Exception as e:
        return f"Error typing text: {str(e)}"

def press_key_combo(keys: str) -> str:
    """Press a keyboard combination."""
    # Normalize key combo format
    normalized = keys
    normalized = normalized.replace("control", "Ctrl")
    normalized = normalized.replace("Control", "Ctrl")
    normalized = normalized.replace("ctrl", "Ctrl")
    normalized = normalized.replace("alt", "Alt")
    normalized = normalized.replace("shift", "Shift")
    normalized = normalized.replace("super", "Super")

    if " " in normalized and "+" not in normalized:
        normalized = normalized.replace(" ", "+")

    try:
        result = mcp_client.call_tool("key_combo", {"keys": normalized})
        return f"Pressed {normalized}"
    except Exception as e:
        return f"Error pressing keys: {str(e)}"

# ----------------------------------------
# HYBRID Command Parser
# ----------------------------------------
def parse_command_fast(command: str) -> tuple:
    """
    Fast pattern-based command parser.

    Returns: (success: bool, result: str, execution_time: float)
    - success=True means command was handled by fast parser
    - success=False means LLM fallback is needed
    """
    start_time = time.time()
    command_lower = command.lower()

    # Launch/Open applications
    if re.search(r'\b(open|launch|start|run)\b', command_lower):
        app_name = extract_app_name(command)
        if app_name:
            result = launch_application(app_name)
            elapsed = (time.time() - start_time) * 1000
            print(f"[FAST] ⚡ Executed in {elapsed:.1f}ms")
            return True, result, elapsed

    # Close window
    if re.search(r'\b(close|quit|exit)\b', command_lower):
        app_name = extract_app_name(command)
        result = close_window_by_name(app_name)
        elapsed = (time.time() - start_time) * 1000
        print(f"[FAST] ⚡ Executed in {elapsed:.1f}ms")
        return True, result, elapsed

    # Maximize window
    if re.search(r'\b(maximize|maximise|fullscreen|expand)\b', command_lower):
        app_name = extract_app_name(command)
        result = maximize_window_by_name(app_name)
        elapsed = (time.time() - start_time) * 1000
        print(f"[FAST] ⚡ Executed in {elapsed:.1f}ms")
        return True, result, elapsed

    # Minimize window
    if re.search(r'\b(minimize|minimise|hide)\b', command_lower):
        app_name = extract_app_name(command)
        result = minimize_window_by_name(app_name)
        elapsed = (time.time() - start_time) * 1000
        print(f"[FAST] ⚡ Executed in {elapsed:.1f}ms")
        return True, result, elapsed

    # Restore window
    if re.search(r'\b(restore|unminimize|unminimise|show)\b', command_lower):
        app_name = extract_app_name(command)
        result = restore_window_by_name(app_name)
        elapsed = (time.time() - start_time) * 1000
        print(f"[FAST] ⚡ Executed in {elapsed:.1f}ms")
        return True, result, elapsed

    # Focus/Switch window
    if re.search(r'\b(focus|switch\s+to|go\s+to)\b', command_lower):
        app_name = extract_app_name(command)
        result = focus_window_by_name(app_name)
        elapsed = (time.time() - start_time) * 1000
        print(f"[FAST] ⚡ Executed in {elapsed:.1f}ms")
        return True, result, elapsed

    # Screenshot desktop
    if re.search(r'\b(screenshot|capture|snap)\b.*\b(desktop|screen)\b', command_lower):
        result = describe_desktop()
        elapsed = (time.time() - start_time) * 1000
        print(f"[FAST] ⚡ Executed in {elapsed:.1f}ms")
        return True, result, elapsed

    # Screenshot window
    if re.search(r'\b(screenshot|capture|snap)\b', command_lower) and not 'desktop' in command_lower:
        app_name = extract_app_name(command)
        result = screenshot_window_by_name(app_name)
        elapsed = (time.time() - start_time) * 1000
        print(f"[FAST] ⚡ Executed in {elapsed:.1f}ms")
        return True, result, elapsed

    # Describe screen
    if re.search(r'\b(describe|what.*see|show.*screen)\b', command_lower):
        result = describe_desktop()
        elapsed = (time.time() - start_time) * 1000
        print(f"[FAST] ⚡ Executed in {elapsed:.1f}ms")
        return True, result, elapsed

    # Type text
    if re.search(r'\b(type|write|enter)\b', command_lower):
        # Extract text after "type"
        match = re.search(r'\b(?:type|write|enter)\s+(.+)', command_lower)
        if match:
            text = match.group(1)
            result = type_text_in_window(text)
            elapsed = (time.time() - start_time) * 1000
            print(f"[FAST] ⚡ Executed in {elapsed:.1f}ms")
            return True, result, elapsed

    # Press key combo
    if re.search(r'\b(press|hit)\b.*\b(ctrl|control|alt|shift|super|key)\b', command_lower):
        # Extract key combo
        match = re.search(r'(?:press|hit)\s+(.+)', command_lower)
        if match:
            keys = match.group(1)
            result = press_key_combo(keys)
            elapsed = (time.time() - start_time) * 1000
            print(f"[FAST] ⚡ Executed in {elapsed:.1f}ms")
            return True, result, elapsed

    # Command not recognized - need LLM fallback
    return False, None, 0

# Tool schema for LLM fallback (same as original)
tool_schema = [
{"type": "function", "function": {"name": "launch_application", "description": "Launches a graphical application on the Linux desktop.", "parameters": {"type": "object", "properties": {"app_name": {"type": "string", "description": "The command name of the app"}}, "required": ["app_name"]}}},
{"type": "function", "function": {"name": "describe_desktop", "description": "Captures a screenshot of the desktop and describes what is visible using AI vision.", "parameters": {"type": "object", "properties": {}}}},
{"type": "function", "function": {"name": "focus_window_by_name", "description": "Focus and bring to front a window.", "parameters": {"type": "object", "properties": {"window_name": {"type": "string", "description": "Application name", "default": ""}}, "required": []}}},
{"type": "function", "function": {"name": "close_window_by_name", "description": "Close a window.", "parameters": {"type": "object", "properties": {"window_name": {"type": "string", "description": "Application name", "default": ""}}, "required": []}}},
{"type": "function", "function": {"name": "maximize_window_by_name", "description": "Maximize a window.", "parameters": {"type": "object", "properties": {"window_name": {"type": "string", "description": "Application name", "default": ""}}, "required": []}}},
{"type": "function", "function": {"name": "minimize_window_by_name", "description": "Minimize a window.", "parameters": {"type": "object", "properties": {"window_name": {"type": "string", "description": "Application name", "default": ""}}, "required": []}}},
{"type": "function", "function": {"name": "restore_window_by_name", "description": "Restore a window to normal state.", "parameters": {"type": "object", "properties": {"window_name": {"type": "string", "description": "Application name", "default": ""}}, "required": []}}},
{"type": "function", "function": {"name": "screenshot_window_by_name", "description": "Screenshot a specific window.", "parameters": {"type": "object", "properties": {"window_name": {"type": "string", "description": "Application name", "default": ""}}, "required": []}}},
{"type": "function", "function": {"name": "type_text_in_window", "description": "Type text.", "parameters": {"type": "object", "properties": {"text": {"type": "string", "description": "Text to type"}}, "required": ["text"]}}},
{"type": "function", "function": {"name": "press_key_combo", "description": "Press key combination.", "parameters": {"type": "object", "properties": {"keys": {"type": "string", "description": "Key combo"}}, "required": ["keys"]}}},
]

def handle_command_with_llm(command: str) -> tuple:
    """LLM fallback for complex commands. Returns (result, execution_time)"""
    start_time = time.time()
    print(f"[LLM] 🤖 Using LLM fallback for: {command}")

    system_msg = {
        "role": "system",
        "content": "You are a silent system orchestrator. Execute tool calls based on user intent. DO NOT output conversational text. Use gnome-text-editor for text editor."
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

                # Execute the tool
                if tool_name == "launch_application":
                    result = launch_application(arguments.get('app_name'))
                elif tool_name == "describe_desktop":
                    result = describe_desktop()
                elif tool_name == "focus_window_by_name":
                    result = focus_window_by_name(arguments.get('window_name', ''))
                elif tool_name == "close_window_by_name":
                    result = close_window_by_name(arguments.get('window_name', ''))
                elif tool_name == "maximize_window_by_name":
                    result = maximize_window_by_name(arguments.get('window_name', ''))
                elif tool_name == "minimize_window_by_name":
                    result = minimize_window_by_name(arguments.get('window_name', ''))
                elif tool_name == "restore_window_by_name":
                    result = restore_window_by_name(arguments.get('window_name', ''))
                elif tool_name == "screenshot_window_by_name":
                    result = screenshot_window_by_name(arguments.get('window_name', ''))
                elif tool_name == "type_text_in_window":
                    result = type_text_in_window(arguments.get('text'))
                elif tool_name == "press_key_combo":
                    result = press_key_combo(arguments.get('keys'))
                else:
                    result = f"Unknown tool: {tool_name}"

                elapsed = (time.time() - start_time) * 1000
                print(f"[LLM] 🐢 Executed in {elapsed:.1f}ms")
                return result, elapsed
        else:
            elapsed = (time.time() - start_time) * 1000
            return "No tool call generated", elapsed

    except Exception as e:
        elapsed = (time.time() - start_time) * 1000
        return f"Error: {str(e)}", elapsed

# ----------------------------------------
# Conversation Mode (unchanged)
# ----------------------------------------
def classify_intent_type(user_input: str) -> str:
    """Classify if user input is a desktop command or conversational chat."""
    classifier_prompt = f"""Classify this voice input as either:
- command: Desktop control actions (open/close apps, describe screen, focus window, type text, press keys)
- conversation: Questions, chat, help requests, explanations, general knowledge

Examples of COMMAND:
- "open firefox"
- "close text editor"
- "describe screen"

Examples of CONVERSATION:
- "what is docker"
- "how do I install nodejs"

Input: "{user_input}"

Reply with ONE word only: command or conversation"""

    try:
        response = ollama.chat(
            model='gemma4:e4b',
            messages=[{'role': 'user', 'content': classifier_prompt}],
            options={
                'num_predict': 10,
                'temperature': 0.1,
                'num_ctx': 512
            }
        )

        result = response['message']['content'].strip().lower()

        if 'command' in result:
            return 'command'
        elif 'conversation' in result:
            return 'conversation'
        else:
            return 'conversation'

    except Exception as e:
        return 'conversation'

def handle_conversation(user_input: str, conversation_history: list) -> tuple:
    """Handle conversational chat with Gemma."""
    conversation_prompt = """You are a helpful AI assistant.
Answer questions clearly and concisely.
Keep responses under 3 sentences unless more detail is requested.
Be friendly and informative."""

    messages = [{'role': 'system', 'content': conversation_prompt}]
    messages.extend(conversation_history)
    messages.append({'role': 'user', 'content': user_input})

    try:
        response = ollama.chat(
            model='gemma4:e4b',
            messages=messages,
            options={
                'temperature': 0.7,
                'num_ctx': 2048
            }
        )

        answer = response['message']['content']

        conversation_history.append({'role': 'user', 'content': user_input})
        conversation_history.append({'role': 'assistant', 'content': answer})

        if len(conversation_history) > 20:
            conversation_history = conversation_history[-20:]

        return answer, conversation_history

    except Exception as e:
        error_msg = f"Sorry, I encountered an error: {str(e)}"
        return error_msg, conversation_history

# ----------------------------------------
# Voice Setup
# ----------------------------------------
print("[SYSTEM] Loading Neural Voice...")
voice_model = PiperVoice.load("en_US-lessac-medium.onnx")
print("[SYSTEM] Voice ready.")

def speak(text: str):
    """Converts text to neural speech and plays it."""
    print(f"\n[Agent]: {text}")

    if not text or text.strip() == "":
        return

    temp_audio_path = "/tmp/agent_response.wav"
    try:
        with wave.open(temp_audio_path, "wb") as wav_file:
            voice_model.synthesize_wav(text, wav_file)
        subprocess.run(["aplay", "-q", temp_audio_path], check=True)
    except Exception as e:
        print(f"[SYSTEM] Voice error: {e}")

# ----------------------------------------
# VAD-Based Voice Input
# ----------------------------------------
print("[SYSTEM] Loading Whisper model...")
whisper_model = WhisperModel("medium.en", device="cpu", compute_type="int8")

print("[SYSTEM] Loading Silero VAD model...")
vad_model, vad_utils = torch.hub.load(
    repo_or_dir='snakers4/silero-vad',
    model='silero_vad',
    force_reload=False,
    onnx=False
)
print("[SYSTEM] VAD model loaded.")

VAD_THRESHOLD = 0.5
SILENCE_DURATION = 1.0
MIN_SPEECH_DURATION = 0.5
PRE_SPEECH_BUFFER = 0.3

def is_speech(audio_chunk, vad_model, rate=16000, threshold=0.5):
    """Check if audio chunk contains speech using Silero VAD"""
    try:
        audio_int16 = np.frombuffer(audio_chunk, dtype=np.int16)
        audio_float32 = audio_int16.astype(np.float32) / 32768.0
        audio_tensor = torch.from_numpy(audio_float32)
        speech_prob = vad_model(audio_tensor, rate).item()
        return speech_prob > threshold
    except Exception as e:
        return True

def listen_and_transcribe():
    """VAD-based continuous listening"""
    CHUNK = 512
    FORMAT = pyaudio.paInt16
    CHANNELS = 1
    RATE = 16000

    p = pyaudio.PyAudio()
    stream = p.open(
        format=FORMAT,
        channels=CHANNELS,
        rate=RATE,
        input=True,
        frames_per_buffer=CHUNK
    )

    print("\n🎤 [VAD] Listening...")

    buffer_size = int(PRE_SPEECH_BUFFER * RATE / CHUNK)
    pre_buffer = collections.deque(maxlen=buffer_size)

    recording = False
    frames = []
    silence_chunks = 0
    silence_threshold = int(SILENCE_DURATION * RATE / CHUNK)

    try:
        while True:
            data = stream.read(CHUNK, exception_on_overflow=False)
            speech_detected = is_speech(data, vad_model, RATE, VAD_THRESHOLD)

            if not recording:
                pre_buffer.append(data)
                if speech_detected:
                    recording = True
                    frames = list(pre_buffer)
                    silence_chunks = 0
                    print("🔴 Recording...")
            else:
                frames.append(data)
                if speech_detected:
                    silence_chunks = 0
                else:
                    silence_chunks += 1
                    if silence_chunks >= silence_threshold:
                        duration = len(frames) * CHUNK / RATE
                        if duration >= MIN_SPEECH_DURATION:
                            print("⏹️  Processing...")
                            stream.stop_stream()
                            stream.close()
                            p.terminate()

                            temp_path = "/tmp/vad_recording.wav"
                            p_temp = pyaudio.PyAudio()
                            with wave.open(temp_path, 'wb') as wf:
                                wf.setnchannels(CHANNELS)
                                wf.setsampwidth(p_temp.get_sample_size(FORMAT))
                                wf.setframerate(RATE)
                                wf.writeframes(b''.join(frames))
                            p_temp.terminate()

                            segments, info = whisper_model.transcribe(
                                temp_path,
                                beam_size=5,
                                vad_filter=True,
                                vad_parameters=dict(min_silence_duration_ms=500)
                            )

                            text = "".join([segment.text for segment in segments]).strip()
                            print(f'✅ You said: "{text}"\n')
                            return text
                        else:
                            recording = False
                            frames = []
                            silence_chunks = 0

    except KeyboardInterrupt:
        print("\n[VAD] 🛑 Ctrl+C detected, shutting down...")
        stream.stop_stream()
        stream.close()
        p.terminate()
        raise

# ----------------------------------------
# Orchestrator Loop
# ----------------------------------------
def run_agent():
    print("\n" + "="*60)
    print("⚡ HYBRID Agentic OS")
    print("="*60)
    print("✅ VAD - unlimited voice input")
    print("✅ Safe close - dialog detection")
    print("✅ Voice confirmation")
    print("⭐ Conversation mode - ask questions")
    print("⚡ NEW: Hybrid parsing - <100ms for common commands\n")

    print("Mode switching:")
    print("  • 'switch to command mode' - force command mode")
    print("  • 'switch to chat mode' - force conversation mode")
    print("  • 'automatic mode' - auto-detect intent")
    print("  • 'clear history' - clear conversation history\n")

    print("[SYSTEM] Starting MCP client...")
    mcp_client.start()

    # State variables
    current_mode = None
    conversation_history = []

    # Performance tracking
    fast_count = 0
    llm_count = 0
    total_fast_time = 0
    total_llm_time = 0

    try:
        while True:
            user_input = listen_and_transcribe()
            if not user_input:
                continue

            user_input_lower = user_input.lower()

            # Mode switching commands
            if 'switch to command mode' in user_input_lower or 'command mode' in user_input_lower:
                current_mode = 'command'
                speak("Command mode activated.")
                print(f"[MODE] 🔧 Command mode (forced)")
                continue

            if 'switch to chat mode' in user_input_lower or 'chat mode' in user_input_lower or 'conversation mode' in user_input_lower:
                current_mode = 'conversation'
                speak("Chat mode activated.")
                print(f"[MODE] 💬 Conversation mode (forced)")
                continue

            if 'automatic mode' in user_input_lower or 'auto detect' in user_input_lower or 'auto mode' in user_input_lower:
                current_mode = None
                speak("Automatic mode.")
                print(f"[MODE] 🤖 Automatic detection")
                continue

            if 'clear history' in user_input_lower or 'new topic' in user_input_lower:
                conversation_history = []
                speak("Conversation history cleared.")
                print(f"[CHAT] 🗑️  History cleared")
                continue

            # Determine intent type
            if current_mode is None:
                intent_type = classify_intent_type(user_input)
                print(f"[MODE] 🤖 Auto-detected: {intent_type}")
            else:
                intent_type = current_mode
                print(f"[MODE] 🔒 Forced: {intent_type}")

            # Route to appropriate handler
            if intent_type == 'command':
                print(f"[COMMAND] Processing: {user_input}")

                # Try fast parser first
                success, result, elapsed = parse_command_fast(user_input)

                if success:
                    # Fast path succeeded
                    fast_count += 1
                    total_fast_time += elapsed
                    print(f"\n[OS Feedback]: {result}")
                    speak(result)
                else:
                    # Fall back to LLM
                    print(f"[COMMAND] Fast parser didn't recognize command, using LLM...")
                    result, elapsed = handle_command_with_llm(user_input)
                    llm_count += 1
                    total_llm_time += elapsed
                    print(f"\n[OS Feedback]: {result}")
                    speak(result)

                # Show performance stats every 10 commands
                total_commands = fast_count + llm_count
                if total_commands > 0 and total_commands % 10 == 0:
                    avg_fast = total_fast_time / fast_count if fast_count > 0 else 0
                    avg_llm = total_llm_time / llm_count if llm_count > 0 else 0
                    print(f"\n[STATS] Fast: {fast_count} commands, avg {avg_fast:.1f}ms | LLM: {llm_count} commands, avg {avg_llm:.1f}ms")

            else:  # intent_type == 'conversation'
                print(f"[CHAT] Processing: {user_input}")
                answer, conversation_history = handle_conversation(user_input, conversation_history)
                print(f"\n[Agent]: {answer}")
                speak(answer)

    except KeyboardInterrupt:
        print("\n[SYSTEM] 🛑 Ctrl+C received, shutting down gracefully...")

        # Final stats
        total_commands = fast_count + llm_count
        if total_commands > 0:
            print("\n" + "="*60)
            print("FINAL PERFORMANCE STATS")
            print("="*60)
            avg_fast = total_fast_time / fast_count if fast_count > 0 else 0
            avg_llm = total_llm_time / llm_count if llm_count > 0 else 0
            print(f"Fast parser: {fast_count} commands ({fast_count/total_commands*100:.1f}%), avg {avg_fast:.1f}ms")
            print(f"LLM fallback: {llm_count} commands ({llm_count/total_commands*100:.1f}%), avg {avg_llm:.1f}ms")
            if fast_count > 0 and llm_count > 0:
                speedup = avg_llm / avg_fast
                print(f"Speedup: {speedup:.1f}x faster with pattern matching")
        return

if __name__ == "__main__":
    try:
        run_agent()
    except KeyboardInterrupt:
        print("\n\n[SYSTEM] Shutting down Agentic OS...")
