#!/usr/bin/env python3
"""
Voice-Driven Desktop Orchestrator with CONVERSATIONAL Mode

Features:
- ✅ VAD continuous listening
- ✅ Configurable AI models (granite, gemma4, etc.)
- ✅ Vision support for screen analysis
- ✅ Tool calling for desktop automation
- ✅ SAFE close handling with dialog detection
- ✅ Reads dialog options to user via voice
- ✅ Waits for user's voice choice
- ✅ Verifies action succeeded
- ✅ Never loses user data without explicit consent
- ⭐ Conversation mode - chat with AI for questions/help
- ⭐ Automatic intent detection - seamlessly switches between command & chat
- ⭐ Explicit mode control - force command/chat mode when needed
- ⭐ Easy model configuration - change models at top of file

Configuration:
To change models, edit the MODEL CONFIGURATION section (lines 48-71)
"""

import os
import sys

# Force offline mode for sentence-transformers BEFORE import
# This prevents internet checks to HuggingFace Hub
os.environ['TRANSFORMERS_OFFLINE'] = '1'
os.environ['HF_HUB_OFFLINE'] = '1'

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
from queue import Queue
from sentence_transformers import SentenceTransformer

from faster_whisper import WhisperModel
from piper.voice import PiperVoice
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from dialog_handler import DialogHandler

# ========================================
# 🎯 MODEL CONFIGURATION
# ========================================
# Change models here - use models that support vision + tool calling
#
# Available models (tested):
#   • granite3.2-vision:latest - 2.4GB, 2-3x faster, supports vision + tools ⭐ RECOMMENDED
#   • gemma4:e4b              - 9.6GB, slower but stable, supports vision + tools
#
# For best performance:
#   1. Use granite3.2-vision for everything (fastest)
#   2. Or use granite for commands, keep gemma4 for vision only
# ========================================

# Model for command mode (tool calling)
COMMAND_MODEL = 'gemma4:e4b'  # Change to 'gemma4:e4b' if needed

# Model for vision tasks (describe_desktop)
VISION_MODEL = 'gemma4:e4b'   # Change to 'gemma4:e4b' if needed

# Model for conversation mode (chat/questions)
CONVERSATION_MODEL = 'gemma4:e4b'  # Change to 'gemma4:e4b' if needed

# Model for intent classification (command vs chat detection)
CLASSIFIER_MODEL = 'gemma4:e4b'  # Change to 'gemma4:e4b' if needed

# ========================================
# End of configuration
# ========================================

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

def build_app_index():
    """Build index of desktop applications from .desktop files.

    Maps natural language terms (Name, GenericName, Keywords) to executable names.
    org.gnome apps have priority and overwrite conflicts.
    """
    global app_name_map, app_friendly_name
    app_name_map = {}
    app_friendly_name = {}

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

        if app['name']:
            app_name_map[app['name'].lower()] = exec_name

        if app['generic_name']:
            app_name_map[app['generic_name'].lower()] = exec_name

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

        if app['name']:
            app_name_map[app['name'].lower()] = exec_name

        if app['generic_name']:
            app_name_map[app['generic_name'].lower()] = exec_name

        for keyword in app['keywords']:
            if keyword:
                app_name_map[keyword.lower()] = exec_name

    print(f"[SYSTEM] ✓ Indexed {len(app_name_map)} app name mappings ({gnome_count} org.gnome with priority)")

# ----------------------------------------
# Tool Functions
# ----------------------------------------
def launch_application(app_name: str) -> str:
    """Launches a graphical application in the background."""
    # Resolve app name using index
    resolved_exec = app_name_map.get(app_name.lower(), app_name)
    friendly_name = app_friendly_name.get(resolved_exec, resolved_exec)

    print(f"\n[SYSTEM] Executing command: Launching {friendly_name}...")
    if resolved_exec != app_name:
        print(f"[SYSTEM] Resolved '{app_name}' → '{resolved_exec}' ({friendly_name})")

    try:
        subprocess.Popen(
            [resolved_exec],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            start_new_session=True
        )
        return f"Successfully launched {friendly_name}."
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

        print(f"[SYSTEM] 🤖 Running vision analysis with gemma4 (this may take 2-10 seconds)...")
        print(f"[SYSTEM] ⏳ Please wait...")

        response = ollama.chat(
            model=VISION_MODEL,
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
                'num_predict': 800,  # Gemma4 needs ~400-500 for thinking + content
                'temperature': 0.7,
                'num_gpu': 99,
            }
        )

        print(f"[SYSTEM] ✅ Vision analysis complete!")

        # Extract content (with 800 tokens, should always be in content field)
        message = response.message if hasattr(response, 'message') else response['message']
        description = message.content if hasattr(message, 'content') else message.get('content', '')

        if not description or description.strip() == "":
            print(f"[SYSTEM] ⚠️ WARNING: Gemma4 returned empty content!")
            print(f"[SYSTEM] Done reason: {response.done_reason if hasattr(response, 'done_reason') else 'unknown'}")
            print(f"[SYSTEM] Tokens used: {response.eval_count if hasattr(response, 'eval_count') else 'unknown'}")
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

def list_installed_applications() -> str:
    """Lists all installed GUI applications on the system."""
    print(f"\n[SYSTEM] Scanning for installed applications...")
    try:
        apps = get_installed_gui_apps()
        app_count = len(apps)
        if app_count == 0:
            return "No applications found."
        return f"Found {app_count} installed applications including {', '.join(apps[:5])}, and others."
    except Exception as e:
        return f"Error listing applications: {str(e)}"

def list_open_windows() -> str:
    """Lists all currently open windows."""
    print(f"\n[SYSTEM] Listing open windows via MCP...")
    try:
        result = mcp_client.call_tool("list_windows", {})
        if result.startswith("Error"):
            return result
        windows = json.loads(result)
        if not windows:
            return "No windows are currently open."
        window_titles = [w.get('title', 'Untitled') for w in windows[:10]]
        return f"Found {len(windows)} open windows: {', '.join(window_titles)}"
    except Exception as e:
        return f"Error listing windows: {str(e)}"

def smart_match_window(window_name: str, windows: list) -> dict:
    """
    Smart window matching that prioritizes app names over full window titles.

    Matching strategy:
    1. If window_name is empty, return the focused window
    2. Extract app name from wmClass (e.g., "text editor" matches "org.gnome.TextEditor")
    3. Match against simplified app names (e.g., "TextEditor" -> "text editor")
    4. Fall back to title matching
    """
    if not window_name or window_name.strip() == "":
        # Find focused window
        for w in windows:
            if w.get('state', {}).get('focused', False):
                return w
        # If no focused window found, return first window
        return windows[0] if windows else None

    window_name_lower = window_name.lower()

    # Try app name matching first (from wmClass)
    for w in windows:
        wm_class = w.get('wmClass', '')

        # Extract app name from wmClass
        # "org.gnome.TextEditor" -> "texteditor"
        # "gnome-text-editor" -> "texteditor"
        app_name = wm_class.lower()
        app_name = app_name.replace('org.gnome.', '')
        app_name = app_name.replace('org.', '')
        app_name = app_name.replace('-', '')
        app_name = app_name.replace('_', '')

        # Also try matching the original wmClass
        wm_class_lower = wm_class.lower()

        # Normalize window_name for comparison
        search_term = window_name_lower.replace(' ', '').replace('-', '').replace('_', '')

        # Check if app name matches
        if search_term in app_name or window_name_lower in wm_class_lower:
            return w

    # Fall back to title matching
    for w in windows:
        title = w.get('title', '').lower()
        if window_name_lower in title:
            return w

    return None

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
    import re
    name = re.sub('([a-z])([A-Z])', r'\1 \2', name)

    # Capitalize each word
    name = ' '.join(word.capitalize() for word in name.split())

    return name

