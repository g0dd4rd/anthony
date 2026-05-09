#!/usr/bin/env python3
"""
Voice-Driven Desktop Orchestrator with CONSOLIDATED TOOLS (Facade Pattern)

This version uses the facade pattern to consolidate 34 individual tools into 10 tools:
- 6 facade tools (window_control, input_control, audio_control, system_settings, vision_control, workspace_control)
- 3 standalone tools (list_installed_applications, send_notification, cleanup_screenshots)
- 1 search tool (gnome_search)

Benefits:
- ⚡ 2-3× faster inference (~17-20s vs 41-69s with 34 tools)
- 🔧 All original functionality preserved through internal routing
- 📊 Clearer namespace organization for RAG
- 🚀 Scales to 100+ features without performance degradation

Features:
- ✅ VAD continuous listening
- ✅ Configurable AI models (granite, gemma4, etc.)
- ✅ Vision support for screen analysis
- ✅ Tool calling for desktop automation (CONSOLIDATED)
- ✅ SAFE close handling with dialog detection
- ✅ Conversation mode - chat with AI for questions/help
- ✅ Automatic intent detection - seamlessly switches between command & chat

Configuration:
To change models, edit the MODEL CONFIGURATION section below
"""

import os
import sys

# Force offline mode for sentence-transformers BEFORE import
# This prevents internet checks to HuggingFace Hub
os.environ['TRANSFORMERS_OFFLINE'] = '1'
os.environ['HF_HUB_OFFLINE'] = '1'

import requests
import ollama  # Fallback for vision tasks only
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
import webcolors
import argparse
from queue import Queue
from sentence_transformers import SentenceTransformer

from faster_whisper import WhisperModel
from piper.voice import PiperVoice
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from dialog_handler import DialogHandler

# Parse command-line arguments
parser = argparse.ArgumentParser(description='Voice-Driven Desktop Orchestrator')
parser.add_argument('--ptt', '--push-to-talk', action='store_true',
                    help='Enable push-to-talk mode (press ENTER to speak)')
parser.add_argument('--restart-server', action='store_true',
                    help='Force restart llama-server even if already running')
parser.add_argument('--kill-server', action='store_true',
                    help='Kill llama-server on exit (default: keep running)')
parser.add_argument('--debug', action='store_true',
                    help='Enable debug output (LLM prompts, tool calls, reasoning)')
args = parser.parse_args()

# Global flags
PUSH_TO_TALK_MODE = args.ptt
RESTART_SERVER = args.restart_server
KILL_SERVER_ON_EXIT = args.kill_server
DEBUG = args.debug

# ========================================
# 🎯 MODEL CONFIGURATION - LLAMA.CPP SERVER
# ========================================
# Using llama-server with Vulkan GPU acceleration (Intel Arc)
#
# Model: Gemma 4 E4B (8B parameters, Q4_K_M quantized, 5GB)
# Performance: ~2x faster than Ollama CPU-only mode
# API: OpenAI-compatible HTTP endpoint
# ========================================

# llama-server endpoint
LLAMA_SERVER_URL = 'http://127.0.0.1:8081/v1/chat/completions'
LLAMA_SERVER_HEALTH_URL = 'http://127.0.0.1:8081/health'

# Model name (for API requests - not used by llama-server but required for API format)
MODEL_NAME = 'gemma4-e4b-q4km'

# llama-server configuration
LLAMA_SERVER_CONFIG = {
    'binary': os.path.expanduser('~/llama.cpp/build/bin/llama-server'),
    'model': os.path.expanduser('~/models/gemma4-e4b-q4km.gguf'),
    'port': 8081,
    'host': '127.0.0.1',
    'ctx_size': 4096,
    'gpu_layers': 99,
    'device': 'Vulkan0',
    'threads': 6,
    'parallel': 1,
}

# Use Ollama fallback for vision tasks (llama-server doesn't support vision yet)
VISION_FALLBACK_OLLAMA = True
OLLAMA_VISION_MODEL = 'gemma4:e4b'

# ========================================
# End of configuration
# ========================================

# ----------------------------------------
# llama-server Lifecycle Management
# ----------------------------------------

# Global variable to track if we started the server
_server_process = None

def check_server_running():
    """Check if llama-server is responding"""
    try:
        response = requests.get(LLAMA_SERVER_HEALTH_URL, timeout=2)
        return response.status_code == 200 and response.json().get('status') == 'ok'
    except:
        return False

def kill_server():
    """Kill any running llama-server processes"""
    try:
        # Find and kill llama-server processes
        result = subprocess.run(['pgrep', '-f', 'llama-server.*gemma4-e4b-q4km'],
                              capture_output=True, text=True)
        if result.stdout.strip():
            pids = result.stdout.strip().split('\n')
            for pid in pids:
                try:
                    subprocess.run(['kill', pid], check=False)
                    print(f"[SERVER] Killed llama-server process (PID {pid})")
                except:
                    pass
            # Wait for processes to die
            time.sleep(2)
        return True
    except Exception as e:
        print(f"[SERVER] Warning: Could not kill server: {e}")
        return False

def start_server():
    """Start llama-server in detached background mode"""
    global _server_process

    config = LLAMA_SERVER_CONFIG

    # Build command
    cmd = [
        config['binary'],
        '--model', config['model'],
        '--ctx-size', str(config['ctx_size']),
        '--n-gpu-layers', str(config['gpu_layers']),
        '--device', config['device'],
        '--port', str(config['port']),
        '--host', config['host'],
        '--threads', str(config['threads']),
        '--parallel', str(config['parallel']),
        '--cont-batching',
        '--flash-attn', 'auto',
    ]

    print(f"[SERVER] Starting llama-server on port {config['port']}...")
    print(f"[SERVER] Model: {config['model']}")
    print(f"[SERVER] GPU: {config['device']} ({config['gpu_layers']} layers)")

    try:
        # Start in background, detached from parent process
        _server_process = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True  # Detach from parent
        )

        # Wait for server to be ready (max 30 seconds)
        print("[SERVER] Waiting for server to start", end='', flush=True)
        for i in range(30):
            time.sleep(1)
            print('.', end='', flush=True)
            if check_server_running():
                print(" ✓")
                print("[SERVER] llama-server started successfully!")
                return True

        print(" ✗")
        print("[SERVER] ⚠️  Server did not respond within 30 seconds")
        return False

    except Exception as e:
        print(f"\n[SERVER] ❌ Failed to start server: {e}")
        return False

def ensure_server_running(force_restart=False):
    """
    Ensure llama-server is running, start if needed

    Args:
        force_restart: If True, restart even if already running

    Returns:
        True if server is ready, False otherwise
    """
    # Check if already running
    if not force_restart and check_server_running():
        print("[SERVER] ✓ llama-server already running")
        return True

    # Force restart requested
    if force_restart:
        print("[SERVER] Restarting llama-server (--restart-server flag)...")
        kill_server()

    # Start server
    return start_server()

# ----------------------------------------
# llama-server Helper Functions
# ----------------------------------------
def call_llama_server(messages, tools=None, temperature=0.0, max_tokens=200):
    """
    Call llama-server with OpenAI-compatible API

    Args:
        messages: List of message dicts with 'role' and 'content'
        tools: Optional list of tool definitions
        temperature: Sampling temperature
        max_tokens: Maximum tokens to generate

    Returns:
        Response dict with 'message' containing 'content' and optional 'tool_calls'
    """
    payload = {
        'messages': messages,
        'temperature': temperature,
        'max_tokens': max_tokens,
        'model': MODEL_NAME  # Required by API format
    }

    if tools:
        payload['tools'] = tools

    try:
        response = requests.post(LLAMA_SERVER_URL, json=payload, timeout=120)
        response.raise_for_status()
        result = response.json()

        # Extract message in Ollama-compatible format
        choice = result['choices'][0]
        message = choice['message']

        # Convert to Ollama-style response format
        ollama_style = {
            'message': {
                'role': message['role'],
                'content': message.get('content', ''),
                'tool_calls': message.get('tool_calls', [])
            },
            'eval_count': result.get('usage', {}).get('completion_tokens', 0)
        }

        return ollama_style

    except requests.exceptions.RequestException as e:
        print(f"[ERROR] llama-server request failed: {e}")
        raise
    except Exception as e:
        print(f"[ERROR] llama-server error: {e}")
        raise


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

# Helper function for dialog handler to send keyboard input via MCP
def send_key_via_mcp(keys: str):
    """
    Send keyboard input via MCP client (for dialog handler callback).

    Args:
        keys: Key string like "Alt+s", "Tab", "Return", "Left", "Right"
    """
    # Check if it's a combo (contains +) or single key
    if '+' in keys:
        # Key combo (e.g., "Alt+s")
        mcp_client.call_tool("key_combo", {"keys": keys})
    else:
        # Single key (e.g., "Tab", "Return", "Left", "Right")
        mcp_client.call_tool("key_press", {"key": keys})

# Forward declarations for voice functions
def speak(text: str):
    pass

def listen_and_transcribe():
    pass

# ----------------------------------------
# Health Check & Auto-Recovery
# ----------------------------------------
def check_automation_health(auto_enable=True) -> tuple[bool, str]:
    """
    Check if GNOME automation extension is running and enabled.

    Args:
        auto_enable: If True, automatically enable automation if it's disabled

    Returns:
        (success: bool, message: str)
    """
    try:
        # Step 1: Ping the extension
        ping_result = mcp_client.call_tool("ping", {})
        if "Error" in ping_result or "alive" not in ping_result.lower():
            return False, "GNOME automation extension not responding. Please check if it's installed and enabled in GNOME Extensions."

        # Step 2: Check if automation is enabled
        enabled_result = mcp_client.call_tool("get_enabled", {})
        if "Error" in enabled_result:
            return False, f"Could not check automation status: {enabled_result}"

        is_enabled = "enabled" in enabled_result.lower() and "disabled" not in enabled_result.lower()

        if not is_enabled:
            if auto_enable:
                print("[SYSTEM] Automation is disabled. Auto-enabling...")
                enable_result = mcp_client.call_tool("set_enabled", {"enabled": True})
                if "Error" in enable_result:
                    return False, f"Failed to enable automation: {enable_result}"
                print("[SYSTEM] ✓ Automation enabled successfully")
                return True, "Automation was disabled but has been auto-enabled"
            else:
                return False, "Automation is disabled. Say 'enable automation' to turn it on."

        return True, "Automation is healthy and ready"

    except Exception as e:
        return False, f"Health check failed: {e}"

# ----------------------------------------
# Desktop Application Indexing
# ----------------------------------------
app_name_map = {}  # Global app name mapping: term → executable
app_friendly_name = {}  # Global executable → friendly name
app_names_only = set()  # Names + GenericNames only (no keywords), for routing

