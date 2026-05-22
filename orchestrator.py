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
from voice_io import speak, listen_and_transcribe, check_audio_health

# ----------------------------------------
# Health Check & Auto-Recovery
# ----------------------------------------
def check_automation_health(auto_enable=True, retries=3) -> tuple[bool, str]:
    """
    Check if GNOME automation extension is running and enabled.

    Args:
        auto_enable: If True, automatically enable automation if it's disabled
        retries: Number of attempts (D-Bus proxy may need time to introspect)

    Returns:
        (success: bool, message: str)
    """
    for attempt in range(retries):
        try:
            ping_result = mcp_client.call_tool("ping", {})
            if "Error" in ping_result or "alive" not in ping_result.lower():
                if attempt < retries - 1:
                    time.sleep(1)
                    continue
                return False, "GNOME automation extension not responding. Please check if it's installed and enabled in GNOME Extensions."

            enabled_result = mcp_client.call_tool("get_enabled", {})
            if "Error" in enabled_result:
                if attempt < retries - 1:
                    time.sleep(1)
                    continue
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
            if attempt < retries - 1:
                time.sleep(1)
                continue
            return False, f"Health check failed: {e}"

    return False, "Health check failed after retries"


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
from tools.standalone import (get_datetime,
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

# Initialize command router and LLM chain
import command_router
command_router.init(mcp_client, speak, listen_and_transcribe)

import llm_chain
llm_chain.init(mcp_client, call_llama_server, speak,
               check_automation_health, debug=DEBUG)

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

    # Ensure GNOME Shell extension is enabled before starting MCP
    _ext_uuid = "desktop-automation@anthonymcp.github.io"
    try:
        _global_disabled = subprocess.run(
            ["gsettings", "get", "org.gnome.shell", "disable-user-extensions"],
            capture_output=True, text=True, timeout=5)
        if "true" in _global_disabled.stdout.lower():
            log_and_print("[SYSTEM] User extensions globally disabled, enabling...")
            subprocess.run(
                ["gsettings", "set", "org.gnome.shell", "disable-user-extensions", "false"],
                timeout=5)
            time.sleep(1)

        _ext_check = subprocess.run(
            ["gnome-extensions", "info", _ext_uuid],
            capture_output=True, text=True, timeout=5)
        if "Enabled: No" in _ext_check.stdout:
            log_and_print("[SYSTEM] Enabling GNOME Shell extension...")
            subprocess.run(["gnome-extensions", "enable", _ext_uuid], timeout=5)
            time.sleep(1)
    except Exception as e:
        log_and_print(f"[SYSTEM] Could not check/enable extension: {e}", level='warning')

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

    # Check audio health (mic + output)
    log_and_print("[SYSTEM] Checking audio health...")
    if not check_audio_health():
        log_and_print("[SYSTEM] ⚠️  Audio issue detected — voice commands may not work", level='warning')

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

                retrieval_start_time = time.time()

                # Step 1: RAG retrieval + auto-focus + shortcut injection
                relevant_namespaces, detected_app, auto_focused = \
                    command_router.prepare_command_context(
                        user_input, command_messages, retrieval_start_time)

                # Step 2: Try short-circuit (skip LLM for simple commands)
                if command_router.try_short_circuit(
                        user_input, user_input_lower,
                        detected_app, auto_focused,
                        retrieval_start_time):
                    continue

                # Step 3: Build filtered tools and run LLM chain
                filtered_tools = build_filtered_tool_schema(relevant_namespaces)
                retrieval_elapsed = time.time() - retrieval_start_time
                log_and_print(f"[TIMING] ⏱️  RAG retrieval took: {retrieval_elapsed:.3f}s ({len(filtered_tools)} tools)")

                llm_chain.run_chain(
                    command_messages, filtered_tools,
                    available_tools, direct_mcp_tools,
                    response_start_time)

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