def focus_window_by_name(window_name: str = "") -> str:
    """Focus a window by its title or application name. If empty, focuses the currently active window."""
    if window_name:
        print(f"\n[SYSTEM] Focusing window: {window_name}...")
    else:
        print(f"\n[SYSTEM] Focusing current window...")
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
    """
    SAFE close window with dialog handling.

    Steps:
    1. Try to close window normally
    2. Detect if save dialog appeared
    3. Read dialog options to user via voice
    4. Wait for user's voice choice
    5. Click appropriate button
    6. Verify success
    7. Report back

    NO force close option - always respects user's data!
    """
    if window_name:
        print(f"\n[SYSTEM] Closing window: {window_name}...")
    else:
        print(f"\n[SYSTEM] Closing current window...")

    try:
        # Step 1: Find target window
        result = mcp_client.call_tool("list_windows", {})
        if result.startswith("Error"):
            return result

        windows = json.loads(result)
        target_window = smart_match_window(window_name, windows)

        if not target_window:
            return f"No window found matching '{window_name}'"

        window_id = target_window['id']
        window_title = target_window.get('title', 'Unknown')
        app_name = target_window.get('wmClass', '')

        print(f"[SYSTEM] Attempting to close: {window_title}")

        # Step 2: Try to close normally
        result = mcp_client.call_tool("close_window", {"window_id": window_id})

        # Step 3: Wait for potential dialog
        print(f"[SYSTEM] Checking for save dialog (app: {app_name})...")

        # Increase timeout and add debug output
        dialog = dialog_handler.detect_save_dialog(app_name=None, timeout=3.0)  # Don't filter by app

        if not dialog:
            print(f"[SYSTEM] ⚠️ No dialog detected via dogtail")

            # Double-check - maybe window already closed
            time.sleep(0.5)
            result = mcp_client.call_tool("list_windows", {})
            if not result.startswith("Error"):
                windows_after = json.loads(result)
                if not any(w['id'] == window_id for w in windows_after):
                    print(f"[SYSTEM] ✅ Window closed successfully (no dialog)")
                    return f"Successfully closed {get_friendly_app_name(app_name)}"

            # Window still exists but no dialog found
            print(f"[SYSTEM] ⚠️ Window still open, but no dialog detected")
            print(f"[SYSTEM]     This may mean:")
            print(f"[SYSTEM]     1. No unsaved changes (window just didn't close yet)")
            print(f"[SYSTEM]     2. Dialog not accessible via dogtail")
            print(f"[SYSTEM]     3. Dialog hasn't appeared yet (slow app)")

            # Try one more time with longer timeout
            print(f"[SYSTEM] Trying again with 5 second timeout...")
            dialog = dialog_handler.detect_save_dialog(app_name=None, timeout=5.0)

            if not dialog:
                return f"Window {window_title} did not close. No dialog detected. The window may not have unsaved changes, or dialog detection failed."

        # Step 4: Dialog detected! Read options to user
        print("[SYSTEM] 💬 Save dialog detected!")
        description = dialog_handler.describe_dialog(dialog)

        # Get button options (if available)
        buttons = dialog['info']['buttons']
        if buttons:
            button_list = ', '.join([btn['text'] for btn in buttons])
        else:
            # Fallback to standard options if buttons not detected
            button_list = "Save, Discard, Cancel"
            print(f"[DIALOG] ⚠️ Buttons not detected, using standard options")

        # Prepare voice prompt
        voice_prompt = f"The window has unsaved changes. Options: {button_list}. What would you like to do?"

        print(f"\n[DIALOG] {description}")
        print(f"[DIALOG] Options: {button_list}")
        print(f"[DIALOG] Asking user for choice...\n")

        # Step 5: Speak options to user
        speak(voice_prompt)

        # Step 6: Listen for user's choice
        print("[SYSTEM] 🎤 Listening for your choice...")
        user_choice = listen_and_transcribe()

        if not user_choice:
            speak("No response heard. Canceling close operation.")
            # Try to press Escape to close dialog
            mcp_client.call_tool("key_combo", {"keys": "Escape"})
            return f"Close operation canceled - no user input"

        print(f"[DIALOG] User chose: {user_choice}")

        # Step 7: Use keyboard shortcut instead of clicking
        # This is more reliable than trying to click buttons via dogtail
        success = dialog_handler.activate_button_by_keyboard(dialog, user_choice)

        if not success:
            speak(f"Could not understand choice {user_choice}. Say save, discard, or cancel.")
            mcp_client.call_tool("key_combo", {"keys": "Escape"})
            return f"Unrecognized choice: {user_choice}. Options are: save, discard, cancel."

        # Step 8: Verify dialog closed
        print("[SYSTEM] Verifying dialog closed...")
        closed = dialog_handler.verify_dialog_closed(dialog, timeout=2.0)

        if closed:
            # Check if window actually closed (for Save/Discard) or still open (for Cancel)
            time.sleep(0.5)
            result = mcp_client.call_tool("list_windows", {})
            if not result.startswith("Error"):
                windows_final = json.loads(result)
                window_still_open = any(w['id'] == window_id for w in windows_final)

                if window_still_open:
                    return f"Dialog closed. {get_friendly_app_name(app_name)} is still open (you may have chosen Cancel)"
                else:
                    return f"Successfully closed {get_friendly_app_name(app_name)}"

            return f"Dialog handled successfully"
        else:
            return f"Dialog might still be open. Please check manually."

    except Exception as e:
        print(f"[ERROR] {e}")
        return f"Error closing window: {str(e)}"

def type_text_in_window(text: str) -> str:
    """Type text into the currently focused window."""
    print(f"\n[SYSTEM] Typing text: {text[:50]}...")
    try:
        result = mcp_client.call_tool("type_text", {"text": text})
        return f"Typed: {text}"
    except Exception as e:
        return f"Error typing text: {str(e)}"

def press_key_combo(keys: str) -> str:
    """Press a keyboard combination like Ctrl+C, Alt+Tab, etc."""
    print(f"\n[SYSTEM] Pressing key combo (raw): {keys}...")

    # Normalize key combo format for MCP
    # MCP expects: "Ctrl+s", "Alt+Tab", "Shift+F5"
    # Gemma might generate: "control s", "ctrl+s", "Control+s", etc.

    # Replace common variations
    normalized = keys
    normalized = normalized.replace("control", "Ctrl")
    normalized = normalized.replace("Control", "Ctrl")
    normalized = normalized.replace("ctrl", "Ctrl")
    normalized = normalized.replace("alt", "Alt")
    normalized = normalized.replace("shift", "Shift")
    normalized = normalized.replace("Shift", "Shift")
    normalized = normalized.replace("super", "Super")
    normalized = normalized.replace("Super", "Super")

    # Add + if missing (space-separated to plus-separated)
    # "Ctrl s" → "Ctrl+s"
    if " " in normalized and "+" not in normalized:
        normalized = normalized.replace(" ", "+")

    print(f"[SYSTEM] Pressing key combo (normalized): {normalized}...")

    try:
        result = mcp_client.call_tool("key_combo", {"keys": normalized})
        return f"Pressed {normalized}"
    except Exception as e:
        return f"Error pressing keys: {str(e)}"

def set_volume(level: int = None, relative: bool = False) -> str:
    """Set system volume level."""
    print(f"\n[SYSTEM] Setting volume to {level}% ({'relative' if relative else 'absolute'})...")
    try:
        if level is None:
            return "Volume level not specified"

        result = mcp_client.call_tool("set_volume", {
            "volume": level,
            "relative": relative
        })
        return result
    except Exception as e:
        return f"Error setting volume: {str(e)}"

def mute_volume() -> str:
    """Mute system volume."""
    print(f"\n[SYSTEM] Muting volume...")
    try:
        result = mcp_client.call_tool("mute_volume", {"mute": True})
        return result
    except Exception as e:
        return f"Error muting: {str(e)}"

def unmute_volume() -> str:
    """Unmute system volume."""
    print(f"\n[SYSTEM] Unmuting volume...")
    try:
        result = mcp_client.call_tool("mute_volume", {"mute": False})
        return result
    except Exception as e:
        return f"Error unmuting: {str(e)}"

def media_play() -> str:
    """Start media playback."""
    print(f"\n[SYSTEM] Starting playback...")
    try:
        result = mcp_client.call_tool("media_control", {"action": "play"})
        return result
    except Exception as e:
        return f"Error playing: {str(e)}"

def media_pause() -> str:
    """Pause media playback."""
    print(f"\n[SYSTEM] Pausing playback...")
    try:
        result = mcp_client.call_tool("media_control", {"action": "pause"})
        return result
    except Exception as e:
        return f"Error pausing: {str(e)}"

def media_play_pause() -> str:
    """Toggle play/pause media playback."""
    print(f"\n[SYSTEM] Toggling play/pause...")
    try:
        result = mcp_client.call_tool("media_control", {"action": "play_pause"})
        return result
    except Exception as e:
        return f"Error toggling playback: {str(e)}"