# Keyboard shortcuts that may trigger save dialogs (close app/window/tab)
# Check for dialogs only on these to avoid performance penalty on other shortcuts
DIALOG_CHECK_SHORTCUTS = {
    'Alt+F4',       # Universal window close (GNOME/GTK standard)
    'Ctrl+Q',       # Quit application (GNOME standard)
    'Ctrl+W',       # Close tab/document (browsers, editors, terminal tabs)
    'Ctrl+Shift+W', # Close window (Firefox, Chrome)
}

def build_app_index():
    """Build index of desktop applications from .desktop files.

    Maps natural language terms (Name, GenericName, Keywords) to executable names.
    org.gnome apps have priority and overwrite conflicts.
    """
    global app_name_map, app_friendly_name, app_names_only
    app_name_map = {}
    app_friendly_name = {}
    app_names_only = set()

    desktop_dir = "/usr/share/applications"

    if not os.path.isdir(desktop_dir):
        print(f"[SYSTEM] Warning: {desktop_dir} not found")
        return

    # Parse all desktop files and collect data
    apps = []

    for filename in os.listdir(desktop_dir):
        if not filename.endswith('.desktop'):
            continue

        filepath = os.path.join(desktop_dir, filename)
        is_gnome = filename.startswith('org.gnome.')

        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()

            # Parse desktop file
            exec_name = None
            name = None
            generic_name = None
            keywords = []

            # Only parse [Desktop Entry] section, stop at next section
            in_desktop_entry = False
            for line in content.split('\n'):
                line = line.strip()

                # Check for section headers
                if line.startswith('['):
                    if line == '[Desktop Entry]':
                        in_desktop_entry = True
                        continue
                    elif in_desktop_entry:
                        # Hit another section, stop parsing
                        break

                if not in_desktop_entry:
                    continue

                if line.startswith('Exec='):
                    # Extract executable (first word, remove path and % codes)
                    exec_line = line[5:].strip()
                    exec_name = exec_line.split()[0] if exec_line else None
                    if exec_name:
                        # Remove path prefix if present
                        exec_name = os.path.basename(exec_name)

                elif line.startswith('Name=') and not name:
                    # Only take first Name= encountered
                    name = line.split('=', 1)[1].strip()

                elif line.startswith('GenericName=') and not generic_name:
                    # Only take first GenericName= encountered
                    generic_name = line.split('=', 1)[1].strip()

                elif line.startswith('Keywords='):
                    keywords_str = line.split('=', 1)[1].strip()
                    keywords = [k.strip().rstrip(';') for k in keywords_str.split(';') if k.strip()]

            if exec_name:
                apps.append({
                    'exec': exec_name,
                    'name': name,
                    'generic_name': generic_name,
                    'keywords': keywords,
                    'is_gnome': is_gnome
                })
        except:
            # Skip files that can't be parsed
            continue

    # First pass: add all non-org.gnome apps
    for app in apps:
        if app['is_gnome']:
            continue

        exec_name = app['exec']

        # Store friendly name (prefer Name field)
        if app['name']:
            app_friendly_name[exec_name] = app['name']
        elif app['generic_name']:
            app_friendly_name[exec_name] = app['generic_name']
        else:
            app_friendly_name[exec_name] = exec_name

        # Add mappings (case-insensitive)
        app_name_map[exec_name.lower()] = exec_name
        app_names_only.add(exec_name.lower())

        if app['name']:
            app_name_map[app['name'].lower()] = exec_name
            app_names_only.add(app['name'].lower())

        if app['generic_name']:
            app_name_map[app['generic_name'].lower()] = exec_name
            app_names_only.add(app['generic_name'].lower())

        for keyword in app['keywords']:
            if keyword:
                app_name_map[keyword.lower()] = exec_name

    # Second pass: add org.gnome apps (overwrite conflicts with priority)
    gnome_count = 0
    for app in apps:
        if not app['is_gnome']:
            continue

        gnome_count += 1
        exec_name = app['exec']

        # Store friendly name (prefer Name field, overwrite previous)
        if app['name']:
            app_friendly_name[exec_name] = app['name']
        elif app['generic_name']:
            app_friendly_name[exec_name] = app['generic_name']
        else:
            app_friendly_name[exec_name] = exec_name

        # Add mappings (case-insensitive) - these overwrite non-gnome apps
        app_name_map[exec_name.lower()] = exec_name
        app_names_only.add(exec_name.lower())

        if app['name']:
            app_name_map[app['name'].lower()] = exec_name
            app_names_only.add(app['name'].lower())

        if app['generic_name']:
            app_name_map[app['generic_name'].lower()] = exec_name
            app_names_only.add(app['generic_name'].lower())

        for keyword in app['keywords']:
            if keyword:
                app_name_map[keyword.lower()] = exec_name

    print(f"[SYSTEM] ✓ Indexed {len(app_name_map)} app name mappings ({gnome_count} org.gnome with priority)")

def get_installed_gui_apps() -> list:
    """Get list of installed GUI applications."""
    apps = set()
    desktop_dir = "/usr/share/applications"

    if not os.path.isdir(desktop_dir):
        return []

    for filename in os.listdir(desktop_dir):
        if filename.endswith('.desktop'):
            filepath = os.path.join(desktop_dir, filename)
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    content = f.read()
                    for line in content.split('\n'):
                        if line.startswith('Name='):
                            app_name = line.split('=', 1)[1].strip()
                            apps.add(app_name)
                            break
            except:
                continue

    return sorted(list(apps))

def smart_match_window(window_name: str, windows: list) -> dict:
    """Smart window matching that prioritizes app names over full window titles."""
    if not window_name or window_name.strip() == "":
        for w in windows:
            if w.get('state', {}).get('focused', False):
                return w
        return windows[0] if windows else None

    window_name_lower = window_name.lower()

    # Try resolving via app_name_map (e.g., "settings" → "gnome-control-center")
    resolved_exec = app_name_map.get(window_name_lower)
    if resolved_exec:
        # Try matching resolved exec name first
        for w in windows:
            wm_class = w.get('wmClass', '').lower()
            if resolved_exec.lower() in wm_class or wm_class in resolved_exec.lower():
                return w

    # Try app name matching first
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

def get_friendly_app_name(wm_class: str) -> str:
    """Convert wmClass to friendly app name for voice output."""
    if not wm_class:
        return "Unknown App"

    name = wm_class
    name = name.replace('org.gnome.', '')
    name = name.replace('org.mozilla.', '')
    name = name.replace('org.', '')
    name = name.replace('-', ' ')
    name = name.replace('_', ' ')

    import re
    name = re.sub('([a-z])([A-Z])', r'\1 \2', name)
    name = ' '.join(word.capitalize() for word in name.split())

    return name

def parse_position(position: str, screen_width: int = 1920, screen_height: int = 1080) -> tuple:
    """Convert natural language position to screen coordinates."""
    position_lower = position.lower()
    center_x = screen_width // 2
    center_y = screen_height // 2
    left_x = 100
    right_x = screen_width - 100
    top_y = 100
    bottom_y = screen_height - 100

    if "top left" in position_lower:
        return (left_x, top_y)
    elif "top right" in position_lower:
        return (right_x, top_y)
    elif "top" in position_lower:
        return (center_x, top_y)
    elif "bottom left" in position_lower:
        return (left_x, bottom_y)
    elif "bottom right" in position_lower:
        return (right_x, bottom_y)
    elif "bottom" in position_lower:
        return (center_x, bottom_y)
    elif "left" in position_lower:
        return (left_x, center_y)
    elif "right" in position_lower:
        return (right_x, center_y)
    elif "center" in position_lower or "middle" in position_lower:
        return (center_x, center_y)
    else:
        return (center_x, center_y)

# ========================================
# 🔥 CONSOLIDATED FACADE TOOLS
# ========================================

