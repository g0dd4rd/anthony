#!/usr/bin/env python3
"""
Voice-Driven Desktop Orchestrator with CONSOLIDATED TOOLS (Facade Pattern)

This version uses the facade pattern to consolidate 34 individual tools into 11 tools:
- 6 facade tools (window_control, input_control, audio_control, system_settings, vision_control, workspace_control)
- 4 standalone tools (list_installed_applications, send_notification, cleanup_screenshots, get_datetime)
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
import shutil, subprocess
import asyncio
import json
import threading
import time
import argparse
from queue import Queue

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
parser.add_argument('--log-dir', type=str, default=None,
                    help='Directory for log files (default: ./logs/)')
args = parser.parse_args()

# Global flags
PUSH_TO_TALK_MODE = args.ptt
RESTART_SERVER = args.restart_server
KILL_SERVER_ON_EXIT = args.kill_server
DEBUG = args.debug

# ========================================
# FILE LOGGING (always active, independent of --debug)
# ========================================
import utils
utils.DEBUG = DEBUG
utils.setup_logging(args.log_dir)
from utils import log_and_print
logger = utils.logger

# ========================================
# 🎯 MODEL CONFIGURATION - LLAMA.CPP SERVER
# ========================================
# Using llama-server with Vulkan GPU acceleration (Intel Arc)
#
# Model: Gemma 4 E4B (8B parameters, Q4_K_M quantized, 5GB)
# Vision: Enabled via mmproj (multimodal projector)
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
    'mmproj': os.path.expanduser('~/models/mmproj-gemma-4-E4B-it-Q8_0.gguf'),
}

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
                    log_and_print(f"[SERVER] Killed llama-server process (PID {pid})")
                except:
                    pass
            # Wait for processes to die
            time.sleep(2)
        return True
    except Exception as e:
        log_and_print(f"[SERVER] Warning: Could not kill server: {e}", level='warning')
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
        '--mmproj', config['mmproj'],
    ]

    log_and_print(f"[SERVER] Starting llama-server on port {config['port']}...")
    log_and_print(f"[SERVER] Model: {config['model']}")
    log_and_print(f"[SERVER] GPU: {config['device']} ({config['gpu_layers']} layers)")

    try:
        # Start in background, detached from parent process
        _server_process = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True  # Detach from parent
        )

        # Wait for server to be ready (max 30 seconds)
        logger.info("[SERVER] Waiting for server to start...")
        print("[SERVER] Waiting for server to start", end='', flush=True)
        for i in range(30):
            time.sleep(1)
            print('.', end='', flush=True)
            if check_server_running():
                log_and_print(" ✓")
                log_and_print("[SERVER] llama-server started successfully!")
                return True

        log_and_print(" ✗")
        log_and_print("[SERVER] ⚠️  Server did not respond within 30 seconds", level='warning')
        return False

    except Exception as e:
        log_and_print(f"\n[SERVER] ❌ Failed to start server: {e}", level='error')
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
        log_and_print("[SERVER] ✓ llama-server already running")
        return True

    # Force restart requested
    if force_restart:
        log_and_print("[SERVER] Restarting llama-server (--restart-server flag)...")
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

        choice = result['choices'][0]
        message = choice['message']

        return {
            'message': {
                'role': message['role'],
                'content': message.get('content', ''),
                'tool_calls': message.get('tool_calls', [])
            },
            'eval_count': result.get('usage', {}).get('completion_tokens', 0)
        }

    except requests.exceptions.RequestException as e:
        log_and_print(f"[ERROR] llama-server request failed: {e}", level='error')
        raise
    except Exception as e:
        log_and_print(f"[ERROR] llama-server error: {e}", level='error')
        raise


# ----------------------------------------
# MCP Client Setup
# ----------------------------------------
class MCPClient:
    """Manages connection to anthony-mcp server"""

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
            command="anthony-mcp",
            args=[],
            env=os.environ.copy()
        )

        async with stdio_client(server_params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                self.session = session
                log_and_print("[SYSTEM] MCP connected to anthony-mcp")

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
log_and_print("[SYSTEM] Initializing dialog handler...")
dialog_handler = DialogHandler()

# Voice I/O loaded from voice_io.py
from voice_io import speak, listen_and_transcribe

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
                log_and_print("[SYSTEM] Automation is disabled. Auto-enabling...")
                enable_result = mcp_client.call_tool("set_enabled", {"enabled": True})
                if "Error" in enable_result:
                    return False, f"Failed to enable automation: {enable_result}"
                log_and_print("[SYSTEM] ✓ Automation enabled successfully")
                return True, "Automation was disabled but has been auto-enabled"
            else:
                return False, "Automation is disabled. Say 'enable automation' to turn it on."

        return True, "Automation is healthy and ready"

    except Exception as e:
        return False, f"Health check failed: {e}"


# ========================================
# APP INDEXING + RAG (loaded from app_index.py)
# ========================================
import app_index
from app_index import (build_app_index, smart_match_window, get_friendly_app_name,
                       get_installed_gui_apps, retrieve_relevant_namespaces,
                       build_filtered_tool_schema)

# Facade tools loaded from tools/facades.py
from tools.facades import (window_control, input_control, audio_control,
                           system_settings, vision_control, workspace_control)

# Standalone tools loaded from tools/standalone.py
from tools.standalone import (get_battery_status, set_brightness, get_power_profile,
                              set_power_profile, lock_screen, power_action, get_datetime,
                              list_installed_applications, send_notification, cleanup_screenshots,
                              search_apps, run_install, run_uninstall, get_app_shortcuts)

# Conversation mode loaded from conversation.py
import conversation
from conversation import classify_intent_type, handle_conversation

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
    "get_datetime": get_datetime,
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
# CONSOLIDATED TOOL SCHEMA (13 tools total)
# ========================================

from config.tool_schemas import TOOL_SCHEMAS
tool_schema_full = TOOL_SCHEMAS
tool_schema = tool_schema_full

log_and_print(f"[SYSTEM] ✓ Consolidated tool schema: {len(tool_schema_full)} tools")

# ========================================
# MODULE INITIALIZATION
# ========================================

# Initialize app_index with tool schema
app_index.init(tool_schema_full)

# Ensure llama-server is running
if not ensure_server_running(force_restart=RESTART_SERVER):
    log_and_print("[SERVER] ❌ Failed to start llama-server. Exiting.")
    sys.exit(1)

# Initialize facades with runtime dependencies
from tools import facades
facades.init(mcp_client, dialog_handler,
             smart_match_window, get_friendly_app_name)

# Initialize standalone tools with runtime dependencies
from tools import standalone
standalone.init(mcp_client, get_installed_gui_apps)

# Initialize conversation module
conversation.init(call_llama_server, debug=DEBUG)

# Log app discovery
live_app_list = get_installed_gui_apps()
log_and_print(f"[SYSTEM] Found {live_app_list['count']} user-visible applications (samples: {', '.join(live_app_list['samples'][:3])})")



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

    logger.info(f"[SYSTEM] Banner displayed (PTT={PUSH_TO_TALK_MODE})")

    log_and_print("[SYSTEM] Starting MCP client...")
    mcp_client.start()

    # Build application index for natural language resolution
    log_and_print("[SYSTEM] Building application index...")
    build_app_index()

    # Health check: ensure automation extension is running and enabled
    log_and_print("[SYSTEM] Checking automation health...")
    health_ok, health_msg = check_automation_health(auto_enable=True)
    if health_ok:
        log_and_print(f"[SYSTEM] ✓ {health_msg}")
    else:
        log_and_print(f"[SYSTEM] ⚠️  {health_msg}", level='warning')
        log_and_print("[SYSTEM] Some features may not work until automation is enabled.", level='warning')

    # Command mode system message
    from config.prompts import COMMAND_SYSTEM_MSG
    command_system_msg = {"role": "system", "content": COMMAND_SYSTEM_MSG}

    # State variables
    current_mode = 'command'  # Start in command mode (explicit switching only)
    conversation_history = []
    command_messages = [command_system_msg]

    # Notify user that system is ready
    log_and_print("[SYSTEM] ✓ Voice orchestrator ready")
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
                    log_and_print("\n[SYSTEM] EOF detected, exiting...")
                    break
                print("\n[PTT] 🟢 Listening activated...")

            user_input = listen_and_transcribe()
            if not user_input:
                if PUSH_TO_TALK_MODE:
                    print("[PTT] ⚪ No speech detected, ready for next command\n")
                continue

            # Start timing from when user input is captured
            response_start_time = time.time()

            user_input_lower = user_input.lower().rstrip('.!?,;')

            # Check for explicit mode switching (these don't need timing - just mode control)
            if 'switch to command mode' in user_input_lower or 'command mode' in user_input_lower:
                current_mode = 'command'
                speak("Command mode. Ready for desktop commands.")
                log_and_print(f"[MODE] 🔧 Command mode")
                continue

            if 'switch to chat mode' in user_input_lower or 'chat mode' in user_input_lower or 'conversation mode' in user_input_lower:
                current_mode = 'conversation'
                speak("Chat mode activated. Ask me anything!")
                log_and_print(f"[MODE] 💬 Conversation mode")
                continue

            # Check for history management
            if 'clear history' in user_input_lower or 'new topic' in user_input_lower:
                conversation_history = []
                speak("Conversation history cleared.")
                log_and_print(f"[CHAT] 🗑️  History cleared")
                continue

            # Use current mode (no automatic detection)
            intent_type = current_mode
            log_and_print(f"[MODE] {intent_type}")
            logger.info(f"[INTENT] input={user_input!r} mode={intent_type}")

            # Route to appropriate handler
            if intent_type == 'command':
              try:
                # COMMAND MODE - execute desktop tools
                log_and_print(f"[COMMAND] Processing: {user_input}")

                command_messages.append({"role": "user", "content": user_input})

                # Hybrid namespace + retrieval approach
                # Retrieve top 2 most relevant namespaces for this query (faster inference)
                retrieval_start_time = time.time()
                relevant_namespaces, detected_app = retrieve_relevant_namespaces(user_input, top_k=2)

                # Auto-focus: if an app was detected, focus its window before LLM acts
                auto_focused = False
                if detected_app:
                    try:
                        focus_result = window_control("focus", detected_app)
                        if "No window found" in focus_result:
                            log_and_print(f"[ROUTING] App '{detected_app}' not running, launching it")
                            try:
                                launch_result = mcp_client.call_tool("gnome_search", {"query": detected_app})
                                log_and_print(f"[ROUTING] Launched: {launch_result}")
                                for _attempt in range(10):
                                    time.sleep(0.5)
                                    focus_result = window_control("focus", detected_app)
                                    if "No window found" not in focus_result:
                                        break
                                if "No window found" not in focus_result:
                                    auto_focused = True
                                    log_and_print(f"[ROUTING] Auto-focused after launch ({(_attempt + 1) * 0.5:.1f}s): {focus_result}")
                                    command_messages[-1]["content"] += f"\n[{detected_app} has been opened and is focused. Do NOT open or search for it.]"
                                else:
                                    log_and_print(f"[ROUTING] App '{detected_app}' didn't appear within 5s", level='warning')
                            except Exception as e:
                                log_and_print(f"[ROUTING] Failed to launch '{detected_app}': {e}")
                        else:
                            auto_focused = True
                            log_and_print(f"[ROUTING] Auto-focused: {focus_result}")
                            command_messages[-1]["content"] += f"\n[{detected_app} is already focused. Do NOT open or search for it.]"
                    except Exception as e:
                        log_and_print(f"[ROUTING] Auto-focus failed: {e}")

                    # Pre-fetch shortcuts+skills so the LLM doesn't have to call get_app_shortcuts
                    try:
                        shortcut_info = get_app_shortcuts(detected_app)
                        if not shortcut_info.startswith("No shortcuts"):
                            command_messages[-1]["content"] += f"\n[{shortcut_info}]"
                            log_and_print(f"[ROUTING] Injected shortcuts+skills for '{detected_app}'")
                    except Exception as e:
                        log_and_print(f"[ROUTING] Failed to inject shortcuts: {e}")
                else:
                    # No app mentioned — check focused window for shortcut context
                    try:
                        result = mcp_client.call_tool("list_windows", {})
                        if not result.startswith("Error"):
                            windows = json.loads(result)
                            focused = next((w for w in windows if w.get('focused', False)), None)
                            if focused:
                                wm_class = focused.get('wmClass', '')
                                # Strip org.gnome. / org.mozilla. prefixes to get shortcut key
                                shortcut_key = wm_class.lower()
                                for prefix in ('org.gnome.', 'org.mozilla.', 'org.'):
                                    if shortcut_key.startswith(prefix):
                                        shortcut_key = shortcut_key[len(prefix):]
                                        break
                                shortcut_info = get_app_shortcuts(shortcut_key)
                                if not shortcut_info.startswith("No shortcuts"):
                                    friendly = get_friendly_app_name(wm_class)
                                    command_messages[-1]["content"] += f"\n[{friendly} is focused. {shortcut_info}]"
                                    log_and_print(f"[ROUTING] Injected shortcuts for focused app '{shortcut_key}'")
                                    # Force input namespace so input_control is available
                                    if 'input' not in [ns for ns in relevant_namespaces]:
                                        relevant_namespaces.append('input')
                    except Exception as e:
                        log_and_print(f"[ROUTING] Focused-window shortcut lookup failed: {e}")

                # Short-circuit: if the command is a pure focus/switch, skip the LLM
                _focus_verbs = ('switch to', 'focus', 'go to', 'open')
                focus_handled = False
                for fv in _focus_verbs:
                    if user_input_lower.startswith(fv):
                        remainder = user_input_lower[len(fv):].strip().strip('.,!').strip()
                        remainder = remainder.removeprefix('the ').strip()
                        if detected_app and remainder == detected_app and auto_focused:
                            friendly = get_friendly_app_name(detected_app)
                            speak(f"Switched to {friendly}.")
                            log_and_print(f"[ROUTING] Short-circuit: focus-only command, skipping LLM")
                            log_and_print(f"[TIMING] ⏱️  Response time: {time.time() - retrieval_start_time:.2f}s (no LLM)")
                            focus_handled = True
                        elif not detected_app and remainder:
                            result = window_control("focus", remainder)
                            if "No window found" not in result:
                                speak(result)
                                log_and_print(f"[ROUTING] Short-circuit: focused '{remainder}' by window match, skipping LLM")
                                log_and_print(f"[TIMING] ⏱️  Response time: {time.time() - retrieval_start_time:.2f}s (no LLM)")
                                focus_handled = True
                        break
                if focus_handled:
                    continue

                # Short-circuit: date/time queries
                _time_phrases = ('what time', 'what\'s the time', 'what is the time',
                                 'what date', 'what\'s the date', 'what is the date',
                                 'what day', 'what\'s the day', 'what is the day',
                                 'current time', 'current date', 'tell me the time',
                                 'tell me the date')
                if any(p in user_input_lower for p in _time_phrases):
                    result = get_datetime()
                    speak(result)
                    log_and_print(f"[ROUTING] Short-circuit: datetime query, skipping LLM")
                    log_and_print(f"[TIMING] ⏱️  Response time: {time.time() - retrieval_start_time:.2f}s (no LLM)")
                    continue

                # Short-circuit: battery queries
                _battery_phrases = ('battery', 'charge level', 'power level',
                                    'how much charge', 'how much power')
                if any(p in user_input_lower for p in _battery_phrases):
                    result = get_battery_status()
                    speak(result)
                    log_and_print(f"[ROUTING] Short-circuit: battery query, skipping LLM")
                    log_and_print(f"[TIMING] ⏱️  Response time: {time.time() - retrieval_start_time:.2f}s (no LLM)")
                    continue

                # Short-circuit: system setting toggles
                _toggle_map = {
                    'dark mode':       'dark_mode',
                    'dark style':      'dark_mode',
                    'dark theme':      'dark_mode',
                    'night light':     'night_light',
                    'night mode':      'night_light',
                    'do not disturb':  'do_not_disturb',
                    'dnd':             'do_not_disturb',
                    'wifi':            'wifi',
                    'wi-fi':           'wifi',
                    'bluetooth':       'bluetooth',
                }
                _on_verbs = ('turn on', 'enable', 'activate', 'switch on')
                _off_verbs = ('turn off', 'disable', 'deactivate', 'switch off')
                toggle_matched = False
                for setting_phrase, action_name in _toggle_map.items():
                    if setting_phrase in user_input_lower:
                        state = None
                        if any(v in user_input_lower for v in _on_verbs):
                            state = 'on'
                        elif any(v in user_input_lower for v in _off_verbs):
                            state = 'off'
                        if state:
                            result = system_settings(action_name, state)
                            state_word = "enabled" if state == "on" else "disabled"
                            speak(f"{setting_phrase.title()} {state_word}.")
                            log_and_print(f"[ROUTING] Short-circuit: {setting_phrase} {state}, skipping LLM")
                            log_and_print(f"[TIMING] ⏱️  Response time: {time.time() - retrieval_start_time:.2f}s (no LLM)")
                            toggle_matched = True
                            break
                if toggle_matched:
                    continue

                # Short-circuit: window management (close/minimize/maximize/restore + app name)
                window_handled = False
                if detected_app:
                    _window_actions = {
                        'close': 'close', 'quit': 'close', 'exit': 'close', 'kill': 'close',
                        'minimize': 'minimize', 'hide': 'minimize',
                        'maximize': 'maximize',
                        'restore': 'restore', 'unminimize': 'restore',
                    }
                    for verb, action in _window_actions.items():
                        if user_input_lower.startswith(verb):
                            remainder = user_input_lower[len(verb):].strip().strip('.,!').strip()
                            remainder = remainder.removeprefix('the ').strip()
                            if remainder == detected_app:
                                result = window_control(action, detected_app)
                                speak(result)
                                log_and_print(f"[ROUTING] Short-circuit: {action} {detected_app}, skipping LLM")
                                log_and_print(f"[TIMING] ⏱️  Response time: {time.time() - retrieval_start_time:.2f}s (no LLM)")
                                window_handled = True
                            break
                if window_handled:
                    continue

                # Short-circuit: window tiling ("move X to the right half", "tile X left")
                _tile_positions = {
                    'left half':      lambda w, h: (0, 0, w // 2, h),
                    'right half':     lambda w, h: (w // 2, 0, w // 2, h),
                    'top half':       lambda w, h: (0, 0, w, h // 2),
                    'bottom half':    lambda w, h: (0, h // 2, w, h // 2),
                    'top left':       lambda w, h: (0, 0, w // 2, h // 2),
                    'top right':      lambda w, h: (w // 2, 0, w // 2, h // 2),
                    'bottom left':    lambda w, h: (0, h // 2, w // 2, h // 2),
                    'bottom right':   lambda w, h: (w // 2, h // 2, w // 2, h // 2),
                    'left side':      lambda w, h: (0, 0, w // 2, h),
                    'right side':     lambda w, h: (w // 2, 0, w // 2, h),
                    'the left':       lambda w, h: (0, 0, w // 2, h),
                    'the right':      lambda w, h: (w // 2, 0, w // 2, h),
                    'center':         lambda w, h: (w // 4, h // 4, w // 2, h // 2),
                }
                tile_handled = False
                if any(p in user_input_lower for p in ('move', 'tile', 'snap', 'put')):
                    for position, calc_fn in _tile_positions.items():
                        if position in user_input_lower:
                            app_to_tile = detected_app
                            if not app_to_tile:
                                try:
                                    win_list = json.loads(mcp_client.call_tool("list_windows", {}))
                                    focused = next((w for w in win_list if w.get('focused', False)), None)
                                    if focused:
                                        app_to_tile = focused.get('wmClass', '')
                                except Exception:
                                    pass
                            if app_to_tile:
                                try:
                                    mon_result = mcp_client.call_tool("get_monitors", {})
                                    monitors = json.loads(mon_result)
                                    primary = next((m for m in monitors if m.get('primary')), monitors[0])
                                    scr_w = primary['width']
                                    scr_h = primary['height']
                                    tx, ty, tw, th = calc_fn(scr_w, scr_h)
                                    result = window_control("move_resize", app_to_tile, x=tx, y=ty, width=tw, height=th)
                                    friendly = get_friendly_app_name(app_to_tile) if app_to_tile else "Window"
                                    speak(f"Moved {friendly} to the {position}.")
                                    log_and_print(f"[ROUTING] Short-circuit: tile {app_to_tile} to {position}, skipping LLM")
                                    log_and_print(f"[TIMING] ⏱️  Response time: {time.time() - retrieval_start_time:.2f}s (no LLM)")
                                    tile_handled = True
                                except Exception as e:
                                    log_and_print(f"[ROUTING] Tiling failed: {e}", level='warning')
                            break
                if tile_handled:
                    continue

                # Short-circuit: audio controls
                audio_handled = False
                # Mute / unmute
                if user_input_lower in ('mute', 'mute the sound', 'mute sound', 'mute audio'):
                    result = audio_control("mute")
                    speak("Muted.")
                    audio_handled = True
                elif any(user_input_lower == p for p in ('unmute', 'unmute the sound', 'unmute sound', 'unmute audio')):
                    result = audio_control("unmute")
                    speak("Unmuted.")
                    audio_handled = True
                # Volume up / down
                elif any(p in user_input_lower for p in ('volume up', 'turn up', 'louder', 'raise the volume', 'raise volume', 'increase volume', 'increase the volume')):
                    result = audio_control("volume", level=10, relative=True)
                    speak("Volume up.")
                    audio_handled = True
                elif any(p in user_input_lower for p in ('volume down', 'turn down', 'quieter', 'lower the volume', 'lower volume', 'decrease volume', 'decrease the volume')):
                    result = audio_control("volume", level=-10, relative=True)
                    speak("Volume down.")
                    audio_handled = True
                # Set volume to X%
                elif 'volume' in user_input_lower:
                    import re
                    vol_match = re.search(r'(\d+)\s*%?', user_input_lower)
                    if vol_match:
                        level = int(vol_match.group(1))
                        result = audio_control("volume", level=level, relative=False)
                        speak(f"Volume set to {level}%.")
                        audio_handled = True
                # Media controls
                elif user_input_lower in ('play', 'play music', 'resume', 'resume playback'):
                    result = audio_control("play")
                    speak("Playing.")
                    audio_handled = True
                elif user_input_lower in ('pause', 'pause music', 'pause playback'):
                    result = audio_control("pause")
                    speak("Paused.")
                    audio_handled = True
                elif user_input_lower in ('play pause', 'play/pause', 'toggle playback'):
                    result = audio_control("play_pause")
                    speak("Toggled playback.")
                    audio_handled = True
                elif user_input_lower in ('stop', 'stop music', 'stop playback', 'stop playing'):
                    result = audio_control("stop")
                    speak("Stopped.")
                    audio_handled = True
                elif user_input_lower in ('next', 'next song', 'next track', 'skip'):
                    result = audio_control("next")
                    speak("Next track.")
                    audio_handled = True
                elif user_input_lower in ('previous', 'previous song', 'previous track', 'go back'):
                    result = audio_control("previous")
                    speak("Previous track.")
                    audio_handled = True
                if audio_handled:
                    log_and_print(f"[ROUTING] Short-circuit: audio control, skipping LLM")
                    log_and_print(f"[TIMING] ⏱️  Response time: {time.time() - retrieval_start_time:.2f}s (no LLM)")
                    continue

                # Short-circuit: screenshot
                _screenshot_phrases = ('take a screenshot', 'take screenshot', 'capture screen',
                                       'screenshot', 'screen capture', 'grab the screen',
                                       'capture the screen')
                if any(user_input_lower == p for p in _screenshot_phrases):
                    result = vision_control("screenshot")
                    speak(result)
                    log_and_print(f"[ROUTING] Short-circuit: screenshot, skipping LLM")
                    log_and_print(f"[TIMING] ⏱️  Response time: {time.time() - retrieval_start_time:.2f}s (no LLM)")
                    continue
                # App-specific screenshot: "take a screenshot of firefox"
                if detected_app and 'screenshot' in user_input_lower:
                    _app_screenshot_prefixes = ('take a screenshot of', 'take screenshot of',
                                                'screenshot of', 'capture')
                    app_screenshot = False
                    for prefix in _app_screenshot_prefixes:
                        if user_input_lower.startswith(prefix):
                            remainder = user_input_lower[len(prefix):].strip()
                            remainder = remainder.removeprefix('the ').strip()
                            if remainder == detected_app:
                                result = window_control("screenshot", detected_app)
                                speak(result)
                                log_and_print(f"[ROUTING] Short-circuit: screenshot of {detected_app}, skipping LLM")
                                log_and_print(f"[TIMING] ⏱️  Response time: {time.time() - retrieval_start_time:.2f}s (no LLM)")
                                app_screenshot = True
                            break
                    if app_screenshot:
                        continue

                # Short-circuit: brightness control
                if 'brightness' in user_input_lower or 'backlight' in user_input_lower:
                    target = "keyboard" if any(w in user_input_lower for w in ('keyboard', 'kbd', 'keys')) else "screen"
                    level = None
                    if any(w in user_input_lower for w in ('up', 'increase', 'brighter', 'raise')):
                        level = "up"
                    elif any(w in user_input_lower for w in ('down', 'decrease', 'dimmer', 'lower', 'dim')):
                        level = "down"
                    elif 'max' in user_input_lower or 'full' in user_input_lower:
                        level = "max"
                    elif 'min' in user_input_lower or ('off' in user_input_lower and target == "keyboard"):
                        level = "min"
                    else:
                        import re
                        pct_match = re.search(r'(\d+)\s*%', user_input_lower)
                        if pct_match:
                            level = f"{pct_match.group(1)}%"
                    if level:
                        result = set_brightness(target, level)
                        speak(result)
                        log_and_print(f"[ROUTING] Short-circuit: {target} brightness {level}, skipping LLM")
                        log_and_print(f"[TIMING] ⏱️  Response time: {time.time() - retrieval_start_time:.2f}s (no LLM)")
                        continue

                # Short-circuit: power profile
                if 'power mode' in user_input_lower or 'power profile' in user_input_lower or 'power saver' in user_input_lower:
                    if any(w in user_input_lower for w in ('what', 'current', 'which', 'get', 'check')):
                        result = get_power_profile()
                    elif 'performance' in user_input_lower:
                        result = set_power_profile("performance")
                    elif 'balanced' in user_input_lower:
                        result = set_power_profile("balanced")
                    elif any(w in user_input_lower for w in ('power saver', 'power-saver', 'saving')):
                        result = set_power_profile("power-saver")
                    else:
                        result = get_power_profile()
                    speak(result)
                    log_and_print(f"[ROUTING] Short-circuit: power profile, skipping LLM")
                    log_and_print(f"[TIMING] ⏱️  Response time: {time.time() - retrieval_start_time:.2f}s (no LLM)")
                    continue

                # Short-circuit: lock screen
                if any(p in user_input_lower for p in ('lock screen', 'lock the screen', 'lock my screen')):
                    result = lock_screen()
                    speak(result)
                    log_and_print(f"[ROUTING] Short-circuit: lock screen, skipping LLM")
                    log_and_print(f"[TIMING] ⏱️  Response time: {time.time() - retrieval_start_time:.2f}s (no LLM)")
                    continue

                # Short-circuit: power actions (with confirmation)
                _power_actions = {
                    'suspend': ('suspend', 'sleep', 'hibernate'),
                    'restart': ('restart', 'reboot'),
                    'shutdown': ('shut down', 'shutdown', 'power off', 'poweroff', 'turn off the computer'),
                    'logout': ('log out', 'logout', 'sign out', 'sign off'),
                }
                power_matched = None
                for action_name, phrases in _power_actions.items():
                    if any(p in user_input_lower for p in phrases):
                        power_matched = action_name
                        break
                if power_matched:
                    _power_confirmations = {
                        'suspend': "Are you sure you want to put the computer to sleep?",
                        'restart': "Are you sure you want to restart the computer?",
                        'shutdown': "Are you sure you want to shut down the computer?",
                        'logout': "Are you sure you want to log out of your desktop session?",
                    }
                    speak(_power_confirmations[power_matched])
                    confirmation = listen_and_transcribe()
                    if confirmation and any(w in confirmation.lower() for w in ('yes', 'yeah', 'yep', 'sure', 'do it', 'confirm', 'go ahead')):
                        result = power_action(power_matched)
                        speak(result)
                    else:
                        speak("Canceled.")
                    log_and_print(f"[ROUTING] Short-circuit: power action {power_matched}, skipping LLM")
                    log_and_print(f"[TIMING] ⏱️  Response time: {time.time() - retrieval_start_time:.2f}s (no LLM)")
                    continue

                # Short-circuit: install/uninstall apps
                _install_verbs = ('install ', 'uninstall ', 'remove app ')
                install_matched = None
                for iv in _install_verbs:
                    if user_input_lower.startswith(iv):
                        install_matched = iv.strip()
                        install_query = user_input_lower[len(iv):].strip().strip('.,!').strip()
                        break
                if install_matched and install_query:
                    is_uninstall = install_matched in ('uninstall', 'remove app')
                    action_word = "uninstall" if is_uninstall else "install"
                    log_and_print(f"[ROUTING] Short-circuit: {action_word} '{install_query}'")

                    speak(f"Searching for {install_query}.")
                    results = search_apps(install_query)

                    _confirm_words = ('yes', 'yeah', 'yep', 'sure', 'do it', 'confirm', 'go ahead')
                    _cancel_words = ('cancel', 'skip', 'nevermind', 'never mind', 'no', 'nope', 'stop', 'forget it', 'none')

                    def _do_install(name, app_id, source):
                        speak(f"{'Uninstalling' if is_uninstall else 'Installing'} {name}. This may take a moment.")
                        r = run_uninstall(app_id, source) if is_uninstall else run_install(app_id, source)
                        speak(r)

                    def _confirm_and_install(name, app_id, source):
                        speak(f"Found {name}. Should I {action_word} it?")
                        confirmation = listen_and_transcribe()
                        if confirmation and any(w in confirmation.lower() for w in _confirm_words):
                            _do_install(name, app_id, source)
                        else:
                            speak("Canceled.")

                    if not results:
                        speak(f"No apps found matching {install_query}.")
                    elif len(results) == 1:
                        name, app_id, source = results[0]
                        _confirm_and_install(name, app_id, source)
                    else:
                        # Check for exact name match first
                        exact = None
                        for name, app_id, source in results:
                            if name.lower() == install_query:
                                exact = (name, app_id, source)
                                break
                        if exact:
                            _confirm_and_install(*exact)
                        else:
                            # Multiple results, ask user to pick
                            names = [name for name, _, _ in results[:5]]
                            names_str = ", ".join(names[:-1]) + f", and {names[-1]}" if len(names) > 1 else names[0]
                            speak(f"I found {names_str}. Which one?")
                            choice = listen_and_transcribe()
                            if not choice:
                                speak("No response heard. Canceled.")
                            elif any(w in choice.lower() for w in _cancel_words):
                                speak("Canceled.")
                            else:
                                choice_lower = choice.lower().strip().strip('.,!').strip()
                                matched = None
                                for name, app_id, source in results:
                                    if name.lower() in choice_lower or choice_lower in name.lower():
                                        matched = (name, app_id, source)
                                        break
                                if matched:
                                    name, app_id, source = matched
                                    _confirm_and_install(name, app_id, source)
                                else:
                                    speak(f"Could not find {choice} in the results. Canceled.")

                    log_and_print(f"[ROUTING] Short-circuit: {action_word} app, skipping LLM")
                    log_and_print(f"[TIMING] ⏱️  Response time: {time.time() - retrieval_start_time:.2f}s (no LLM)")
                    continue

                # Build filtered tool schema with only relevant tools
                filtered_tools = build_filtered_tool_schema(relevant_namespaces)
                retrieval_elapsed = time.time() - retrieval_start_time
                log_and_print(f"[TIMING] ⏱️  RAG retrieval took: {retrieval_elapsed:.3f}s ({len(filtered_tools)} tools)")

                MAX_CHAIN_STEPS = 5
                last_tool_result = None
                chain_abort = False

                for chain_step in range(MAX_CHAIN_STEPS):
                    if chain_step > 0:
                        log_and_print(f"[CHAIN] Step {chain_step + 1}/{MAX_CHAIN_STEPS}")

                    debug_lines = ["[DEBUG] Messages sent to LLM:"]
                    for msg in command_messages:
                        role = msg.get('role', 'unknown')
                        content = msg.get('content', '')
                        if content and len(content) > 200:
                            content = content[:200] + "..."
                        debug_lines.append(f"  [{role}]: {content}")
                    debug_lines.append(f"[DEBUG] Available tools: {[t['function']['name'] for t in filtered_tools]}")
                    log_and_print('\n'.join(debug_lines), level='debug', console=DEBUG)

                    logger.info(f"[LLM_REQ] chain_step={chain_step} tools={[t['function']['name'] for t in filtered_tools]} msg_count={len(command_messages)}")
                    max_tokens = 300
                    llm_start_time = time.time()
                    response = call_llama_server(
                        messages=command_messages,
                        tools=filtered_tools,
                        temperature=0.0,
                        max_tokens=max_tokens
                    )
                    llm_elapsed = time.time() - llm_start_time

                    # Detect truncation: if LLM hit max_tokens, retry with more
                    eval_count = response.get('eval_count', 0)
                    if eval_count >= max_tokens and response['message'].get('tool_calls'):
                        log_and_print(f"[LLM] Output truncated at {max_tokens} tokens, retrying with 600...", level='warning')
                        response = call_llama_server(
                            messages=command_messages,
                            tools=filtered_tools,
                            temperature=0.0,
                            max_tokens=600
                        )
                        retry_elapsed = time.time() - llm_start_time - llm_elapsed
                        llm_elapsed = time.time() - llm_start_time
                        log_and_print(f"[TIMING] ⏱️  LLM inference took: {llm_elapsed:.2f}s (incl. truncation retry: {retry_elapsed:.2f}s)")
                    else:
                        log_and_print(f"[TIMING] ⏱️  LLM inference took: {llm_elapsed:.2f}s")

                    logger.info(f"[LLM_RESP] inference={llm_elapsed:.2f}s tokens={response.get('eval_count', 'N/A')} has_tool_calls={bool(response['message'].get('tool_calls'))}")

                    debug_lines = [f"[DEBUG] Gemma eval_count: {response.get('eval_count', 'N/A')} tokens"]
                    debug_lines.append(f"[DEBUG] Response content length: {len(response['message'].get('content', ''))}")
                    if response['message'].get('content'):
                        debug_lines.append(f"[DEBUG] Content preview: {response['message']['content'][:200]}")
                    if response['message'].get('tool_calls'):
                        debug_lines.append("[DEBUG] Tool calls:")
                        for tc in response['message']['tool_calls']:
                            debug_lines.append(f"  - {tc['function']['name']}: {tc['function']['arguments']}")
                    log_and_print('\n'.join(debug_lines), level='debug', console=DEBUG)

                    message = response['message']
                    command_messages.append(message)

                    if not message.get('tool_calls'):
                        # LLM returned text — final answer
                        content = message.get('content', '').strip()
                        if content:
                            log_and_print(f"\n[OS Feedback]: {content}")
                            response_time = time.time() - response_start_time
                            log_and_print(f"[TIMING] ⏱️  Response time: {response_time:.2f}s")
                            speak(content)
                        elif last_tool_result:
                            log_and_print(f"\n[OS Feedback]: {last_tool_result}")
                            response_time = time.time() - response_start_time
                            log_and_print(f"[TIMING] ⏱️  Response time: {response_time:.2f}s")
                            speak(last_tool_result)
                        else:
                            log_and_print("[COMMAND] ⚠️  No tool call generated. Try rephrasing or switch to chat mode.", level='warning')
                            response_time = time.time() - response_start_time
                            log_and_print(f"[TIMING] ⏱️  Response time: {response_time:.2f}s")
                            speak("I'm not sure what command to run. Try rephrasing or say 'switch to chat mode'.")
                        break

                    for tool_call in message['tool_calls']:
                        tool_name = tool_call['function']['name']
                        arguments = tool_call['function']['arguments']
                        tool_call_id = tool_call.get('id', f"call_{chain_step}_{tool_name}")

                        # Parse JSON string to dict if needed (llama-server returns string, Ollama returns dict)
                        if isinstance(arguments, str):
                            try:
                                arguments = json.loads(arguments)
                            except json.JSONDecodeError:
                                log_and_print(f"[COMMAND] ⚠️  LLM returned malformed JSON for {tool_name}: {arguments[:100]}...", level='warning')
                                speak("Something went wrong processing that command. Please try again.")
                                chain_abort = True
                                break

                        result = None

                        # Check if it's a direct MCP tool (no wrapper needed)
                        if tool_name in direct_mcp_tools:
                            log_and_print(f"\n[SYSTEM] Calling MCP tool directly: {tool_name}")

                            # Special handling for gnome_search: check for markers
                            if tool_name == "gnome_search" and "query" in arguments:
                                query = arguments["query"].strip()

                                # Check for " website" marker - use xdg-open for deterministic browser opening
                                if query.endswith(' website'):
                                    url = query[:-8].strip()  # Remove " website" suffix

                                    # Add protocol if missing
                                    if not url.startswith('http://') and not url.startswith('https://'):
                                        url = f"https://www.{url}"

                                    log_and_print(f"[GNOME_SEARCH] Detected website marker, opening URL via xdg-open: {url}")
                                    subprocess.run(['xdg-open', url], check=False,
                                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                                    result = f"Opening {url} in browser"

                                # Check for " file" marker - use open_file MCP tool for smart file opening
                                elif query.endswith(' file'):
                                    filename = query[:-5].strip()  # Remove " file" suffix

                                    log_and_print(f"[GNOME_SEARCH] Detected file marker, using open_file: {filename}")
                                    result = mcp_client.call_tool("open_file", {"path": filename})

                                else:
                                    # Before launching, check if the app is already running
                                    try:
                                        win_list = json.loads(mcp_client.call_tool("list_windows", {}))
                                        match = smart_match_window(query, win_list)
                                        if match:
                                            mcp_client.call_tool("focus_window", {"id": match["id"]})
                                            friendly = get_friendly_app_name(match.get('wmClass', query))
                                            result = f"{friendly} is already running. Switched to it."
                                            log_and_print(f"[GNOME_SEARCH] App already running: {friendly}, focused window '{match.get('title', '')}'")
                                        else:
                                            result = mcp_client.call_tool(tool_name, arguments)
                                    except Exception:
                                        result = mcp_client.call_tool(tool_name, arguments)
                            else:
                                result = mcp_client.call_tool(tool_name, arguments)

                            # Auto-recovery: if automation is disabled, enable and retry
                            if "Error" in result and ("disabled" in result.lower() or "not responding" in result.lower()):
                                log_and_print(f"[SYSTEM] Tool failed, attempting auto-recovery...")
                                health_ok, health_msg = check_automation_health(auto_enable=True)
                                if health_ok:
                                    log_and_print(f"[SYSTEM] Retrying {tool_name}...")
                                    result = mcp_client.call_tool(tool_name, arguments)
                                else:
                                    result = f"Error: {health_msg}"

                        # Check if it's a custom wrapper function
                        elif tool_name in available_tools:
                            function_to_call = available_tools[tool_name]
                            result = function_to_call(**arguments)

                            # Auto-recovery: if result indicates automation error, enable and retry
                            if "Error" in result and ("disabled" in result.lower() or "not responding" in result.lower()):
                                log_and_print(f"[SYSTEM] Tool failed, attempting auto-recovery...")
                                health_ok, health_msg = check_automation_health(auto_enable=True)
                                if health_ok:
                                    log_and_print(f"[SYSTEM] Retrying {tool_name}...")
                                    result = function_to_call(**arguments)
                                else:
                                    result = f"Error: {health_msg}"

                        else:
                            result = f"Unknown tool: {tool_name}"
                            log_and_print(f"[COMMAND] ⚠️  {result}", level='warning')

                        log_and_print(f"\n[OS Feedback]: {result}")
                        logger.info(f"[TOOL_EXEC] tool={tool_name} args={arguments} result_len={len(str(result))}")
                        logger.debug(f"[TOOL_RESULT] tool={tool_name} result={str(result)[:500]}")
                        last_tool_result = result

                        # Append tool result to messages so LLM can chain
                        command_messages.append({
                            "role": "tool",
                            "tool_call_id": tool_call_id,
                            "content": str(result)
                        })

                    if chain_abort:
                        break

                else:
                    # Exhausted MAX_CHAIN_STEPS — speak whatever we have
                    log_and_print(f"[CHAIN] ⚠️  Reached max chain steps ({MAX_CHAIN_STEPS})", level='warning')
                    if last_tool_result:
                        response_time = time.time() - response_start_time
                        log_and_print(f"[TIMING] ⏱️  Response time: {response_time:.2f}s")
                        speak(last_tool_result)

                response_time = time.time() - response_start_time
                log_and_print(f"[TIMING] ⏱️  Total chain time: {response_time:.2f}s")
              except Exception as e:
                log_and_print(f"[ERROR] Command failed: {e}", level='error')
                speak("Sorry, that command failed.")
              finally:
                command_messages = [command_system_msg]

            else:  # intent_type == 'conversation'
                # CONVERSATION MODE - chat with Gemma
                log_and_print(f"[CHAT] Processing: {user_input}")

                answer, conversation_history = handle_conversation(user_input, conversation_history)

                log_and_print(f"\n[Agent]: {answer}")
                response_time = time.time() - response_start_time
                log_and_print(f"[TIMING] ⏱️  Response time: {response_time:.2f}s")
                speak(answer)

            # Blank line before next prompt in PTT mode
            if PUSH_TO_TALK_MODE:
                print()

    except KeyboardInterrupt:
        log_and_print("\n[SYSTEM] 🛑 Ctrl+C received, shutting down gracefully...")
        logger.info("=== Orchestrator session ended ===")
    finally:
        # Cleanup: optionally kill llama-server on exit
        if KILL_SERVER_ON_EXIT:
            log_and_print("[SYSTEM] Stopping llama-server (--kill-server flag)...")
            kill_server()
        else:
            log_and_print("[SYSTEM] Note: llama-server is still running on port 8081")
            log_and_print("[SYSTEM] Reuse it on next run for faster startup, or kill with --kill-server flag")

if __name__ == "__main__":
    try:
        run_agent()
    except KeyboardInterrupt:
        log_and_print("\n\n[SYSTEM] Shutting down Agentic OS...")