def media_next() -> str:
    """Skip to next track."""
    print(f"\n[SYSTEM] Skipping to next track...")
    try:
        result = mcp_client.call_tool("media_control", {"action": "next"})
        return result
    except Exception as e:
        return f"Error skipping: {str(e)}"

def media_previous() -> str:
    """Skip to previous track."""
    print(f"\n[SYSTEM] Skipping to previous track...")
    try:
        result = mcp_client.call_tool("media_control", {"action": "previous"})
        return result
    except Exception as e:
        return f"Error going back: {str(e)}"

def media_stop() -> str:
    """Stop media playback."""
    print(f"\n[SYSTEM] Stopping playback...")
    try:
        result = mcp_client.call_tool("media_control", {"action": "stop"})
        return result
    except Exception as e:
        return f"Error stopping: {str(e)}"

def toggle_dark_mode(enabled: bool) -> str:
    """Toggle dark mode on or off."""
    print(f"\n[SYSTEM] {'Enabling' if enabled else 'Disabling'} dark mode...")
    try:
        result = mcp_client.call_tool("quick_settings", {
            "setting": "dark_style",
            "enabled": enabled
        })
        return result
    except Exception as e:
        return f"Error toggling dark mode: {str(e)}"

def toggle_night_light(enabled: bool) -> str:
    """Toggle night light on or off."""
    print(f"\n[SYSTEM] {'Enabling' if enabled else 'Disabling'} night light...")
    try:
        result = mcp_client.call_tool("quick_settings", {
            "setting": "night_light",
            "enabled": enabled
        })
        return result
    except Exception as e:
        return f"Error toggling night light: {str(e)}"

def toggle_do_not_disturb(enabled: bool) -> str:
    """Toggle Do Not Disturb on or off."""
    print(f"\n[SYSTEM] {'Enabling' if enabled else 'Disabling'} Do Not Disturb...")
    try:
        result = mcp_client.call_tool("quick_settings", {
            "setting": "do_not_disturb",
            "enabled": enabled
        })
        return result
    except Exception as e:
        return f"Error toggling Do Not Disturb: {str(e)}"

def toggle_wifi(enabled: bool) -> str:
    """Toggle WiFi on or off."""
    print(f"\n[SYSTEM] {'Enabling' if enabled else 'Disabling'} WiFi...")
    try:
        result = mcp_client.call_tool("quick_settings", {
            "setting": "wifi",
            "enabled": enabled
        })
        return result
    except Exception as e:
        return f"Error toggling WiFi: {str(e)}"

def toggle_bluetooth(enabled: bool) -> str:
    """Toggle Bluetooth on or off."""
    print(f"\n[SYSTEM] {'Enabling' if enabled else 'Disabling'} Bluetooth...")
    try:
        result = mcp_client.call_tool("quick_settings", {
            "setting": "bluetooth",
            "enabled": enabled
        })
        return result
    except Exception as e:
        return f"Error toggling Bluetooth: {str(e)}"

def open_file(path: str, search_location: str = "") -> str:
    """Smart file opener - opens by path or searches first."""
    print(f"\n[SYSTEM] Opening: {path}" + (f" in {search_location}" if search_location else "") + "...")
    try:
        result = mcp_client.call_tool("open_file", {
            "path": path,
            "search_location": search_location
        })
        return result
    except Exception as e:
        return f"Error opening: {str(e)}"

def open_url(url: str) -> str:
    """Open a URL in the default browser."""
    print(f"\n[SYSTEM] Opening URL: {url}...")
    try:
        result = mcp_client.call_tool("open_url", {"url": url})
        return result
    except Exception as e:
        return f"Error opening URL: {str(e)}"

def search_files(query: str, file_type: str = "files", limit: int = 10) -> str:
    """Search for files using GNOME file indexing."""
    print(f"\n[SYSTEM] Searching for '{query}' ({file_type})...")
    try:
        result = mcp_client.call_tool("search_files", {
            "query": query,
            "file_type": file_type,
            "limit": limit
        })
        return result
    except Exception as e:
        return f"Error searching: {str(e)}"

def set_wallpaper(image_path: str) -> str:
    """Set desktop wallpaper/background image."""
    print(f"\n[SYSTEM] Setting wallpaper: {image_path}...")
    try:
        result = mcp_client.call_tool("set_wallpaper", {"image_path": image_path})
        return result
    except Exception as e:
        return f"Error setting wallpaper: {str(e)}"

def maximize_window_by_name(window_name: str = "") -> str:
    """Toggle maximize/restore for a window. If empty, maximizes the currently focused window."""
    if window_name:
        print(f"\n[SYSTEM] Toggling maximize for window: {window_name}...")
    else:
        print(f"\n[SYSTEM] Toggling maximize for current window...")
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

        # Toggle: if maximized, restore; if not, maximize
        if is_maximized:
            result = mcp_client.call_tool("unmaximize_window", {"window_id": window_id})
            return f"Restored {get_friendly_app_name(wm_class)}"
        else:
            result = mcp_client.call_tool("maximize_window", {"window_id": window_id})
            return f"Maximized {get_friendly_app_name(wm_class)}"
    except Exception as e:
        return f"Error toggling window maximize: {str(e)}"

def minimize_window_by_name(window_name: str = "") -> str:
    """Minimize a window by its title or application name. If empty, minimizes the currently focused window."""
    if window_name:
        print(f"\n[SYSTEM] Minimizing window: {window_name}...")
    else:
        print(f"\n[SYSTEM] Minimizing current window...")
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
    """
    Restore a window to normal state. Handles both minimized and maximized windows.
    If empty, restores the currently focused window.

    Note: Always attempts to unminimize first since GNOME Shell doesn't reliably
    report minimized state in the window list. Then checks for maximized state.
    Also focuses the window to bring it to the front.
    """
    if window_name:
        print(f"\n[SYSTEM] Restoring window: {window_name}...")
    else:
        print(f"\n[SYSTEM] Restoring current window...")
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

        actions_taken = []

        # Always try to unminimize first (minimized state isn't reliably reported)
        result = mcp_client.call_tool("unminimize_window", {"window_id": window_id})
        if "unminimized" in result.lower() or "restored" in result.lower():
            actions_taken.append("unminimized")
            print(f"[SYSTEM] Unminimized window")

        # Focus the window to bring it to front (critical for minimized windows)
        mcp_client.call_tool("focus_window", {"window_id": window_id})
        print(f"[SYSTEM] Focused window")

        # Then check and restore from maximized state
        if is_maximized:
            result = mcp_client.call_tool("unmaximize_window", {"window_id": window_id})
            actions_taken.append("unmaximized")
            print(f"[SYSTEM] Unmaximized window")

        if not actions_taken:
            # Try unmaximize anyway in case state detection failed
            result = mcp_client.call_tool("unmaximize_window", {"window_id": window_id})
            if "unmaximized" in result.lower() or "restored" in result.lower():
                actions_taken.append("unmaximized")

        if actions_taken:
            action_desc = " and ".join(actions_taken)
            return f"Restored {get_friendly_app_name(wm_class)} ({action_desc})"
        else:
            return f"Restored {get_friendly_app_name(wm_class)}"
    except Exception as e:
        return f"Error restoring window: {str(e)}"

def screenshot_window_by_name(window_name: str = "", include_frame: bool = True) -> str:
    """Take a screenshot of a specific window. If empty, screenshots the currently focused window."""
    if window_name:
        print(f"\n[SYSTEM] Taking screenshot of window: {window_name}...")
    else:
        print(f"\n[SYSTEM] Taking screenshot of current window...")
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
        return f"Screenshot of {get_friendly_app_name(wm_class)} saved to {screenshot_path}"
    except Exception as e:
        return f"Error taking window screenshot: {str(e)}"

def screenshot_area(x: int, y: int, width: int, height: int) -> str:
    """Take a screenshot of a specific rectangular area of the screen."""
    print(f"\n[SYSTEM] Taking screenshot of area ({x}, {y}) size {width}x{height}...")
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
        return f"Area screenshot ({width}x{height}) saved to {screenshot_path}"
    except Exception as e:
        return f"Error taking area screenshot: {str(e)}"