def window_control(action: str, window_name: str = "", x: int = 0, y: int = 0,
                  width: int = 800, height: int = 600, include_frame: bool = True) -> str:
    """
    **FACADE TOOL**: Unified window management.

    Handles all window operations: list, focus, close, minimize, maximize, restore,
    screenshot (full or area), move, resize.

    Args:
        action: list | focus | close | minimize | maximize | restore | screenshot | screenshot_area | move_resize
        window_name: Application name (e.g., 'text editor'). Empty = current window.
        x, y: Position for move_resize or screenshot_area
        width, height: Size for move_resize or screenshot_area
        include_frame: Include window borders in screenshot
    """
    print(f"\n[WINDOW_CONTROL] Action: {action}, Window: {window_name or 'current'}")

    try:
        # LIST action
        if action == "list":
            result = mcp_client.call_tool("list_windows", {})
            if result.startswith("Error"):
                return result
            windows = json.loads(result)
            if not windows:
                return "No windows are currently open."
            window_titles = [w.get('title', 'Untitled') for w in windows[:10]]
            return f"Found {len(windows)} open windows: {', '.join(window_titles)}"

        # SCREENSHOT_AREA action (doesn't need window)
        if action == "screenshot_area":
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
            return f"Area screenshot ({width}x{height}) saved to {result.strip()}"

        # All other actions need a window
        result = mcp_client.call_tool("list_windows", {})
        if result.startswith("Error"):
            return result
        windows = json.loads(result)

        target_window = smart_match_window(window_name, windows)
        if not target_window:
            return f"No window found matching '{window_name}'"

        window_id = target_window['id']
        wm_class = target_window.get('wmClass', 'Unknown')
        friendly_name = get_friendly_app_name(wm_class)

        # FOCUS
        if action == "focus":
            mcp_client.call_tool("focus_window", {"window_id": window_id})
            return f"Focused {friendly_name}"

        # CLOSE (with dialog handling)
        elif action == "close":
            window_title = target_window.get('title', 'Unknown')
            mcp_client.call_tool("close_window", {"window_id": window_id})

            # Check for save dialog
            dialog = dialog_handler.detect_save_dialog(app_name=None, timeout=3.0)
            if not dialog:
                time.sleep(0.5)
                result = mcp_client.call_tool("list_windows", {})
                if not result.startswith("Error"):
                    windows_after = json.loads(result)
                    if not any(w['id'] == window_id for w in windows_after):
                        return f"Successfully closed {friendly_name}"

                # Try longer timeout
                dialog = dialog_handler.detect_save_dialog(app_name=None, timeout=5.0)
                if not dialog:
                    return f"Window did not close. No dialog detected."

            # Dialog detected - ask user
            buttons = dialog['info']['buttons']
            button_list = ', '.join([btn['text'] for btn in buttons]) if buttons else "Save, Discard, Cancel"
            voice_prompt = f"The window has unsaved changes. Options: {button_list}. What would you like to do?"

            speak(voice_prompt)
            user_choice = listen_and_transcribe()

            if not user_choice:
                speak("No response heard. Canceling close operation.")
                mcp_client.call_tool("key_combo", {"keys": "Escape"})
                return "Close operation canceled"

            success = dialog_handler.activate_button_by_keyboard(dialog, user_choice, key_callback=send_key_via_mcp)
            if not success:
                speak(f"Could not understand choice {user_choice}")
                mcp_client.call_tool("key_combo", {"keys": "Escape"})
                return f"Unrecognized choice: {user_choice}"

            closed = dialog_handler.verify_dialog_closed(dialog, timeout=2.0)
            if closed:
                time.sleep(0.5)
                result = mcp_client.call_tool("list_windows", {})
                if not result.startswith("Error"):
                    windows_final = json.loads(result)
                    window_still_open = any(w['id'] == window_id for w in windows_final)
                    if window_still_open:
                        return f"Dialog closed. {friendly_name} is still open"
                    else:
                        return f"Successfully closed {friendly_name}"
                return "Dialog handled successfully"
            else:
                return "Dialog might still be open"

        # MINIMIZE
        elif action == "minimize":
            mcp_client.call_tool("minimize_window", {"window_id": window_id})
            return f"Minimized {friendly_name}"

        # MAXIMIZE
        elif action == "maximize":
            state = target_window.get('state', {})
            is_maximized = state.get('maximized', False)

            if is_maximized:
                mcp_client.call_tool("unmaximize_window", {"window_id": window_id})
                return f"Restored {friendly_name}"
            else:
                mcp_client.call_tool("maximize_window", {"window_id": window_id})
                return f"Maximized {friendly_name}"

        # RESTORE
        elif action == "restore":
            state = target_window.get('state', {})
            is_maximized = state.get('maximized', False)

            mcp_client.call_tool("unminimize_window", {"window_id": window_id})
            mcp_client.call_tool("focus_window", {"window_id": window_id})

            if is_maximized:
                mcp_client.call_tool("unmaximize_window", {"window_id": window_id})

            return f"Restored {friendly_name}"

        # SCREENSHOT
        elif action == "screenshot":
            result = mcp_client.call_tool("screenshot_window", {
                "window_id": window_id,
                "include_frame": include_frame,
                "include_cursor": False,
                "format": "path"
            })
            if result.startswith("Error"):
                return result
            return f"Screenshot of {friendly_name} saved to {result.strip()}"

        # MOVE_RESIZE
        elif action == "move_resize":
            # Validate that dimensions are integers (gemma4 sometimes passes strings like "50%")
            try:
                x_int = int(x) if isinstance(x, (int, str)) else x
                y_int = int(y) if isinstance(y, (int, str)) else y
                width_int = int(width) if isinstance(width, (int, str)) else width
                height_int = int(height) if isinstance(height, (int, str)) else height
            except (ValueError, TypeError):
                return f"Error: move_resize requires integer dimensions, got x={x}, y={y}, width={width}, height={height}"

            # Get current window info to compare if size changed
            window_info = mcp_client.call_tool("list_windows", {})
            windows = json.loads(window_info)
            current_window = next((w for w in windows if w['id'] == window_id), None)

            old_width = current_window.get('width', 0) if current_window else 0
            old_height = current_window.get('height', 0) if current_window else 0
            old_x = current_window.get('x', 0) if current_window else 0
            old_y = current_window.get('y', 0) if current_window else 0

            mcp_client.call_tool("move_resize_window", {
                "window_id": window_id,
                "x": x_int,
                "y": y_int,
                "width": width_int,
                "height": height_int
            })

            # Smart feedback: infer user intent from what changed
            size_changed = abs(width_int - old_width) > 50 or abs(height_int - old_height) > 50
            position_changed = abs(x_int - old_x) > 50 or abs(y_int - old_y) > 50

            # Infer screen layout (common GNOME tiling positions)
            # Assuming 1920x1080 screen (adapt from actual values)
            position_description = None
            if x_int == 0 and width_int < 1000:  # Left half/side
                position_description = "left side"
            elif x_int > 900 and x_int < 1000 and width_int < 1000:  # Right half/side
                position_description = "right side"
            elif y_int == 0 and height_int < 600:  # Top
                position_description = "top"
            elif y_int > 400 and height_int < 700:  # Bottom
                position_description = "bottom"
            elif x_int == 0 and y_int == 0:  # Top-left corner
                position_description = "top-left corner"
            elif x_int > 900 and y_int == 0:  # Top-right corner
                position_description = "top-right corner"

            # Generate natural feedback
            # Priority: If we have a named position (left/right/top/bottom), just say that
            # The automatic resize from tiling is an implementation detail users don't care about
            if position_description and position_changed:
                return f"Moved {friendly_name} to the {position_description}"
            elif size_changed and not position_changed:
                # Only resize, no move
                return f"Resized {friendly_name} to {width_int}x{height_int}"
            elif position_changed and not size_changed:
                # Moved but no named position
                return f"Moved {friendly_name}"
            elif position_changed and size_changed:
                # Both changed, but no named position (custom move+resize)
                return f"Moved and resized {friendly_name} to {width_int}x{height_int}"
            else:
                # Nothing really changed?
                return f"Window {friendly_name} is already at the requested position and size"

        else:
            return f"Unknown window action: {action}"

    except Exception as e:
        return f"Error in window_control: {str(e)}"


def input_control(action: str, text: str = "", keys: str = "",
                 x: int = 0, y: int = 0, to_x: int = 0, to_y: int = 0,
                 direction: str = "down", amount: int = 1, button: int = 1,
                 from_position: str = "center", to_position: str = "center") -> str:
    """
    **FACADE TOOL**: Unified input control.

    Handles keyboard and mouse operations: type, key_combo, key_press, click,
    double_click, drag, scroll.

    Args:
        action: type | key_combo | key_press | click | double_click | drag | scroll
        text: Text to type (for 'type' action)
        keys: Key combo like 'Ctrl+c' (for 'key_combo' or 'key_press')
        x, y: Click position or drag start
        to_x, to_y: Drag end position
        from_position, to_position: Natural language positions for drag
        direction: Scroll direction 'up' or 'down'
        amount: Scroll amount (number of times)
        button: Mouse button (1=left, 2=middle, 3=right)
    """
    print(f"\n[INPUT_CONTROL] Action: {action}")

    try:
        # TYPE
        if action == "type":
            mcp_client.call_tool("type_text", {"text": text})
            return f"Typed: {text}"

        # KEY_COMBO
        elif action == "key_combo":
            # Normalize key combo
            normalized = keys
            normalized = normalized.replace("control", "Ctrl").replace("Control", "Ctrl").replace("ctrl", "Ctrl")
            normalized = normalized.replace("alt", "Alt").replace("shift", "Shift").replace("super", "Super")
            if " " in normalized and "+" not in normalized:
                normalized = normalized.replace(" ", "+")

            mcp_client.call_tool("key_combo", {"keys": normalized})

            # Check for save dialog if this is a known close shortcut
            if normalized in DIALOG_CHECK_SHORTCUTS:
                time.sleep(0.5)  # Give window time to show dialog
                dialog = dialog_handler.detect_save_dialog(app_name=None, timeout=3.0)

                if dialog:
                    # Dialog detected - ask user what to do
                    buttons = dialog['info']['buttons']
                    button_list = ', '.join([btn['text'] for btn in buttons]) if buttons else "Save, Discard, Cancel"
                    voice_prompt = f"The window has unsaved changes. Options: {button_list}. What would you like to do?"

                    speak(voice_prompt)
                    user_choice = listen_and_transcribe()

                    if not user_choice:
                        speak("No response heard. Canceling close operation.")
                        mcp_client.call_tool("key_combo", {"keys": "Escape"})
                        return f"Pressed {normalized} but close operation was canceled (no response to dialog)"

                    success = dialog_handler.activate_button_by_keyboard(dialog, user_choice, key_callback=send_key_via_mcp)
                    if not success:
                        speak(f"Could not understand choice {user_choice}")
                        mcp_client.call_tool("key_combo", {"keys": "Escape"})
                        return f"Pressed {normalized} but unrecognized dialog choice: {user_choice}"

                    closed = dialog_handler.verify_dialog_closed(dialog, timeout=2.0)
                    if closed:
                        return f"Pressed {normalized} and handled save dialog: {user_choice}"
                    else:
                        return f"Pressed {normalized} - dialog might still be open"

            return f"Pressed {normalized}"

        # KEY_PRESS
        elif action == "key_press":
            mcp_client.call_tool("key_press", {"key": keys})
            return f"Pressed {keys}"

        # CLICK
        elif action == "click":
            mcp_client.call_tool("mouse_click", {"x": x, "y": y, "button": button})
            return f"Clicked at ({x}, {y})"

        # DOUBLE_CLICK
        elif action == "double_click":
            mcp_client.call_tool("mouse_double_click", {"x": x, "y": y, "button": button})
            return f"Double-clicked at ({x}, {y})"

        # DRAG
        elif action == "drag":
            # Use positions if coordinates not provided
            if to_x == 0 and to_y == 0:
                from_coords = parse_position(from_position)
                to_coords = parse_position(to_position)
                x, y = from_coords
                to_x, to_y = to_coords

            mcp_client.call_tool("mouse_drag", {
                "x1": x,
                "y1": y,
                "x2": to_x,
                "y2": to_y,
                "button": button
            })
            return f"Dragged from ({x}, {y}) to ({to_x}, {to_y})"

        # SCROLL
        elif action == "scroll":
            is_down = "down" in direction.lower()

            # Try mouse scroll first
            dy = 100 * amount if is_down else -100 * amount
            result = mcp_client.call_tool("mouse_scroll", {
                "x": 960, "y": 540, "dx": 0, "dy": dy
            })

            if not result.startswith("Error"):
                return f"Scrolled {direction}"

            # Fall back to Page keys
            key = "Page_Down" if is_down else "Page_Up"
            for i in range(amount):
                mcp_client.call_tool("key_combo", {"keys": key})
                if i < amount - 1:
                    time.sleep(0.1)

            return f"Scrolled {direction}"

        else:
            return f"Unknown input action: {action}"

    except Exception as e:
        return f"Error in input_control: {str(e)}"


def audio_control(action: str, level: int = 0, relative: bool = False) -> str:
    """
    **FACADE TOOL**: Unified audio control.

    Handles volume and media playback: volume, mute, unmute, play, pause,
    play_pause, next, previous, stop.

    Args:
        action: volume | mute | unmute | play | pause | play_pause | next | previous | stop
        level: Volume level (0-100 absolute, or +/- for relative)
        relative: True for relative volume change
    """
    print(f"\n[AUDIO_CONTROL] Action: {action}")

    try:
        # VOLUME
        if action == "volume":
            result = mcp_client.call_tool("set_volume", {
                "volume": level,
                "relative": relative
            })
            return result

        # MUTE
        elif action == "mute":
            result = mcp_client.call_tool("mute_volume", {"mute": True})
            return result

        # UNMUTE
        elif action == "unmute":
            result = mcp_client.call_tool("mute_volume", {"mute": False})
            return result

        # MEDIA CONTROLS
        elif action in ["play", "pause", "play_pause", "next", "previous", "stop"]:
            # Map underscores to dashes for MCP
            mcp_action = action.replace("_", "-")
            result = mcp_client.call_tool("media_control", {"action": mcp_action})
            return result

        else:
            return f"Unknown audio action: {action}"

    except Exception as e:
        return f"Error in audio_control: {str(e)}"