def move_resize_window_by_name(window_name: str = "", x: int = 0, y: int = 0, width: int = 800, height: int = 600) -> str:
    """
    Move and resize a window to specific position and size.
    If empty window_name, moves/resizes the currently focused window.

    Note: Unmaximizes the window first if needed.
    Common screen resolution is 1920x1080.
    """
    if window_name:
        print(f"\n[SYSTEM] Moving and resizing window: {window_name}...")
    else:
        print(f"\n[SYSTEM] Moving and resizing current window...")

    print(f"[SYSTEM] Position: ({x}, {y}), Size: {width}x{height}")

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

        result = mcp_client.call_tool("move_resize_window", {
            "window_id": window_id,
            "x": x,
            "y": y,
            "width": width,
            "height": height
        })

        if result.startswith("Error"):
            return result

        return f"Moved {get_friendly_app_name(wm_class)} to ({x}, {y}) with size {width}x{height}"
    except Exception as e:
        return f"Error moving/resizing window: {str(e)}"

def scroll_page(direction: str = "down", amount: int = 1) -> str:
    """
    Scroll a page with automatic fallback to multiple methods.

    Tries in order:
    1. Mouse scroll (most reliable for precise control)
    2. PageDown/PageUp keys (works when mouse scroll fails)
    3. Arrow keys (universal fallback)

    Parameters:
    - direction: "up" or "down"
    - amount: Number of times to scroll (for repeated scrolling)
    """
    print(f"\n[SYSTEM] Scrolling {direction} (amount: {amount})...")

    direction_lower = direction.lower()
    is_down = "down" in direction_lower

    # Method 1: Try mouse scroll first
    print(f"[SYSTEM] Trying mouse scroll...")
    try:
        dy = 100 * amount if is_down else -100 * amount
        result = mcp_client.call_tool("mouse_scroll", {
            "x": 960,
            "y": 540,
            "dx": 0,
            "dy": dy
        })

        if not result.startswith("Error"):
            print(f"[SYSTEM] ✅ Mouse scroll succeeded")
            return f"Scrolled {direction}"
        else:
            print(f"[SYSTEM] ⚠️ Mouse scroll failed: {result}")
    except Exception as e:
        print(f"[SYSTEM] ⚠️ Mouse scroll error: {e}")

    # Method 2: Fall back to PageDown/PageUp
    print(f"[SYSTEM] Falling back to Page keys...")
    try:
        key = "Page_Down" if is_down else "Page_Up"
        for i in range(amount):
            result = mcp_client.call_tool("key_combo", {"keys": key})
            if i < amount - 1:
                time.sleep(0.1)  # Small delay between repeated presses

        if not result.startswith("Error"):
            print(f"[SYSTEM] ✅ Page key succeeded")
            return f"Scrolled {direction} using {key}"
        else:
            print(f"[SYSTEM] ⚠️ Page key failed: {result}")
    except Exception as e:
        print(f"[SYSTEM] ⚠️ Page key error: {e}")

    # Method 3: Ultimate fallback - arrow keys
    print(f"[SYSTEM] Falling back to arrow keys...")
    try:
        key = "Down" if is_down else "Up"
        # Arrow keys scroll less, so multiply by 3
        presses = amount * 3
        for i in range(presses):
            result = mcp_client.call_tool("key_combo", {"keys": key})
            if i < presses - 1:
                time.sleep(0.05)

        print(f"[SYSTEM] ✅ Arrow keys succeeded")
        return f"Scrolled {direction} using arrow keys"
    except Exception as e:
        print(f"[SYSTEM] ❌ All scroll methods failed")
        return f"Error: Could not scroll - {str(e)}"

def list_workspaces() -> str:
    """List all virtual desktops/workspaces."""
    print(f"\n[SYSTEM] Listing workspaces...")
    try:
        result = mcp_client.call_tool("list_workspaces", {})

        if result.startswith("Error"):
            return result

        # Parse JSON to provide friendly output
        try:
            workspaces = json.loads(result)
            if not workspaces:
                return "No workspaces found"

            active_workspace = None
            workspace_info = []

            for ws in workspaces:
                index = ws.get('index', 0)
                is_active = ws.get('active', False)

                if is_active:
                    active_workspace = index
                    workspace_info.append(f"Workspace {index} (current)")
                else:
                    workspace_info.append(f"Workspace {index}")

            total = len(workspaces)
            summary = f"You have {total} workspace{'s' if total > 1 else ''}. Current: workspace {active_workspace}. " + ", ".join(workspace_info)
            return summary

        except json.JSONDecodeError:
            # If JSON parsing fails, return raw result
            return result

    except Exception as e:
        return f"Error listing workspaces: {str(e)}"

def activate_workspace(index: int) -> str:
    """Switch to a specific workspace by index (0-based)."""
    print(f"\n[SYSTEM] Switching to workspace {index}...")
    try:
        result = mcp_client.call_tool("activate_workspace", {"index": index})

        if result.startswith("Error"):
            return result

        return f"Switched to workspace {index}"
    except Exception as e:
        return f"Error switching workspace: {str(e)}"

def parse_position(position: str, screen_width: int = 1920, screen_height: int = 1080) -> tuple:
    """
    Convert natural language position to screen coordinates.

    Positions:
    - "left" / "left side" -> (100, center_y)
    - "right" / "right side" -> (1820, center_y)
    - "center" / "middle" -> (960, 540)
    - "top" / "top center" -> (960, 100)
    - "bottom" / "bottom center" -> (960, 980)
    - "top left" -> (100, 100)
    - "top right" -> (1820, 100)
    - "bottom left" -> (100, 980)
    - "bottom right" -> (1820, 980)
    """
    position_lower = position.lower()
    center_x = screen_width // 2
    center_y = screen_height // 2
    left_x = 100
    right_x = screen_width - 100
    top_y = 100
    bottom_y = screen_height - 100

    # Top positions
    if "top left" in position_lower:
        return (left_x, top_y)
    elif "top right" in position_lower:
        return (right_x, top_y)
    elif "top" in position_lower:
        return (center_x, top_y)

    # Bottom positions
    elif "bottom left" in position_lower:
        return (left_x, bottom_y)
    elif "bottom right" in position_lower:
        return (right_x, bottom_y)
    elif "bottom" in position_lower:
        return (center_x, bottom_y)

    # Left/Right positions
    elif "left" in position_lower:
        return (left_x, center_y)
    elif "right" in position_lower:
        return (right_x, center_y)

    # Center
    elif "center" in position_lower or "middle" in position_lower:
        return (center_x, center_y)

    # Default to center if unrecognized
    else:
        print(f"[SYSTEM] ⚠️ Unrecognized position '{position}', using center")
        return (center_x, center_y)

def drag_item(from_position: str = "center", to_position: str = "center",
              from_x: int = None, from_y: int = None,
              to_x: int = None, to_y: int = None) -> str:
    """
    Drag from one position to another using natural language or exact coordinates.

    Can use either:
    - Natural positions: "left side", "right side", "center", "top", "bottom", etc.
    - Exact coordinates: from_x, from_y, to_x, to_y

    Examples:
    - drag_item(from_position="left", to_position="right")
    - drag_item(from_x=100, from_y=200, to_x=500, to_y=600)
    """
    # Determine start position
    if from_x is not None and from_y is not None:
        x1, y1 = from_x, from_y
        print(f"[SYSTEM] Drag from exact coordinates: ({x1}, {y1})")
    else:
        x1, y1 = parse_position(from_position)
        print(f"[SYSTEM] Drag from '{from_position}' -> ({x1}, {y1})")

    # Determine end position
    if to_x is not None and to_y is not None:
        x2, y2 = to_x, to_y
        print(f"[SYSTEM] Drag to exact coordinates: ({x2}, {y2})")
    else:
        x2, y2 = parse_position(to_position)
        print(f"[SYSTEM] Drag to '{to_position}' -> ({x2}, {y2})")

    try:
        result = mcp_client.call_tool("mouse_drag", {
            "x1": x1,
            "y1": y1,
            "x2": x2,
            "y2": y2,
            "button": 1  # Left mouse button
        })

        if result.startswith("Error"):
            return result

        return f"Dragged from ({x1}, {y1}) to ({x2}, {y2})"
    except Exception as e:
        return f"Error dragging: {str(e)}"

# Available tools (custom wrappers)
available_tools = {
    "describe_desktop": describe_desktop,
    "list_installed_applications": list_installed_applications,
    "list_open_windows": list_open_windows,
    "focus_window_by_name": focus_window_by_name,
    "close_window_by_name": close_window_by_name,
    "maximize_window_by_name": maximize_window_by_name,
    "minimize_window_by_name": minimize_window_by_name,
    "restore_window_by_name": restore_window_by_name,
    "screenshot_window_by_name": screenshot_window_by_name,
    "screenshot_area": screenshot_area,
    "move_resize_window_by_name": move_resize_window_by_name,
    "scroll_page": scroll_page,
    "list_workspaces": list_workspaces,
    "activate_workspace": activate_workspace,
    "drag_item": drag_item,
    "type_text_in_window": type_text_in_window,
    "press_key_combo": press_key_combo,
    "set_volume": set_volume,
    "mute_volume": mute_volume,
    "unmute_volume": unmute_volume,
    "media_play": media_play,
    "media_pause": media_pause,
    "media_play_pause": media_play_pause,
    "media_next": media_next,
    "media_previous": media_previous,
    "media_stop": media_stop,
    "toggle_dark_mode": toggle_dark_mode,
    "toggle_night_light": toggle_night_light,
    "toggle_do_not_disturb": toggle_do_not_disturb,
    "toggle_wifi": toggle_wifi,
    "toggle_bluetooth": toggle_bluetooth,
    "set_wallpaper": set_wallpaper,
}

# Direct MCP tools (forwarded directly without wrappers)
direct_mcp_tools = [
    "gnome_search",      # GNOME search overlay - find and open apps/files/settings
    "key_press",         # Press single key - simple passthrough
    "mouse_click",       # Click at screen coordinates - simple passthrough
    "mouse_double_click", # Double-click at screen coordinates - simple passthrough
    "pick_color",        # Get RGB color at coordinates - simple passthrough
    "get_monitors",      # List all monitors - simple passthrough
    "ping",              # Check if extension is alive - health check
    "get_enabled",       # Check if automation is enabled - health check
    "set_enabled",       # Enable/disable automation - management
    "send_notification", # Send desktop notification - user feedback
    "cleanup_screenshots", # Clean up temp screenshot files - maintenance
]

# ----------------------------------------
# Namespace Organization + Semantic Retrieval
# ----------------------------------------

# Define tool namespaces with semantic descriptions
# Each namespace groups related tools with a description used for retrieval
namespaces = {
    "search": {
        "description": "Launch applications, start programs, open files, navigate to websites. Commands like: open firefox, open text editor, start calculator, launch terminal, run files app. Open documents: open screenshot.png, open document.pdf, find image.jpg. Web navigation: go to amazon.com, visit github.com, browse seznam.cz, open google.com. Settings: open wifi settings, bluetooth settings. Use GNOME search to find and launch anything.",
        "tools": ["gnome_search"]
    },
    "window": {
        "description": "Managing already running windows - maximize, minimize, close, focus, move, resize, restore existing application windows. List what windows are currently running. NOT for launching new applications.",
        "tools": ["list_open_windows", "focus_window_by_name", "close_window_by_name",
                  "maximize_window_by_name", "minimize_window_by_name", "restore_window_by_name",
                  "screenshot_window_by_name", "screenshot_area", "move_resize_window_by_name"]
    },
    "workspace": {
        "description": "Virtual desktops, workspace switching, multi-desktop management",
        "tools": ["list_workspaces", "activate_workspace"]
    },
    "input": {
        "description": "Keyboard input, typing text, pressing keys, key combinations, shortcuts, mouse clicks, dragging, scrolling",
        "tools": ["type_text_in_window", "press_key_combo", "key_press", "mouse_click",
                  "mouse_double_click", "drag_item", "scroll_page"]
    },
    "volume": {
        "description": "Sound volume control, mute, unmute, audio levels, speaker settings",
        "tools": ["set_volume", "mute_volume", "unmute_volume"]
    },
    "media": {
        "description": "Media playback control - play, pause, stop, next track, previous track, music control, audio player control",
        "tools": ["media_play", "media_pause", "media_play_pause", "media_next", "media_previous", "media_stop"]
    },
    "settings": {
        "description": "System settings - dark mode, light mode, night light, notifications, do not disturb, WiFi, Bluetooth, wallpaper, background image, quick settings toggles",
        "tools": ["toggle_dark_mode", "toggle_night_light", "toggle_do_not_disturb",
                  "toggle_wifi", "toggle_bluetooth", "set_wallpaper"]
    },
    "vision": {
        "description": "Analyzing current screen content, describing what's visible on desktop right now, color picking from display, monitor configuration. Not for opening files.",
        "tools": ["describe_desktop", "pick_color", "get_monitors"]
    },
    "system": {
        "description": "System automation control, notifications, reminders, timers, cleanup, maintenance",
        "tools": ["set_enabled", "send_notification", "cleanup_screenshots"]
    }
}

# Load embedding model for semantic retrieval (offline mode set at import time)
print("[SYSTEM] Loading embedding model for tool retrieval...")
embedding_model = SentenceTransformer('all-MiniLM-L6-v2', device='cpu')  # Uses cached model only

# Pre-compute namespace embeddings
namespace_names = list(namespaces.keys())
namespace_descriptions = [namespaces[ns]["description"] for ns in namespace_names]
namespace_embeddings = embedding_model.encode(namespace_descriptions, convert_to_tensor=True)
print(f"[SYSTEM] ✓ Loaded embeddings for {len(namespace_names)} namespaces")

def retrieve_relevant_namespaces(user_input: str, top_k: int = 3) -> list:
    """
    Retrieve most relevant namespaces for a user input using semantic similarity.

    Args:
        user_input: The user's command/query
        top_k: Number of top namespaces to retrieve (default 3)

    Returns:
        List of namespace names sorted by relevance
    """
    # Encode user input
    from sentence_transformers.util import cos_sim
    query_embedding = embedding_model.encode(user_input, convert_to_tensor=True)

    # Compute cosine similarity
    similarities = cos_sim(query_embedding, namespace_embeddings)[0]

    # Get top-k indices
    top_indices = similarities.argsort(descending=True)[:top_k]

    # Return namespace names
    relevant_namespaces = [namespace_names[i] for i in top_indices]

    # Debug logging
    print(f"[RETRIEVAL] Query: '{user_input}'")
    for i, ns in enumerate(relevant_namespaces):
        score = similarities[namespace_names.index(ns)].item()
        print(f"  {i+1}. {ns} (score: {score:.3f}) - {len(namespaces[ns]['tools'])} tools")

    return relevant_namespaces

def build_filtered_tool_schema(relevant_namespaces: list) -> list:
    """
    Build a filtered tool schema containing only tools from relevant namespaces.

    Args:
        relevant_namespaces: List of namespace names to include

    Returns:
        Filtered tool_schema list with only relevant tools
    """
    # Collect all tool names from relevant namespaces
    relevant_tool_names = set()
    for ns in relevant_namespaces:
        relevant_tool_names.update(namespaces[ns]["tools"])

    # Filter tool_schema (will be defined below)
    # We'll use a mapping from tool name to tool definition
    filtered_schema = [tool for tool in tool_schema_full
                      if tool["function"]["name"] in relevant_tool_names]

    print(f"[FILTER] Showing {len(filtered_schema)} tools from {len(relevant_namespaces)} namespaces")
    print(f"  Tools: {[t['function']['name'] for t in filtered_schema]}")

    return filtered_schema