def system_settings(action: str, state: str = "toggle", path: str = "") -> str:
    """
    **FACADE TOOL**: Unified system settings.

    Handles quick settings toggles: dark_mode, night_light, do_not_disturb,
    wifi, bluetooth, wallpaper.

    Args:
        action: dark_mode | night_light | do_not_disturb | wifi | bluetooth | wallpaper
        state: 'on' | 'off' | 'toggle' (for toggles), or color/path (for wallpaper)
        path: Image path (for wallpaper action)
    """
    print(f"\n[SYSTEM_SETTINGS] Action: {action}, State: {state}")

    try:
        # WALLPAPER
        if action == "wallpaper":
            result = mcp_client.call_tool("set_wallpaper", {"image_path": path or state})
            return result

        # TOGGLES
        else:
            # Map action to setting name
            setting_map = {
                "dark_mode": "dark_style",
                "night_light": "night_light",
                "do_not_disturb": "do_not_disturb",
                "wifi": "wifi",
                "bluetooth": "bluetooth"
            }

            setting_name = setting_map.get(action)
            if not setting_name:
                return f"Unknown setting: {action}"

            # Convert state to boolean
            if state.lower() in ["on", "true", "enable", "enabled"]:
                enabled = True
            elif state.lower() in ["off", "false", "disable", "disabled"]:
                enabled = False
            else:
                # For 'toggle', would need to query current state
                # For simplicity, treat as error
                return "Please specify 'on' or 'off' for this setting"

            result = mcp_client.call_tool("quick_settings", {
                "setting": setting_name,
                "enabled": enabled
            })
            return result

    except Exception as e:
        return f"Error in system_settings: {str(e)}"