# Full tool schema (all 43 tools)
# This will be filtered dynamically based on user input
tool_schema_full = [
{"type": "function", "function": {"name": "gnome_search", "description": "Use GNOME search to find and open apps, files, or settings. Opens Activities search, types the query, and presses Enter. GNOME finds and opens the best match automatically. Extract just the app name, file name, or domain from user input.", "parameters": {"type": "object", "properties": {"query": {"type": "string", "description": "Just the app name, file name, or domain. Examples: 'firefox', 'text editor', 'screenshot.png', 'amazon.com', 'wifi'"}}, "required": ["query"]}}},
{"type": "function", "function": {"name": "describe_desktop", "description": "Captures a screenshot of the desktop and describes what is visible using AI vision.", "parameters": {"type": "object", "properties": {}}}},
{"type": "function", "function": {"name": "list_installed_applications", "description": "Lists all installed GUI applications available on the Linux system. Use for 'what apps are installed', 'list all applications', 'show me installed programs'.", "parameters": {"type": "object", "properties": {}}}},
{"type": "function", "function": {"name": "list_open_windows", "description": "Lists all currently open windows on the desktop.", "parameters": {"type": "object", "properties": {}}}},
{"type": "function", "function": {"name": "focus_window_by_name", "description": "Focus and bring to front a window. Can match by application name (e.g. 'text editor', 'firefox'). If window_name is empty, focuses the current window.", "parameters": {"type": "object", "properties": {"window_name": {"type": "string", "description": "Application name or part of window title (e.g., 'text editor', 'firefox'). Leave empty to use current window.", "default": ""}}, "required": []}}},
{"type": "function", "function": {"name": "close_window_by_name", "description": "Safely close a window. Matches by application name (e.g., 'text editor'). If window_name is empty, closes the current window. If unsaved changes exist, asks user via voice what to do (Save, Discard, Cancel).", "parameters": {"type": "object", "properties": {"window_name": {"type": "string", "description": "Application name or part of window title (e.g., 'text editor', 'firefox'). Leave empty to use current window.", "default": ""}}, "required": []}}},
{"type": "function", "function": {"name": "type_text_in_window", "description": "Type text into the currently focused window.", "parameters": {"type": "object", "properties": {"text": {"type": "string", "description": "The text to type"}}, "required": ["text"]}}},
{"type": "function", "function": {"name": "press_key_combo", "description": "Press a keyboard combination like Ctrl+C, Alt+Tab, Super+l, etc.", "parameters": {"type": "object", "properties": {"keys": {"type": "string", "description": "Key combination like 'Ctrl+c', 'Alt+Tab', 'Super+l'"}}, "required": ["keys"]}}},
{"type": "function", "function": {"name": "set_volume", "description": "Set system volume level. Can set absolute volume (0-100) or relative change (+/- from current). Examples: 'set volume to 50', 'increase volume by 10', 'decrease volume by 20', 'turn volume to 75'.", "parameters": {"type": "object", "properties": {"level": {"type": "integer", "description": "Volume level: 0-100 for absolute, or -100 to 100 for relative change"}, "relative": {"type": "boolean", "description": "If true, level is a relative change (+/-). If false, level is absolute (0-100).", "default": False}}, "required": ["level"]}}},
{"type": "function", "function": {"name": "mute_volume", "description": "Mute the system volume. Use for 'mute', 'mute volume', 'silence', 'turn off sound'.", "parameters": {"type": "object", "properties": {}, "required": []}}},
{"type": "function", "function": {"name": "unmute_volume", "description": "Unmute the system volume. Use for 'unmute', 'unmute volume', 'turn on sound', 'restore sound'.", "parameters": {"type": "object", "properties": {}, "required": []}}},
{"type": "function", "function": {"name": "media_play", "description": "Start playing media (music, audio). Use for 'play', 'start playing', 'play music', 'play track', 'resume'.", "parameters": {"type": "object", "properties": {}, "required": []}}},
{"type": "function", "function": {"name": "media_pause", "description": "Pause media playback. Use for 'pause', 'pause music', 'pause track', 'pause playback'.", "parameters": {"type": "object", "properties": {}, "required": []}}},
{"type": "function", "function": {"name": "media_play_pause", "description": "Toggle between play and pause. Use for 'play pause', 'toggle playback', 'playtrack' (interpreted as play/pause toggle).", "parameters": {"type": "object", "properties": {}, "required": []}}},
{"type": "function", "function": {"name": "media_next", "description": "Skip to the next track/song. Use for 'next track', 'next song', 'skip', 'skip track', 'next'.", "parameters": {"type": "object", "properties": {}, "required": []}}},
{"type": "function", "function": {"name": "media_previous", "description": "Go back to the previous track/song. Use for 'previous track', 'previous song', 'previous', 'go back', 'last track'.", "parameters": {"type": "object", "properties": {}, "required": []}}},
{"type": "function", "function": {"name": "media_stop", "description": "Stop media playback completely. Use for 'stop', 'stop music', 'stop playback', 'stop track'.", "parameters": {"type": "object", "properties": {}, "required": []}}},
{"type": "function", "function": {"name": "toggle_dark_mode", "description": "Enable or disable dark mode theme. Use for 'turn on dark mode', 'turn off dark mode', 'enable dark mode', 'disable dark mode', 'switch to dark mode', 'switch to light mode'.", "parameters": {"type": "object", "properties": {"enabled": {"type": "boolean", "description": "true to enable dark mode, false to switch to light mode"}}, "required": ["enabled"]}}},
{"type": "function", "function": {"name": "toggle_night_light", "description": "Enable or disable night light (warm screen color temperature). Use for 'turn on night light', 'turn off night light', 'enable night light', 'disable night light'.", "parameters": {"type": "object", "properties": {"enabled": {"type": "boolean", "description": "true to enable night light, false to disable"}}, "required": ["enabled"]}}},
{"type": "function", "function": {"name": "toggle_do_not_disturb", "description": "Enable or disable Do Not Disturb mode (blocks notifications). Use for 'turn on do not disturb', 'turn off do not disturb', 'enable DND', 'disable DND', 'silence notifications', 'allow notifications'.", "parameters": {"type": "object", "properties": {"enabled": {"type": "boolean", "description": "true to enable DND (block notifications), false to disable DND (allow notifications)"}}, "required": ["enabled"]}}},
{"type": "function", "function": {"name": "toggle_wifi", "description": "Enable or disable WiFi. Use for 'turn on wifi', 'turn off wifi', 'enable wifi', 'disable wifi', 'wifi on', 'wifi off'.", "parameters": {"type": "object", "properties": {"enabled": {"type": "boolean", "description": "true to enable WiFi, false to disable"}}, "required": ["enabled"]}}},
{"type": "function", "function": {"name": "toggle_bluetooth", "description": "Enable or disable Bluetooth. Use for 'turn on bluetooth', 'turn off bluetooth', 'enable bluetooth', 'disable bluetooth', 'bluetooth on', 'bluetooth off'.", "parameters": {"type": "object", "properties": {"enabled": {"type": "boolean", "description": "true to enable Bluetooth, false to disable"}}, "required": ["enabled"]}}},
{"type": "function", "function": {"name": "set_wallpaper", "description": "Set desktop wallpaper/background image. Smart search: use color names (red, blue, green, orange, purple, gray, black) OR wallpaper names (fedora, adwaita, amber) OR file paths. Use for 'change background to red', 'set wallpaper blue', 'change wallpaper to fedora', 'set wallpaper ~/Pictures/sunset.jpg'.", "parameters": {"type": "object", "properties": {"image_path": {"type": "string", "description": "Color name (red, blue, green), wallpaper name (fedora, amber), or file path (/home/user/Pictures/photo.jpg, ~/Pictures/sunset.png)"}}, "required": ["image_path"]}}},
{"type": "function", "function": {"name": "maximize_window_by_name", "description": "Toggle maximize/restore for a window. Matches by application name (e.g., 'text editor'). If window_name is empty, uses the current window. If already maximized, restores to original size. If not maximized, makes it full-screen.", "parameters": {"type": "object", "properties": {"window_name": {"type": "string", "description": "Application name (e.g., 'text editor', 'firefox'). Leave empty to use current window.", "default": ""}}, "required": []}}},
{"type": "function", "function": {"name": "minimize_window_by_name", "description": "Minimize (hide) a window. Matches by application name (e.g., 'text editor'). If window_name is empty, uses the current window.", "parameters": {"type": "object", "properties": {"window_name": {"type": "string", "description": "Application name (e.g., 'text editor', 'firefox'). Leave empty to use current window.", "default": ""}}, "required": []}}},
{"type": "function", "function": {"name": "restore_window_by_name", "description": "Restore a window to normal state. Works for both minimized and maximized windows - brings them back to regular size and visibility. Matches by application name (e.g., 'text editor'). If window_name is empty, uses the current window.", "parameters": {"type": "object", "properties": {"window_name": {"type": "string", "description": "Application name (e.g., 'text editor', 'firefox'). Leave empty to use current window.", "default": ""}}, "required": []}}},
{"type": "function", "function": {"name": "screenshot_window_by_name", "description": "Take a screenshot of a specific window only (not the whole desktop). Matches by application name (e.g., 'text editor', 'firefox'). If window_name is empty, screenshots the current window.", "parameters": {"type": "object", "properties": {"window_name": {"type": "string", "description": "Application name (e.g., 'text editor', 'firefox'). Leave empty to use current window.", "default": ""}, "include_frame": {"type": "boolean", "description": "Whether to include window decorations/borders", "default": True}}, "required": []}}},
{"type": "function", "function": {"name": "screenshot_area", "description": "Take a screenshot of a specific rectangular region of the screen. Useful for capturing just a portion of the screen (e.g., top-left corner, center region, etc.).", "parameters": {"type": "object", "properties": {"x": {"type": "integer", "description": "Left edge in pixels (0 = left edge of screen)"}, "y": {"type": "integer", "description": "Top edge in pixels (0 = top edge of screen)"}, "width": {"type": "integer", "description": "Width in pixels"}, "height": {"type": "integer", "description": "Height in pixels"}}, "required": ["x", "y", "width", "height"]}}},
{"type": "function", "function": {"name": "move_resize_window_by_name", "description": "Move and resize a window to a specific position and size. If window_name is empty, moves/resizes the current window. Unmaximizes first if needed. Common use cases: left half (x=0, y=0, width=960, height=1080), right half (x=960, y=0, width=960, height=1080) on 1920x1080 screen.", "parameters": {"type": "object", "properties": {"window_name": {"type": "string", "description": "Application name (e.g., 'text editor', 'firefox'). Leave empty to use current window.", "default": ""}, "x": {"type": "integer", "description": "X position in pixels (0 = left edge)", "default": 0}, "y": {"type": "integer", "description": "Y position in pixels (0 = top edge)", "default": 0}, "width": {"type": "integer", "description": "Width in pixels", "default": 800}, "height": {"type": "integer", "description": "Height in pixels", "default": 600}}, "required": []}}},
{"type": "function", "function": {"name": "scroll_page", "description": "Scroll web pages, documents, or any scrollable content up or down. Automatically tries multiple methods (mouse scroll, Page keys, arrow keys) for maximum reliability. Use this for 'scroll down', 'scroll up', 'scroll down 3 times', etc.", "parameters": {"type": "object", "properties": {"direction": {"type": "string", "description": "Direction to scroll: 'up' or 'down'", "default": "down"}, "amount": {"type": "integer", "description": "Number of times to scroll (for repeated scrolling)", "default": 1}}, "required": []}}},
{"type": "function", "function": {"name": "list_workspaces", "description": "List all virtual desktops/workspaces. Shows which workspace is currently active and total count. Use for 'list workspaces', 'how many workspaces', 'which workspace am I on'.", "parameters": {"type": "object", "properties": {}}}},
{"type": "function", "function": {"name": "activate_workspace", "description": "Switch to a specific workspace/virtual desktop by index. Workspace numbering typically starts at 0. Use for 'switch to workspace 2', 'go to workspace 1'.", "parameters": {"type": "object", "properties": {"index": {"type": "integer", "description": "Workspace index to switch to (0-based, so workspace 1 is index 0, workspace 2 is index 1, etc.)"}}, "required": ["index"]}}},
{"type": "function", "function": {"name": "drag_item", "description": "Drag from one position to another. Supports natural language positions like 'left side', 'right side', 'center', 'top', 'bottom', 'top left', 'bottom right', etc. OR exact coordinates. Use for 'drag from left to right', 'drag from center to bottom', 'drag app from left side to right side'. Can also drag files, windows, icons.", "parameters": {"type": "object", "properties": {"from_position": {"type": "string", "description": "Start position: 'left', 'right', 'center', 'top', 'bottom', 'top left', 'top right', 'bottom left', 'bottom right'", "default": "center"}, "to_position": {"type": "string", "description": "End position: 'left', 'right', 'center', 'top', 'bottom', 'top left', 'top right', 'bottom left', 'bottom right'", "default": "center"}, "from_x": {"type": "integer", "description": "Optional: exact start X coordinate (overrides from_position)"}, "from_y": {"type": "integer", "description": "Optional: exact start Y coordinate (overrides from_position)"}, "to_x": {"type": "integer", "description": "Optional: exact end X coordinate (overrides to_position)"}, "to_y": {"type": "integer", "description": "Optional: exact end Y coordinate (overrides to_position)"}}, "required": []}}},
{"type": "function", "function": {"name": "key_press", "description": "Press and release a single key like Return, Escape, F5, Tab, etc.", "parameters": {"type": "object", "properties": {"key": {"type": "string", "description": "Key name like 'Return', 'Escape', 'F5', 'Tab', 'a', 'Space'"}}, "required": ["key"]}}},
{"type": "function", "function": {"name": "mouse_click", "description": "Click at specific screen coordinates. Can left-click, right-click, or middle-click. Use with describe_desktop to identify where to click.", "parameters": {"type": "object", "properties": {"x": {"type": "integer", "description": "X coordinate in pixels"}, "y": {"type": "integer", "description": "Y coordinate in pixels"}, "button": {"type": "integer", "description": "Mouse button: 1=left, 2=middle, 3=right", "default": 1}}, "required": ["x", "y"]}}},
{"type": "function", "function": {"name": "mouse_double_click", "description": "Double-click at specific screen coordinates. Opens files, folders, applications. Can left, right, or middle double-click. Use with describe_desktop to find where icons/items are located.", "parameters": {"type": "object", "properties": {"x": {"type": "integer", "description": "X coordinate in pixels"}, "y": {"type": "integer", "description": "Y coordinate in pixels"}, "button": {"type": "integer", "description": "Mouse button: 1=left (default), 2=middle, 3=right", "default": 1}}, "required": ["x", "y"]}}},
{"type": "function", "function": {"name": "pick_color", "description": "Get the RGB color of a pixel at specific screen coordinates. Returns JSON with r, g, b values (0.0-1.0 range). Useful for color picking, design work, accessibility checks. Use with describe_desktop to find coordinates of UI elements.", "parameters": {"type": "object", "properties": {"x": {"type": "integer", "description": "X coordinate in pixels"}, "y": {"type": "integer", "description": "Y coordinate in pixels"}}, "required": ["x", "y"]}}},
{"type": "function", "function": {"name": "get_monitors", "description": "List all connected monitors/displays with their geometry, position, scale factor, and primary status. Returns JSON array with monitor information. Useful for multi-monitor setups, positioning windows on specific screens, understanding screen layout.", "parameters": {"type": "object", "properties": {}, "required": []}}},
{"type": "function", "function": {"name": "set_enabled", "description": "Enable or disable desktop automation. Use for 'enable automation', 'disable automation', 'turn on automation', 'turn off automation'. When disabled, all automation commands will stop working until re-enabled.", "parameters": {"type": "object", "properties": {"enabled": {"type": "boolean", "description": "true to enable automation, false to disable it"}}, "required": ["enabled"]}}},
{"type": "function", "function": {"name": "send_notification", "description": "Send a desktop notification immediately or after a delay. Use for reminders, timers, alerts. Examples: 'remind me in 5 minutes about the meeting', 'notify me in 1 hour to check logs', 'alert me in 30 seconds', 'send notification build complete' (immediate).", "parameters": {"type": "object", "properties": {"summary": {"type": "string", "description": "Notification title/headline (required)"}, "body": {"type": "string", "description": "Notification message body (optional)", "default": ""}, "delay": {"type": "string", "description": "Time delay before sending (optional). Examples: '5 minutes', '1 hour', '30 seconds', '2 hours 30 minutes'. If empty, sends immediately.", "default": ""}}, "required": ["summary"]}}},
{"type": "function", "function": {"name": "cleanup_screenshots", "description": "Remove all temporary screenshot files from /tmp/gnome-mcp to free up disk space. Use for 'clean up screenshots', 'delete temp screenshots', 'free up screenshot space'.", "parameters": {"type": "object", "properties": {}, "required": []}}}
]

# Initially, use all tools (will be filtered dynamically during execution)
tool_schema = tool_schema_full

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
        raise  # Re-raise to exit main loop

def get_installed_gui_apps():
    """Scans Fedora's application directory for installed GUI programs."""
    app_dir = "/usr/share/applications"
    installed_apps = []
    try:
        for filename in os.listdir(app_dir):
            if filename.endswith(".desktop"):
                app_name = filename.replace(".desktop", "")
                if "org.gnome." in app_name:
                    app_name = app_name.replace("org.gnome.", "")
                installed_apps.append(app_name)
    except Exception as e:
        return ["firefox", "gnome-calculator", "nautilus"]
    return installed_apps

live_app_list = get_installed_gui_apps()
print(f"[SYSTEM] Found {len(live_app_list)} installed applications")

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
        response = ollama.chat(
            model=CLASSIFIER_MODEL,
            messages=[{'role': 'user', 'content': classifier_prompt}],
            options={
                'num_predict': 10,
                'temperature': 0.1,
                'num_ctx': 512
            }
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
        response = ollama.chat(
            model=CONVERSATION_MODEL,
            messages=messages,
            options={
                # No num_predict limit - let model stop naturally
                # Prompt already asks for concise responses (3 sentences)
                'temperature': 0.7,
                'num_ctx': 2048
            }
        )

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
    print("💬  CONVERSATIONAL Agentic OS")
    print("="*60)
    print("✅ VAD - unlimited voice input")
    print("✅ Safe close - never loses data without your consent")
    print("✅ Dialog detection - reads options to you")
    print("✅ Voice confirmation - you choose what to do")
    print("⭐ Conversation mode - ask questions, get help")
    print("⭐ Automatic detection - seamlessly switches modes\n")

    print("Mode switching:")
    print("  • 'switch to command mode' - force command mode")
    print("  • 'switch to chat mode' - force conversation mode")
    print("  • 'automatic mode' - auto-detect intent")
    print("  • 'clear history' - clear conversation history\n")

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
        "content": "You are a silent system orchestrator. Your ONLY job is to execute tool calls based on user intent. DO NOT output conversational text. DO NOT confirm actions. DO NOT be polite. If you need to use a tool, output ONLY the tool call. FORGET gedit and USE gnome-text-editor."
    }

    # State variables
    current_mode = None  # None = automatic, 'command' = forced, 'conversation' = forced
    conversation_history = []
    command_messages = [command_system_msg]

    # Notify user that system is ready
    print("[SYSTEM] ✓ Voice orchestrator ready")
    speak("Voice orchestrator ready. Listening for commands.")

    try:
        while True:
            user_input = listen_and_transcribe()
            if not user_input:
                continue

            # Start timing from when user input is captured
            response_start_time = time.time()

            user_input_lower = user_input.lower()

            # Check for explicit mode switching (these don't need timing - just mode control)
            if 'switch to command mode' in user_input_lower or 'command mode' in user_input_lower:
                current_mode = 'command'
                speak("Command mode activated. I'll only execute desktop commands.")
                print(f"[MODE] 🔧 Command mode (forced)")
                continue

            if 'switch to chat mode' in user_input_lower or 'chat mode' in user_input_lower or 'conversation mode' in user_input_lower:
                current_mode = 'conversation'
                speak("Chat mode activated. Ask me anything!")
                print(f"[MODE] 💬 Conversation mode (forced)")
                continue

            if 'automatic mode' in user_input_lower or 'auto detect' in user_input_lower or 'auto mode' in user_input_lower:
                current_mode = None
                speak("Automatic mode. I'll detect whether you want commands or conversation.")
                print(f"[MODE] 🤖 Automatic detection")
                continue

            # Check for history management
            if 'clear history' in user_input_lower or 'new topic' in user_input_lower:
                conversation_history = []
                speak("Conversation history cleared.")
                print(f"[CHAT] 🗑️  History cleared")
                continue

            # Determine intent type
            if current_mode is None:
                # Automatic detection
                intent_type = classify_intent_type(user_input)
                print(f"[MODE] 🤖 Auto-detected: {intent_type}")
            else:
                # Use forced mode
                intent_type = current_mode
                print(f"[MODE] 🔒 Forced: {intent_type}")

            # Route to appropriate handler
            if intent_type == 'command':
                # COMMAND MODE - execute desktop tools
                print(f"[COMMAND] Processing: {user_input}")

                command_messages.append({"role": "user", "content": user_input})

                # Hybrid namespace + retrieval approach
                # Retrieve top 2 most relevant namespaces for this query (faster inference)
                relevant_namespaces = retrieve_relevant_namespaces(user_input, top_k=2)

                # Build filtered tool schema with only relevant tools
                filtered_tools = build_filtered_tool_schema(relevant_namespaces)

                print(f"[TIMING] ⏱️  Calling {COMMAND_MODEL} with {len(filtered_tools)} tools...")
                llm_start_time = time.time()
                response = ollama.chat(
                    model=COMMAND_MODEL,
                    messages=command_messages,
                    tools=filtered_tools,  # Use filtered tools instead of all 43
                    keep_alive=-1,
                    options={
                        'temperature': 0.0,
                        'top_p': 0.1,
                        'num_predict': 200  # Limit tokens - function calls are short (<100 tokens)
                    }
                )
                llm_elapsed = time.time() - llm_start_time
                print(f"[TIMING] ⏱️  LLM inference took: {llm_elapsed:.2f}s")

                # Debug: Check what gemma actually generated
                print(f"[DEBUG] Gemma eval_count: {response.get('eval_count', 'N/A')} tokens")
                print(f"[DEBUG] Response content length: {len(response['message'].get('content', ''))}")
                if response['message'].get('content'):
                    print(f"[DEBUG] Content preview: {response['message']['content'][:200]}")

                message = response['message']
                command_messages.append(message)

                if message.get('tool_calls'):
                    for tool_call in message['tool_calls']:
                        tool_name = tool_call['function']['name']
                        arguments = tool_call['function']['arguments']

                        # Check if it's a direct MCP tool (no wrapper needed)
                        if tool_name in direct_mcp_tools:
                            print(f"\n[SYSTEM] Calling MCP tool directly: {tool_name}")
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

                            print(f"\n[OS Feedback]: {result}")
                            response_time = time.time() - response_start_time
                            print(f"[TIMING] ⏱️  Response time: {response_time:.2f}s")
                            speak(result)
                            command_messages = [command_system_msg]

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

                            print(f"\n[OS Feedback]: {result}")
                            response_time = time.time() - response_start_time
                            print(f"[TIMING] ⏱️  Response time: {response_time:.2f}s")
                            speak(result)
                            command_messages = [command_system_msg]

                        else:
                            print(f"[COMMAND] ⚠️  Unknown tool: {tool_name}")
                            response_time = time.time() - response_start_time
                            print(f"[TIMING] ⏱️  Response time: {response_time:.2f}s")
                            speak(f"I don't know how to use {tool_name}")
                            command_messages = [command_system_msg]
                else:
                    # No tool call generated
                    print("[COMMAND] ⚠️  No tool call generated. Try rephrasing or switch to chat mode.")
                    response_time = time.time() - response_start_time
                    print(f"[TIMING] ⏱️  Response time: {response_time:.2f}s")
                    speak("I'm not sure what command to run. Try rephrasing or say 'switch to chat mode'.")

            else:  # intent_type == 'conversation'
                # CONVERSATION MODE - chat with Gemma
                print(f"[CHAT] Processing: {user_input}")

                answer, conversation_history = handle_conversation(user_input, conversation_history)

                print(f"\n[Agent]: {answer}")
                response_time = time.time() - response_start_time
                print(f"[TIMING] ⏱️  Response time: {response_time:.2f}s")
                speak(answer)

    except KeyboardInterrupt:
        print("\n[SYSTEM] 🛑 Ctrl+C received, shutting down gracefully...")
        # Unload models from memory
        print("[SYSTEM] Unloading AI models...")
        try:
            # Stop all models that might be loaded
            for model in [COMMAND_MODEL, VISION_MODEL, CONVERSATION_MODEL, CLASSIFIER_MODEL]:
                ollama.chat(model=model, messages=[], keep_alive=0)
        except:
            pass  # Ignore errors if models weren't loaded
        print("[SYSTEM] ✓ Models unloaded")
        return

if __name__ == "__main__":
    try:
        run_agent()
    except KeyboardInterrupt:
        print("\n\n[SYSTEM] Shutting down Agentic OS...")
        # Unload models from memory
        print("[SYSTEM] Unloading AI models...")
        try:
            # Stop all models that might be loaded
            for model in [COMMAND_MODEL, VISION_MODEL, CONVERSATION_MODEL, CLASSIFIER_MODEL]:
                ollama.chat(model=model, messages=[], keep_alive=0)
        except:
            pass  # Ignore errors if models weren't loaded
        print("[SYSTEM] ✓ Models unloaded")