def vision_control(action: str, x: int = 0, y: int = 0, path: str = "") -> str:
    """
    **FACADE TOOL**: Unified vision operations.

    Handles screen analysis and display info: screenshot, describe, describe_file, pick_color, get_monitors.

    Args:
        action: screenshot | describe | describe_file | pick_color | get_monitors
        x, y: Coordinates for pick_color
        path: File path for describe_file
    """
    print(f"\n[VISION_CONTROL] Action: {action}")

    try:
        # SCREENSHOT (full desktop)
        if action == "screenshot":
            result = mcp_client.call_tool("screenshot", {"include_cursor": False, "format": "path"})
            if result.startswith("Error"):
                return result
            return f"Full desktop screenshot saved to {result.strip()}"

        # DESCRIBE
        elif action == "describe":
            result = mcp_client.call_tool("screenshot", {"include_cursor": False, "format": "path"})
            if result.startswith("Error"):
                return result

            screenshot_path = result.strip()

            with open(screenshot_path, 'rb') as img_file:
                import base64
                img_data = base64.b64encode(img_file.read()).decode('utf-8')

            # Use Ollama fallback for vision (llama-server doesn't support images yet)
            response = ollama.chat(
                model=OLLAMA_VISION_MODEL,
                messages=[
                    {
                        'role': 'system',
                        'content': 'You are a screen reader for visually impaired users. Describe what you see in plain text without any formatting. Do not use markdown, asterisks, or special characters. Answer directly without explaining your reasoning process.'
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

            message = response.message if hasattr(response, 'message') else response['message']
            description = message.content if hasattr(message, 'content') else message.get('content', '')

            try:
                os.remove(screenshot_path)
            except:
                pass

            return description

        # DESCRIBE_FILE
        elif action == "describe_file":
            file_path = os.path.expanduser(path)
            if not os.path.isfile(file_path):
                print(f"[VISION_CONTROL] Exact path not found, searching via localsearch...")
                try:
                    search_result = mcp_client.call_tool("search_files", {"query": os.path.basename(path), "file_type": "files", "limit": 5})
                    results = json.loads(search_result)
                    if results.get("count", 0) > 0:
                        file_path = results["results"][0]
                        print(f"[VISION_CONTROL] Resolved to: {file_path}")
                    else:
                        return f"File not found: {path}"
                except Exception:
                    return f"File not found: {path}"

            with open(file_path, 'rb') as img_file:
                import base64
                img_data = base64.b64encode(img_file.read()).decode('utf-8')

            response = ollama.chat(
                model=OLLAMA_VISION_MODEL,
                messages=[
                    {
                        'role': 'system',
                        'content': 'Describe the image in plain text without any formatting. Do not use markdown, asterisks, or special characters. Answer directly without explaining your reasoning process.'
                    },
                    {
                        'role': 'user',
                        'content': f'Describe this image: {os.path.basename(file_path)}',
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

            message = response.message if hasattr(response, 'message') else response['message']
            description = message.content if hasattr(message, 'content') else message.get('content', '')
            return description

        # PICK_COLOR
        elif action == "pick_color":
            if DEBUG:
                print(f"[DEBUG] vision_control received coordinates: x={x}, y={y}, types: x={type(x)}, y={type(y)}")
            result = mcp_client.call_tool("pick_color", {"x": x, "y": y})
            if DEBUG:
                print(f"[DEBUG] pick_color result: {result}")

            # Parse RGB values and convert to color name
            try:
                rgb_data = json.loads(result)
                r, g, b = int(rgb_data['r']), int(rgb_data['g']), int(rgb_data['b'])

                # Try exact match first
                try:
                    color_name = webcolors.rgb_to_name((r, g, b), spec='css3')
                except ValueError:
                    # Find closest named color
                    min_distance = float('inf')
                    closest_name = None
                    for name in webcolors.names('css3'):
                        named_rgb = webcolors.name_to_rgb(name)
                        distance = sum((a - b) ** 2 for a, b in zip((r, g, b), named_rgb)) ** 0.5
                        if distance < min_distance:
                            min_distance = distance
                            closest_name = name
                    color_name = closest_name

                return f"{color_name} (RGB: {r}, {g}, {b})"
            except Exception as e:
                # Fallback to raw result if parsing fails
                if DEBUG:
                    print(f"[DEBUG] Color name conversion failed: {e}")
                return result

        # GET_MONITORS
        elif action == "get_monitors":
            result = mcp_client.call_tool("get_monitors", {})

            # Format friendly output for users
            try:
                monitors = json.loads(result)
                if len(monitors) == 0:
                    return "No monitors detected"
                elif len(monitors) == 1:
                    m = monitors[0]
                    primary_tag = " (primary)" if m.get('primary') else ""
                    return f"1 {primary_tag} monitor, resolution {m['width']}x{m['height']} at scale {m.get('scale', 1)}"
                else:
                    # Multiple monitors
                    lines = [f"{len(monitors)} monitors connected:"]
                    for i, m in enumerate(monitors):
                        primary_tag = " (primary)" if m.get('primary') else ""
                        lines.append(f"Monitor {i+1}{primary_tag}, resolution {m['width']}x{m['height']} at position ({m['x']}, {m['y']})")
                    return " ".join(lines)
            except Exception as e:
                # Fallback to raw JSON if parsing fails
                if DEBUG:
                    print(f"[DEBUG] Monitor formatting failed: {e}")
                return result

        else:
            return f"Unknown vision action: {action}"

    except Exception as e:
        return f"Error in vision_control: {str(e)}"


def workspace_control(action: str, index: int = 0) -> str:
    """
    **FACADE TOOL**: Unified workspace management.

    Handles virtual desktop operations: list, activate.

    Args:
        action: list | activate
        index: Workspace index (0-based) for activate
    """
    print(f"\n[WORKSPACE_CONTROL] Action: {action}")

    try:
        # LIST
        if action == "list":
            result = mcp_client.call_tool("list_workspaces", {})
            if result.startswith("Error"):
                return result

            try:
                workspaces = json.loads(result)
                if not workspaces:
                    return "No workspaces found"

                # Find active workspace
                active_workspace = None
                for ws in workspaces:
                    if ws.get('active', False):
                        active_workspace = ws.get('index', 0)
                        break

                total = len(workspaces)
                return f"You have {total} workspace{'s' if total > 1 else ''}. Workspace {active_workspace} is the current workspace."

            except json.JSONDecodeError:
                return result

        # ACTIVATE
        elif action == "activate":
            result = mcp_client.call_tool("activate_workspace", {"index": index})
            if result.startswith("Error"):
                return result
            return f"Switched to workspace {index}"

        else:
            return f"Unknown workspace action: {action}"

    except Exception as e:
        return f"Error in workspace_control: {str(e)}"


# ========================================
# STANDALONE TOOLS (low frequency)
# ========================================

def list_installed_applications() -> str:
    """Lists all installed GUI applications on the system."""
    print(f"\n[SYSTEM] Scanning for installed applications...")
    try:
        app_data = get_installed_gui_apps()
        app_count = app_data['count']
        samples = app_data['samples']

        if app_count == 0:
            return "No applications found."

        if samples:
            return f"Found {app_count} installed applications including {', '.join(samples)}, and more."
        else:
            return f"Found {app_count} installed applications."
    except Exception as e:
        return f"Error listing applications: {str(e)}"

def send_notification(summary: str, body: str = "", delay: str = "") -> str:
    """Send a desktop notification."""
    print(f"\n[SYSTEM] Sending notification: {summary}")
    try:
        result = mcp_client.call_tool("send_notification", {
            "summary": summary,
            "body": body,
            "delay": delay
        })
        return result
    except Exception as e:
        return f"Error sending notification: {str(e)}"

def cleanup_screenshots() -> str:
    """Clean up temporary screenshot files by moving them to trash."""
    print(f"\n[SYSTEM] Cleaning up screenshots...")
    try:
        result = mcp_client.call_tool("cleanup_screenshots", {})
        # Update feedback to clarify files are moved to trash, not deleted permanently
        if result.startswith("Removed"):
            # Parse count from "Removed X screenshot files"
            import re
            match = re.search(r'Removed (\d+)', result)
            if match:
                count = match.group(1)
                return f"Moved {count} screenshots from Pictures/Screenshots to trash"
            else:
                return "Moved screenshots from Pictures/Screenshots to trash"
        return result
    except Exception as e:
        return f"Error cleaning up: {str(e)}"


def get_app_shortcuts(app_name: str) -> str:
    """Look up keyboard shortcuts for an application."""
    from shortcuts.gnome_shortcuts import get_shortcuts_for_app
    import json as _json

    app_lower = app_name.lower().strip()
    shortcuts = {}

    # Check curated JSON first
    shortcuts_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "shortcuts")
    json_path = os.path.join(shortcuts_dir, "app_shortcuts.json")
    try:
        with open(json_path) as f:
            curated = _json.load(f)
        # Fuzzy match: "text editor" → "text-editor", "files" → "nautilus"
        alias_map = {
            "text editor": "text-editor",
            "gnome text editor": "text-editor",
            "gnome-text-editor": "text-editor",
            "files": "nautilus",
            "file manager": "nautilus",
            "image viewer": "loupe",
            "document viewer": "papers",
            "pdf viewer": "papers",
            "terminal": "ptyxis",
        }
        lookup_key = alias_map.get(app_lower, app_lower)
        if lookup_key in curated:
            shortcuts.update(curated[lookup_key])
    except Exception:
        pass

    # Check gsettings schemas
    gs_shortcuts = get_shortcuts_for_app(app_name)
    if gs_shortcuts:
        shortcuts.update(gs_shortcuts)

    # Filter out metadata fields
    shortcuts = {k: v for k, v in shortcuts.items() if not k.startswith("_")}

    if not shortcuts:
        return f"No shortcuts found for '{app_name}'"

    lines = [f"Shortcuts for {app_name}:"]
    for action, shortcut in shortcuts.items():
        lines.append(f"- {action}: {shortcut}")
    return "\n".join(lines)


# ========================================
# TOOL REGISTRY
# ========================================

# Available tools (facade + standalone + direct MCP)
available_tools = {
    # Facade tools
    "window_control": window_control,
    "input_control": input_control,
    "audio_control": audio_control,
    "system_settings": system_settings,
    "vision_control": vision_control,
    "workspace_control": workspace_control,

    # Standalone tools
    "list_installed_applications": list_installed_applications,
    "send_notification": send_notification,
    "cleanup_screenshots": cleanup_screenshots,
    "get_app_shortcuts": get_app_shortcuts,
}

# Direct MCP tools (forwarded without wrappers)
direct_mcp_tools = [
    "gnome_search",      # GNOME search overlay
    "search_files",      # File search via localsearch (returns paths)
    "ping",              # Health check
    "get_enabled",       # Check automation status
    "set_enabled",       # Enable/disable automation
]

# ========================================
# NAMESPACE ORGANIZATION + RAG
# ========================================

namespaces = {
    "search": {
        "description": "Opening and launching: applications (firefox, text editor, calculator, terminal), files and documents (image.png, document.pdf, report.txt, presentation.pptx), websites (amazon.com, github.com), system settings (wifi, bluetooth). Use for any 'open', 'launch', 'start', 'find' command. Examples: open firefox, open report.pdf, open image.png, launch calculator, go to amazon.com, find settings.",
        "tools": ["gnome_search"]
    },
    "window": {
        "description": "Managing already running application windows: close, minimize, maximize, restore, focus, move, resize windows. List currently running windows. Capture window images or screen regions. NOT for launching/opening new apps or files.",
        "tools": ["window_control"]
    },
    "input": {
        "description": "Keyboard input, typing text, pressing keys, key combinations, shortcuts, mouse clicks, double clicks, dragging, scrolling pages up and down. Look up app-specific keyboard shortcuts before performing in-app actions.",
        "tools": ["input_control", "get_app_shortcuts"]
    },
    "audio": {
        "description": "Sound volume control, mute, unmute, audio levels. Media playback control - play, pause, stop, next track, previous track, music control, audio player control",
        "tools": ["audio_control"]
    },
    "settings": {
        "description": "System settings - dark mode, light mode, night light, notifications, do not disturb, WiFi, Bluetooth, wallpaper, background image, quick settings toggles",
        "tools": ["system_settings"]
    },
    "vision": {
        "description": "Screen analysis and display tools: capture full desktop image, describe current screen content with AI, describe or analyze an image file by path (e.g., describe screenshot.png, what's in this picture), pick pixel colors at coordinates, get monitor information (resolution, scaling, position)",
        "tools": ["vision_control", "search_files"]
    },
    "workspace": {
        "description": "Virtual desktops, workspace switching (switch to workspace 1, go to workspace 2, activate workspace), multi-desktop management, listing workspaces",
        "tools": ["workspace_control"]
    },
    "system": {
        "description": "System tasks: list installed applications (show apps, what apps are installed), send desktop notifications (notify me, remind me, alert me in X minutes), clean up screenshots (delete screenshots, remove screenshots, cleanup temp files), enable or disable automation",
        "tools": ["list_installed_applications", "send_notification", "cleanup_screenshots", "set_enabled"]
    }
}

# Load embedding model
print("[SYSTEM] Loading embedding model for tool retrieval...")
embedding_model = SentenceTransformer('all-MiniLM-L6-v2', device='cpu')

# Pre-compute namespace embeddings
namespace_names = list(namespaces.keys())
namespace_descriptions = [namespaces[ns]["description"] for ns in namespace_names]
namespace_embeddings = embedding_model.encode(namespace_descriptions, convert_to_tensor=True)
print(f"[SYSTEM] ✓ Loaded embeddings for {len(namespace_names)} namespaces")

# Ensure llama-server is running
if not ensure_server_running(force_restart=RESTART_SERVER):
    print("[SERVER] ❌ Failed to start llama-server. Exiting.")
    sys.exit(1)

def retrieve_relevant_namespaces(user_input: str, top_k: int = 2) -> tuple:
    """Retrieve most relevant namespaces using semantic similarity + verb routing.
    Returns (namespaces_list, detected_app_name_or_None)."""
    from sentence_transformers.util import cos_sim

    user_input_lower = user_input.lower()

    # Verb-based routing: force include specific namespaces for certain verbs
    forced_namespaces = []

    # Window management verbs → force window namespace
    # Note: Removed 'screenshot' - it's ambiguous (could be window screenshot, desktop screenshot, or filename)
    window_verbs = ['close', 'quit', 'exit', 'kill', 'minimize', 'maximize', 'restore',
                    'focus', 'switch to', 'move', 'resize']
    if any(verb in user_input_lower for verb in window_verbs):
        if 'window' not in forced_namespaces:
            forced_namespaces.append('window')

    # App name detected → force input namespace (for get_app_shortcuts + input_control)
    # Uses app_names_only (Name + GenericName fields, no keywords) to avoid false positives
    import string
    words = [w.strip(string.punctuation) for w in user_input_lower.split()]
    words = [w for w in words if w]
    detected_app = None
    for n in range(len(words), 0, -1):
        for i in range(len(words) - n + 1):
            phrase = ' '.join(words[i:i+n])
            if phrase in app_names_only:
                detected_app = phrase
                if 'input' not in forced_namespaces:
                    forced_namespaces.append('input')
                    print(f"[ROUTING] Detected app '{phrase}' → forcing input namespace")
                break
        else:
            continue
        break

    # If we forced namespaces, reduce top_k to make room
    adjusted_top_k = max(1, top_k - len(forced_namespaces))

    # Get semantic matches
    query_embedding = embedding_model.encode(user_input, convert_to_tensor=True)
    similarities = cos_sim(query_embedding, namespace_embeddings)[0]
    top_indices = similarities.argsort(descending=True)[:adjusted_top_k]
    semantic_namespaces = [namespace_names[i] for i in top_indices]

    # Combine forced + semantic (remove duplicates, preserve order)
    relevant_namespaces = forced_namespaces.copy()
    for ns in semantic_namespaces:
        if ns not in relevant_namespaces:
            relevant_namespaces.append(ns)

    # Ensure we return exactly top_k namespaces
    relevant_namespaces = relevant_namespaces[:top_k]

    print(f"[RETRIEVAL] Query: '{user_input}'")
    if forced_namespaces:
        print(f"[ROUTING] Forced namespaces: {forced_namespaces}")
    for i, ns in enumerate(relevant_namespaces):
        score = similarities[namespace_names.index(ns)].item()
        forced_marker = " [FORCED]" if ns in forced_namespaces else ""
        print(f"  {i+1}. {ns} (score: {score:.3f}) - {len(namespaces[ns]['tools'])} tools{forced_marker}")

    return relevant_namespaces, detected_app

def build_filtered_tool_schema(relevant_namespaces: list) -> list:
    """Build filtered tool schema from relevant namespaces."""
    relevant_tool_names = set()
    for ns in relevant_namespaces:
        relevant_tool_names.update(namespaces[ns]["tools"])

    filtered_schema = [tool for tool in tool_schema_full
                      if tool["function"]["name"] in relevant_tool_names]

    print(f"[FILTER] Showing {len(filtered_schema)} tools from {len(relevant_namespaces)} namespaces")
    print(f"  Tools: {[t['function']['name'] for t in filtered_schema]}")

    return filtered_schema

# ========================================
# CONSOLIDATED TOOL SCHEMA (10 tools total)
# ========================================

tool_schema_full = [
    # 1. SEARCH (direct MCP)
    {"type": "function", "function": {"name": "gnome_search", "description": "Find and open apps, files, settings, or websites. For WEBSITES (domains/URLs): append ' website' to query (e.g., 'amazon.com website', 'github.com website'). For FILES (documents, images, etc.): append ' file' to query (e.g., 'Screenshot-1.png file', 'document.pdf file'). For APPS and SETTINGS: use query as-is (e.g., 'firefox', 'text editor', 'wifi settings'). The markers (' website' or ' file') tell the system how to handle the query.", "parameters": {"type": "object", "properties": {"query": {"type": "string", "description": "App name, file name+' file', setting, or domain+' website'. Examples: 'firefox', 'text editor', 'Screenshot-1.png file', 'document.pdf file', 'amazon.com website', 'github.com website', 'wifi'"}}, "required": ["query"]}}},

    # 2. SEARCH_FILES (direct MCP)
    {"type": "function", "function": {"name": "search_files", "description": "Search for files by name using GNOME file indexing. Returns a JSON list of full absolute file paths matching the query. Use this to find a file's exact path before acting on it (e.g., before describing an image). Does NOT open files.", "parameters": {"type": "object", "properties": {"query": {"type": "string", "description": "Filename or keywords to search for. Example: 'screenshot.png', 'report'"}}, "required": ["query"]}}},

    # 3. WINDOW_CONTROL (facade)
    {"type": "function", "function": {"name": "window_control", "description": "Unified window management: list windows, focus/close/minimize/maximize/restore windows, take window screenshots or area screenshots, move and resize windows. Matches windows by application name (e.g., 'text editor', 'firefox', 'nautilus'). Empty window_name = current window. For move_resize: left half of 1920x1080 screen = x:0, y:0, width:960, height:1080. Right half = x:960, y:0, width:960, height:1080.", "parameters": {"type": "object", "properties": {"action": {"type": "string", "description": "Action to perform: list | focus | close | minimize | maximize | restore | screenshot | screenshot_area | move_resize"}, "window_name": {"type": "string", "description": "Application name (e.g., 'text editor'). Leave empty for current window.", "default": ""}, "x": {"type": "integer", "description": "X position in pixels for move_resize or screenshot_area. Must be integer, NOT percentage.", "default": 0}, "y": {"type": "integer", "description": "Y position in pixels for move_resize or screenshot_area. Must be integer, NOT percentage.", "default": 0}, "width": {"type": "integer", "description": "Width in pixels for move_resize or screenshot_area. Must be integer, NOT percentage. For left/right half: use 960 pixels on 1920 wide screen.", "default": 800}, "height": {"type": "integer", "description": "Height in pixels for move_resize or screenshot_area. Must be integer, NOT percentage. For full height: use 1080 pixels on 1080 tall screen.", "default": 600}, "include_frame": {"type": "boolean", "description": "Include window borders in screenshot", "default": True}}, "required": ["action"]}}},

    # 3. INPUT_CONTROL (facade)
    {"type": "function", "function": {"name": "input_control", "description": "Unified input control: type text, press key combos, press single keys, mouse click/double-click, drag and drop, scroll. Use get_app_shortcuts to look up the correct shortcut before pressing keys.", "parameters": {"type": "object", "properties": {"action": {"type": "string", "description": "Action: type | key_combo | key_press | click | double_click | drag | scroll"}, "text": {"type": "string", "description": "Text to type (for 'type' action)", "default": ""}, "keys": {"type": "string", "description": "Key combo like 'Ctrl+c' or single key like 'Enter'", "default": ""}, "x": {"type": "integer", "description": "X coordinate for click or drag start", "default": 0}, "y": {"type": "integer", "description": "Y coordinate for click or drag start", "default": 0}, "to_x": {"type": "integer", "description": "Drag end X coordinate", "default": 0}, "to_y": {"type": "integer", "description": "Drag end Y coordinate", "default": 0}, "from_position": {"type": "string", "description": "Natural language start position for drag: 'left', 'right', 'center', 'top left', etc.", "default": "center"}, "to_position": {"type": "string", "description": "Natural language end position for drag: 'left', 'right', 'center', 'bottom right', etc.", "default": "center"}, "direction": {"type": "string", "description": "Scroll direction: 'up' or 'down'", "default": "down"}, "amount": {"type": "integer", "description": "Scroll amount (number of times)", "default": 1}, "button": {"type": "integer", "description": "Mouse button: 1=left, 2=middle, 3=right", "default": 1}}, "required": ["action"]}}},

    # 4. GET_APP_SHORTCUTS (standalone)
    {"type": "function", "function": {"name": "get_app_shortcuts", "description": "Look up keyboard shortcuts for a specific application. Call this before using input_control key_combo/key_press to find the correct shortcut for an action. Returns a list of available shortcuts.", "parameters": {"type": "object", "properties": {"app_name": {"type": "string", "description": "Application name (e.g., 'firefox', 'text editor', 'nautilus', 'terminal', 'gnome' for desktop-wide shortcuts)"}}, "required": ["app_name"]}}},

    # 4. AUDIO_CONTROL (facade)
    {"type": "function", "function": {"name": "audio_control", "description": "Unified audio control: volume (set/increase/decrease), mute, unmute, media playback (play, pause, play_pause toggle, next, previous, stop). Handles all sound and media controls.", "parameters": {"type": "object", "properties": {"action": {"type": "string", "description": "Action: volume | mute | unmute | play | pause | play_pause | next | previous | stop"}, "level": {"type": "integer", "description": "Volume level: 0-100 absolute, or +/- for relative change", "default": 0}, "relative": {"type": "boolean", "description": "True for relative volume change (+/-), false for absolute", "default": False}}, "required": ["action"]}}},

    # 5. SYSTEM_SETTINGS (facade)
    {"type": "function", "function": {"name": "system_settings", "description": "Unified system settings: toggle dark mode, night light, do not disturb, WiFi, Bluetooth, set wallpaper. Handles all quick settings and appearance controls. For wallpaper: can use color names (red, blue, green), wallpaper names (fedora, adwaita), or file paths.", "parameters": {"type": "object", "properties": {"action": {"type": "string", "description": "Setting: dark_mode | night_light | do_not_disturb | wifi | bluetooth | wallpaper"}, "state": {"type": "string", "description": "For toggles: 'on' or 'off'. For wallpaper: color name (red, blue), wallpaper name (fedora), or path", "default": "toggle"}, "path": {"type": "string", "description": "Image path for wallpaper action (alternative to state parameter)", "default": ""}}, "required": ["action"]}}},

    # 6. VISION_CONTROL (facade)
    {"type": "function", "function": {"name": "vision_control", "description": "Unified vision operations: take full desktop screenshot, describe what's on screen using AI vision, describe/analyze an image file by path, pick RGB color at screen coordinates, get monitor information (position, resolution, scaling). Handles all screen analysis and display queries. For pick_color: user says 'at 100, 100' or 'at 100-100' or 'at coordinates 100 and 100' means x=100, y=100. For describe_file: use search_files FIRST to get the exact path, then call describe_file with the full path from the search result.", "parameters": {"type": "object", "properties": {"action": {"type": "string", "description": "Action: screenshot (full desktop) | describe (AI vision of current screen) | describe_file (analyze image at path) | pick_color | get_monitors"}, "x": {"type": "integer", "description": "X coordinate in pixels for pick_color action. User says '100, 100' or '100-100' means x=100. Must be positive integer >= 1.", "default": 0}, "y": {"type": "integer", "description": "Y coordinate in pixels for pick_color action. User says '100, 100' or '100-100' or 'at 100 and 100' means y=100. Must be positive integer >= 1.", "default": 0}, "path": {"type": "string", "description": "File path for describe_file action. Supports ~ for home directory. Example: '~/Pictures/screenshot.png'", "default": ""}}, "required": ["action"]}}},

    # 7. WORKSPACE_CONTROL (facade)
    {"type": "function", "function": {"name": "workspace_control", "description": "Unified workspace management: list all virtual desktops, switch to specific workspace by index (0-based). Handles all multi-desktop operations. NOTE: Workspace numbering is 0-based: 'workspace 1' = index 0, 'workspace 2' = index 1, etc. User says 'workspace ONE' or 'workspace 1' means index=1 (second workspace).", "parameters": {"type": "object", "properties": {"action": {"type": "string", "description": "Action: list | activate"}, "index": {"type": "integer", "description": "Workspace index (0-based integer). User says 'workspace 1' or 'workspace ONE' = use index 1. User says 'workspace 0' or 'first workspace' = use index 0.", "default": 0}}, "required": ["action"]}}},

    # 8. LIST_INSTALLED_APPLICATIONS (standalone)
    {"type": "function", "function": {"name": "list_installed_applications", "description": "Lists all installed GUI applications available on the Linux system. Use for 'what apps are installed', 'list all applications', 'show me installed programs'.", "parameters": {"type": "object", "properties": {}}}},

    # 9. SEND_NOTIFICATION (standalone)
    {"type": "function", "function": {"name": "send_notification", "description": "Send a desktop notification immediately or after a delay. Use for reminders, timers, alerts. Examples: 'remind me in 5 minutes', 'notify in 1 hour', 'send notification' (immediate).", "parameters": {"type": "object", "properties": {"summary": {"type": "string", "description": "Notification title/headline (required)"}, "body": {"type": "string", "description": "Notification message body (optional)", "default": ""}, "delay": {"type": "string", "description": "Time delay: '5 minutes', '1 hour', '30 seconds'. Empty = immediate.", "default": ""}}, "required": ["summary"]}}},

    # 10. CLEANUP_SCREENSHOTS (standalone)
    {"type": "function", "function": {"name": "cleanup_screenshots", "description": "Remove all temporary screenshot files to free disk space. Use for maintenance, cleanup tasks.", "parameters": {"type": "object", "properties": {}}}},
]

# Initially, use all tools (will be filtered dynamically during execution)
tool_schema = tool_schema_full

print(f"[SYSTEM] ✓ Consolidated tool schema: {len(tool_schema_full)} tools")
print(f"[SYSTEM]   - Reduced from 34 individual tools")
print(f"[SYSTEM]   - Expected performance: ~17-20s inference (vs 41-69s)")

# ----------------------------------------
# ----------------------------------------
# Voice Setup
# ----------------------------------------
print("[SYSTEM] Loading Neural Voice...")
voice_model = PiperVoice.load("en_US-lessac-medium.onnx")
print("[SYSTEM] Voice ready.")

def strip_markdown(text: str) -> str:
    """Remove markdown formatting from text for TTS.

    Removes:
    - Bold: **text** or __text__
    - Italic: *text* or _text_
    - Code: `text`
    - Headers: # text
    - Lists: - text, * text, 1. text
    """
    import re

    # Remove bold (**text** or __text__)
    text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)
    text = re.sub(r'__(.+?)__', r'\1', text)

    # Remove italic (*text* or _text_) - be careful not to remove emphasis
    text = re.sub(r'\*(.+?)\*', r'\1', text)
    text = re.sub(r'_(.+?)_', r'\1', text)

    # Remove inline code (`text`)
    text = re.sub(r'`(.+?)`', r'\1', text)

    # Remove headers (# text)
    text = re.sub(r'^#+\s*', '', text, flags=re.MULTILINE)

    # Remove list markers (- text, * text, 1. text)
    text = re.sub(r'^\s*[-*]\s+', '', text, flags=re.MULTILINE)
    text = re.sub(r'^\s*\d+\.\s+', '', text, flags=re.MULTILINE)

    return text


def speak(text: str):
    """Converts text to neural speech and plays it."""
    print(f"\n[Agent]: {text}")

    # Skip TTS if text is empty
    if not text or text.strip() == "":
        print(f"[SYSTEM] ⚠️ Skipping TTS - empty text")
        return

    # Strip markdown formatting for better TTS
    clean_text = strip_markdown(text)

    temp_audio_path = "/tmp/agent_response.wav"
    try:
        with wave.open(temp_audio_path, "wb") as wav_file:
            voice_model.synthesize_wav(clean_text, wav_file)
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

def get_default_input_device():
    """
    Get the current system default input device index.

    This ensures we use whichever microphone is selected in GNOME settings,
    even if the user switches between devices (e.g., built-in mic to headset).
    """
    try:
        p = pyaudio.PyAudio()

        # Get the default input device info
        default_device_info = p.get_default_input_device_info()
        device_index = default_device_info['index']
        device_name = default_device_info['name']

        print(f"[AUDIO] Using input device: {device_name} (index {device_index})")

        p.terminate()
        return device_index
    except Exception as e:
        print(f"[AUDIO] Warning: Could not get default input device: {e}")
        print(f"[AUDIO] Falling back to system default")
        return None  # Let PyAudio choose

def listen_and_transcribe():
    """VAD-based continuous listening"""
    CHUNK = 512
    FORMAT = pyaudio.paInt16
    CHANNELS = 1
    RATE = 16000

    # Get the current default input device (respects GNOME settings)
    device_index = get_default_input_device()

    p = pyaudio.PyAudio()

    # Open stream with explicit device index (or None for system default)
    try:
        stream = p.open(
            format=FORMAT,
            channels=CHANNELS,
            rate=RATE,
            input=True,
            input_device_index=device_index,  # Use current system default
            frames_per_buffer=CHUNK
        )
    except Exception as e:
        print(f"[AUDIO] Error opening device {device_index}: {e}")
        print(f"[AUDIO] Retrying with system default...")
        # Fallback: let PyAudio choose
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

                            # Time Whisper transcription
                            whisper_start = time.time()
                            segments, info = whisper_model.transcribe(
                                temp_path,
                                beam_size=5,
                                temperature=0.2,  # 0.2 = better spacing and less hallucinations (was 0.0)
                                word_timestamps=True,  # Help with word boundary detection
                                vad_filter=True,
                                vad_parameters=dict(min_silence_duration_ms=500),
                                initial_prompt="Commands for opening files, applications, and websites. Files may have spaces in names like 'bugs and ideas.txt' or 'practical presentation advice.txt'."
                            )
                            whisper_elapsed = time.time() - whisper_start

                            text = "".join([segment.text for segment in segments]).strip()
                            print(f'⏱️  Whisper transcription: {whisper_elapsed:.2f}s')
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
        raise  # Re-raise to exit main loop

def get_installed_gui_apps():
    """
    Scans application directory for user-visible GUI programs.

    Returns dict with:
    - 'count': total user-visible apps
    - 'samples': representative apps from key categories
    """
    app_dir = "/usr/share/applications"
    categorized_apps = {
        'browser': [],
        'text_editor': [],
        'file_manager': [],
        'media': [],
        'graphics': [],
        'terminal': [],
        'system_utility': [],
        'other': []
    }

    app_count = 0
    try:
        for filename in os.listdir(app_dir):
            if not filename.endswith(".desktop"):
                continue

            filepath = os.path.join(app_dir, filename)
            try:
                with open(filepath, 'r') as f:
                    content = f.read()

                # Skip if NoDisplay=true (hidden system utilities)
                if 'NoDisplay=true' in content:
                    continue

                app_count += 1

                # Extract Name and Categories from [Desktop Entry] section only
                name = None
                categories = ""
                in_desktop_entry = False

                for line in content.split('\n'):
                    line = line.strip()

                    # Track which section we're in
                    if line.startswith('['):
                        in_desktop_entry = (line == '[Desktop Entry]')
                        continue

                    # Only parse from [Desktop Entry] section
                    if in_desktop_entry:
                        if line.startswith('Name='):
                            name = line.split('=', 1)[1].strip()
                        elif line.startswith('Categories='):
                            categories = line.split('=', 1)[1].strip().lower()

                if not name:
                    continue

                # Categorize
                if 'browser' in categories or 'webbrowser' in categories:
                    categorized_apps['browser'].append(name)
                elif 'texteditor' in categories or 'editor' in categories:
                    categorized_apps['text_editor'].append(name)
                elif 'filemanager' in categories:
                    categorized_apps['file_manager'].append(name)
                elif 'audio' in categories or 'video' in categories or 'player' in categories:
                    categorized_apps['media'].append(name)
                elif 'graphics' in categories or 'image' in categories:
                    categorized_apps['graphics'].append(name)
                elif 'terminalemulator' in categories:
                    categorized_apps['terminal'].append(name)
                elif 'settings' in categories or 'system' in categories or 'monitor' in categories:
                    categorized_apps['system_utility'].append(name)
                else:
                    categorized_apps['other'].append(name)

            except Exception:
                continue

    except Exception as e:
        # Fallback
        return {
            'count': 3,
            'samples': ['Firefox', 'Text Editor', 'Files']
        }

    # Build representative samples from key categories
    samples = []
    for category in ['browser', 'text_editor', 'file_manager', 'terminal', 'media', 'graphics', 'system_utility']:
        if categorized_apps[category]:
            samples.append(categorized_apps[category][0])

    return {
        'count': app_count,
        'samples': samples[:7],  # Limit to 7 samples for voice feedback
        'categorized': categorized_apps
    }

live_app_list = get_installed_gui_apps()
print(f"[SYSTEM] Found {live_app_list['count']} user-visible applications (samples: {', '.join(live_app_list['samples'][:3])})")

# ----------------------------------------
# Conversation Mode Functions
# ----------------------------------------
def classify_intent_type(user_input: str) -> str:
    """
    Classify if user input is a desktop command or conversational chat.

    Returns: 'command' or 'conversation'
    """
    classifier_prompt = f"""Classify this voice input as either:
- command: Desktop control actions (open/close apps, window operations, mouse/keyboard, screenshots, colors, volume/audio control, media playback, system settings)
- conversation: Questions, chat, help requests, explanations, general knowledge

Examples of COMMAND:
- "open firefox"
- "close text editor"
- "describe screen"
- "maximize window"
- "scroll down"
- "drag from left to right"
- "screenshot the window"
- "pick color at 500 300"
- "what color is at position 800 400"
- "click at 100 200"
- "switch to workspace 2"
- "type hello world"
- "press ctrl c"
- "enable automation"
- "disable automation"
- "turn on automation"
- "turn off automation"
- "clean up screenshots"
- "delete screenshots"
- "set volume to 50"
- "increase volume by 10"
- "decrease volume"
- "turn volume up"
- "turn volume down"
- "mute"
- "unmute"
- "mute volume"
- "unmute volume"
- "play"
- "pause"
- "play track"
- "pause track"
- "playtrack"
- "next track"
- "previous track"
- "skip"
- "skip track"
- "play music"
- "pause music"
- "next song"
- "previous song"
- "stop music"
- "turn on dark mode"
- "turn off dark mode"
- "enable dark mode"
- "disable dark mode"
- "switch to light mode"
- "turn on night light"
- "turn off night light"
- "enable do not disturb"
- "disable do not disturb"
- "turn on wifi"
- "turn off wifi"
- "enable bluetooth"
- "disable bluetooth"
- "open google.com"
- "go to github.com"
- "open https://example.com"
- "open screenshot.png"
- "open screenshot in pictures"
- "open report.pdf"
- "open ~/Documents/report.pdf"
- "find all PDFs"
- "search for screenshots"
- "where are my tax documents"
- "list installed applications"
- "show installed apps"
- "what apps are installed"
- "notify me in 5 minutes"
- "remind me about meeting"
- "send notification"
- "alert me in 1 hour"
- "cleanup screenshots"
- "remove screenshots"
- "list workspaces"
- "switch to workspace 1"

Examples of CONVERSATION:
- "what is docker"
- "how do I install nodejs"
- "tell me about python"
- "what's the weather"
- "explain kubernetes"
- "what does this code do"

Input: "{user_input}"

Reply with ONE word only: command or conversation"""

    try:
        response = call_llama_server(
            messages=[{'role': 'user', 'content': classifier_prompt}],
            temperature=0.1,
            max_tokens=10
        )

        result = response['message']['content'].strip().lower()

        # Parse response - look for keywords
        if 'command' in result:
            return 'command'
        elif 'conversation' in result:
            return 'conversation'
        else:
            # Default to conversation if unclear (safer)
            print(f"[CLASSIFIER] Unclear result: '{result}', defaulting to conversation")
            return 'conversation'

    except Exception as e:
        print(f"[CLASSIFIER] Error: {e}, defaulting to conversation")
        return 'conversation'


def handle_conversation(user_input: str, conversation_history: list) -> tuple:
    """
    Handle conversational chat with Gemma.

    Args:
        user_input: User's question/chat
        conversation_history: List of previous message dicts

    Returns:
        (answer_text, updated_history)
    """
    conversation_prompt = """You are a helpful AI assistant.
Answer questions clearly and concisely.
Keep responses under 3 sentences unless more detail is requested.
Be friendly and informative."""

    # Build message history
    messages = [{'role': 'system', 'content': conversation_prompt}]
    messages.extend(conversation_history)
    messages.append({'role': 'user', 'content': user_input})

    try:
        print(f"[CHAT] Generating response...")

        if DEBUG:
            print(f"[DEBUG] Conversation messages sent to LLM:")
            for msg in messages:
                role = msg.get('role', 'unknown')
                content = msg.get('content', '')
                if len(content) > 200:
                    content = content[:200] + "..."
                print(f"  [{role}]: {content}")

        response = call_llama_server(
            messages=messages,
            temperature=0.7,
            max_tokens=500  # Generous limit for conversation
        )

        if DEBUG:
            print(f"[DEBUG] Response content length: {len(response['message'].get('content', ''))}")

        answer = response['message']['content']

        # Update history
        conversation_history.append({'role': 'user', 'content': user_input})
        conversation_history.append({'role': 'assistant', 'content': answer})

        # Keep only last 20 messages (10 exchanges)
        if len(conversation_history) > 20:
            conversation_history = conversation_history[-20:]

        return answer, conversation_history

    except Exception as e:
        error_msg = f"Sorry, I encountered an error: {str(e)}"
        return error_msg, conversation_history


# ----------------------------------------
# Orchestrator Loop
# ----------------------------------------
def run_agent():
    print("\n" + "="*60)
    if PUSH_TO_TALK_MODE:
        print("💬  CONVERSATIONAL Agentic OS - PUSH-TO-TALK MODE")
    else:
        print("💬  CONVERSATIONAL Agentic OS")
    print("="*60)
    print("✅ VAD - unlimited voice input")
    print("✅ Safe close - never loses data without your consent")
    print("✅ Dialog detection - reads options to you")
    print("✅ Voice confirmation - you choose what to do")
    print("⭐ Command mode (default) - desktop control")
    print("⭐ Chat mode (optional) - ask questions, get help")
    if PUSH_TO_TALK_MODE:
        print("🎤 PUSH-TO-TALK - Press ENTER to speak\n")
    else:
        print()

    print("Mode switching (starts in command mode):")
    print("  • 'switch to chat mode' - switch to conversation")
    print("  • 'switch to command mode' - back to commands")
    print("  • 'clear history' - clear chat history")
    if PUSH_TO_TALK_MODE:
        print("\n💡 Tip: PTT mode prevents accidental triggering during presentations\n")
    else:
        print()

    print("[SYSTEM] Starting MCP client...")
    mcp_client.start()

    # Build application index for natural language resolution
    print("[SYSTEM] Building application index...")
    build_app_index()

    # Health check: ensure automation extension is running and enabled
    print("[SYSTEM] Checking automation health...")
    health_ok, health_msg = check_automation_health(auto_enable=True)
    if health_ok:
        print(f"[SYSTEM] ✓ {health_msg}")
    else:
        print(f"[SYSTEM] ⚠️  {health_msg}")
        print("[SYSTEM] Some features may not work until automation is enabled.")

    # Command mode system message
    command_system_msg = {
        "role": "system",
        "content": "You are a silent system orchestrator. Your ONLY job is to execute tool calls based on user intent. DO NOT output conversational text. DO NOT confirm actions. DO NOT be polite. If you need to use a tool, output ONLY the tool call. FORGET gedit and USE gnome-text-editor. When a command requires multiple steps, make tool calls one at a time. After receiving tool results, either make another tool call or return a brief spoken summary. Keep summaries under 2 sentences."
    }

    # State variables
    current_mode = 'command'  # Start in command mode (explicit switching only)
    conversation_history = []
    command_messages = [command_system_msg]

    # Notify user that system is ready
    print("[SYSTEM] ✓ Voice orchestrator ready")
    if PUSH_TO_TALK_MODE:
        print("\n" + "="*60)
        print("🎤 PUSH-TO-TALK MODE ACTIVE")
        print("="*60)
        print("Press ENTER to speak a command")
        print("Press Ctrl+C to exit\n")
    else:
        speak("Voice orchestrator ready. Listening for commands.")

    try:
        while True:
            # PTT mode: wait for Enter key press
            if PUSH_TO_TALK_MODE:
                try:
                    input("🎤 Press ENTER to speak (Ctrl+C to exit): ")
                except EOFError:
                    print("\n[SYSTEM] EOF detected, exiting...")
                    break
                print("\n[PTT] 🟢 Listening activated...")

            user_input = listen_and_transcribe()
            if not user_input:
                if PUSH_TO_TALK_MODE:
                    print("[PTT] ⚪ No speech detected, ready for next command\n")
                continue

            # Start timing from when user input is captured
            response_start_time = time.time()

            user_input_lower = user_input.lower()

            # Check for explicit mode switching (these don't need timing - just mode control)
            if 'switch to command mode' in user_input_lower or 'command mode' in user_input_lower:
                current_mode = 'command'
                speak("Command mode. Ready for desktop commands.")
                print(f"[MODE] 🔧 Command mode")
                continue

            if 'switch to chat mode' in user_input_lower or 'chat mode' in user_input_lower or 'conversation mode' in user_input_lower:
                current_mode = 'conversation'
                speak("Chat mode activated. Ask me anything!")
                print(f"[MODE] 💬 Conversation mode")
                continue

            # Check for history management
            if 'clear history' in user_input_lower or 'new topic' in user_input_lower:
                conversation_history = []
                speak("Conversation history cleared.")
                print(f"[CHAT] 🗑️  History cleared")
                continue

            # Use current mode (no automatic detection)
            intent_type = current_mode
            print(f"[MODE] {intent_type}")

            # Route to appropriate handler
            if intent_type == 'command':
                # COMMAND MODE - execute desktop tools
                print(f"[COMMAND] Processing: {user_input}")

                command_messages.append({"role": "user", "content": user_input})

                # Hybrid namespace + retrieval approach
                # Retrieve top 2 most relevant namespaces for this query (faster inference)
                retrieval_start_time = time.time()
                relevant_namespaces, detected_app = retrieve_relevant_namespaces(user_input, top_k=2)

                # Auto-focus: if an app was detected, focus its window before LLM acts
                if detected_app:
                    try:
                        focus_result = window_control("focus", detected_app)
                        if "No window found" in focus_result:
                            print(f"[ROUTING] App '{detected_app}' not running, skipping auto-focus")
                        else:
                            print(f"[ROUTING] Auto-focused: {focus_result}")
                            command_messages[-1]["content"] += f"\n[{detected_app} is already focused. Do NOT open or search for it.]"
                    except Exception as e:
                        print(f"[ROUTING] Auto-focus failed: {e}")

                # Build filtered tool schema with only relevant tools
                filtered_tools = build_filtered_tool_schema(relevant_namespaces)
                retrieval_elapsed = time.time() - retrieval_start_time
                print(f"[TIMING] ⏱️  RAG retrieval took: {retrieval_elapsed:.3f}s ({len(filtered_tools)} tools)")

                MAX_CHAIN_STEPS = 5
                last_tool_result = None

                for chain_step in range(MAX_CHAIN_STEPS):
                    if chain_step > 0:
                        print(f"[CHAIN] Step {chain_step + 1}/{MAX_CHAIN_STEPS}")

                    if DEBUG:
                        print(f"[DEBUG] Messages sent to LLM:")
                        for msg in command_messages:
                            role = msg.get('role', 'unknown')
                            content = msg.get('content', '')
                            if content and len(content) > 200:
                                content = content[:200] + "..."
                            print(f"  [{role}]: {content}")
                        print(f"[DEBUG] Available tools: {[t['function']['name'] for t in filtered_tools]}")

                    llm_start_time = time.time()
                    response = call_llama_server(
                        messages=command_messages,
                        tools=filtered_tools,
                        temperature=0.0,
                        max_tokens=300
                    )
                    llm_elapsed = time.time() - llm_start_time
                    print(f"[TIMING] ⏱️  LLM inference took: {llm_elapsed:.2f}s")

                    if DEBUG:
                        print(f"[DEBUG] Gemma eval_count: {response.get('eval_count', 'N/A')} tokens")
                        print(f"[DEBUG] Response content length: {len(response['message'].get('content', ''))}")
                        if response['message'].get('content'):
                            print(f"[DEBUG] Content preview: {response['message']['content'][:200]}")
                        if response['message'].get('tool_calls'):
                            print(f"[DEBUG] Tool calls:")
                            for tc in response['message']['tool_calls']:
                                print(f"  - {tc['function']['name']}: {tc['function']['arguments']}")

                    message = response['message']
                    command_messages.append(message)

                    if not message.get('tool_calls'):
                        # LLM returned text — final answer
                        content = message.get('content', '').strip()
                        if content:
                            print(f"\n[OS Feedback]: {content}")
                            response_time = time.time() - response_start_time
                            print(f"[TIMING] ⏱️  Response time: {response_time:.2f}s")
                            speak(content)
                        elif last_tool_result:
                            print(f"\n[OS Feedback]: {last_tool_result}")
                            response_time = time.time() - response_start_time
                            print(f"[TIMING] ⏱️  Response time: {response_time:.2f}s")
                            speak(last_tool_result)
                        else:
                            print("[COMMAND] ⚠️  No tool call generated. Try rephrasing or switch to chat mode.")
                            response_time = time.time() - response_start_time
                            print(f"[TIMING] ⏱️  Response time: {response_time:.2f}s")
                            speak("I'm not sure what command to run. Try rephrasing or say 'switch to chat mode'.")
                        break

                    for tool_call in message['tool_calls']:
                        tool_name = tool_call['function']['name']
                        arguments = tool_call['function']['arguments']
                        tool_call_id = tool_call.get('id', f"call_{chain_step}_{tool_name}")

                        # Parse JSON string to dict if needed (llama-server returns string, Ollama returns dict)
                        if isinstance(arguments, str):
                            arguments = json.loads(arguments)

                        result = None

                        # Check if it's a direct MCP tool (no wrapper needed)
                        if tool_name in direct_mcp_tools:
                            print(f"\n[SYSTEM] Calling MCP tool directly: {tool_name}")

                            # Special handling for gnome_search: check for markers
                            if tool_name == "gnome_search" and "query" in arguments:
                                query = arguments["query"].strip()

                                # Check for " website" marker - use xdg-open for deterministic browser opening
                                if query.endswith(' website'):
                                    url = query[:-8].strip()  # Remove " website" suffix

                                    # Add protocol if missing
                                    if not url.startswith('http://') and not url.startswith('https://'):
                                        url = f"https://www.{url}"

                                    print(f"[GNOME_SEARCH] Detected website marker, opening URL via xdg-open: {url}")
                                    subprocess.run(['xdg-open', url], check=False,
                                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                                    result = f"Opening {url} in browser"

                                # Check for " file" marker - use open_file MCP tool for smart file opening
                                elif query.endswith(' file'):
                                    filename = query[:-5].strip()  # Remove " file" suffix

                                    print(f"[GNOME_SEARCH] Detected file marker, using open_file: {filename}")
                                    result = mcp_client.call_tool("open_file", {"path": filename})

                                else:
                                    # Normal GNOME search for apps/settings
                                    result = mcp_client.call_tool(tool_name, arguments)
                            else:
                                result = mcp_client.call_tool(tool_name, arguments)

                            # Auto-recovery: if automation is disabled, enable and retry
                            if "Error" in result and ("disabled" in result.lower() or "not responding" in result.lower()):
                                print(f"[SYSTEM] Tool failed, attempting auto-recovery...")
                                health_ok, health_msg = check_automation_health(auto_enable=True)
                                if health_ok:
                                    print(f"[SYSTEM] Retrying {tool_name}...")
                                    result = mcp_client.call_tool(tool_name, arguments)
                                else:
                                    result = f"Error: {health_msg}"

                        # Check if it's a custom wrapper function
                        elif tool_name in available_tools:
                            function_to_call = available_tools[tool_name]
                            result = function_to_call(**arguments)

                            # Auto-recovery: if result indicates automation error, enable and retry
                            if "Error" in result and ("disabled" in result.lower() or "not responding" in result.lower()):
                                print(f"[SYSTEM] Tool failed, attempting auto-recovery...")
                                health_ok, health_msg = check_automation_health(auto_enable=True)
                                if health_ok:
                                    print(f"[SYSTEM] Retrying {tool_name}...")
                                    result = function_to_call(**arguments)
                                else:
                                    result = f"Error: {health_msg}"

                        else:
                            result = f"Unknown tool: {tool_name}"
                            print(f"[COMMAND] ⚠️  {result}")

                        print(f"\n[OS Feedback]: {result}")
                        last_tool_result = result

                        # Append tool result to messages so LLM can chain
                        command_messages.append({
                            "role": "tool",
                            "tool_call_id": tool_call_id,
                            "content": str(result)
                        })

                else:
                    # Exhausted MAX_CHAIN_STEPS — speak whatever we have
                    print(f"[CHAIN] ⚠️  Reached max chain steps ({MAX_CHAIN_STEPS})")
                    if last_tool_result:
                        response_time = time.time() - response_start_time
                        print(f"[TIMING] ⏱️  Response time: {response_time:.2f}s")
                        speak(last_tool_result)

                response_time = time.time() - response_start_time
                print(f"[TIMING] ⏱️  Total chain time: {response_time:.2f}s")
                command_messages = [command_system_msg]

            else:  # intent_type == 'conversation'
                # CONVERSATION MODE - chat with Gemma
                print(f"[CHAT] Processing: {user_input}")

                answer, conversation_history = handle_conversation(user_input, conversation_history)

                print(f"\n[Agent]: {answer}")
                response_time = time.time() - response_start_time
                print(f"[TIMING] ⏱️  Response time: {response_time:.2f}s")
                speak(answer)

            # Blank line before next prompt in PTT mode
            if PUSH_TO_TALK_MODE:
                print()

    except KeyboardInterrupt:
        print("\n[SYSTEM] 🛑 Ctrl+C received, shutting down gracefully...")
    finally:
        # Cleanup: optionally kill llama-server on exit
        if KILL_SERVER_ON_EXIT:
            print("[SYSTEM] Stopping llama-server (--kill-server flag)...")
            kill_server()
        else:
            print("[SYSTEM] Note: llama-server is still running on port 8081")
            print("[SYSTEM] Reuse it on next run for faster startup, or kill with --kill-server flag")

if __name__ == "__main__":
    try:
        run_agent()
    except KeyboardInterrupt:
        print("\n\n[SYSTEM] Shutting down Agentic OS...")
