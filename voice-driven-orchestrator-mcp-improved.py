#!/usr/bin/env python3
import ollama, os
import pyaudio
import shutil, subprocess
import wave
import asyncio
import json
import threading
import time
from queue import Queue

from faster_whisper import WhisperModel
from piper.voice import PiperVoice
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
        # Wait for connection to be ready
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
            env=os.environ.copy()  # Pass all environment variables including DISPLAY and DBUS
        )

        async with stdio_client(server_params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                self.session = session
                print("[SYSTEM] MCP connected to gnome-desktop-mcp")

                # Process commands from queue
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

        # Wait for result with timeout
        start_time = time.time()
        while self.result_queue.empty():
            if time.time() - start_time > timeout:
                return f"Error: Tool call timed out after {timeout}s"
            time.sleep(0.01)

        status, result = self.result_queue.get()
        if status == "error":
            return f"Error: {result}"
        return result

# Initialize MCP client
mcp_client = MCPClient()

# ----------------------------------------
# Tool Functions (Original + MCP)
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
    print(f"\n[SYSTEM] Capturing screenshot with MCP...")

    try:
        # Use MCP screenshot tool
        result = mcp_client.call_tool("screenshot", {"include_cursor": False, "format": "path"})

        if result.startswith("Error"):
            return result

        # Parse the screenshot path from result
        screenshot_path = result.strip()

        print(f"[SYSTEM] Analyzing screenshot: {screenshot_path}")

        # Send screenshot to Ollama with faster vision model
        with open(screenshot_path, 'rb') as img_file:
            import base64
            img_data = base64.b64encode(img_file.read()).decode('utf-8')

        # IMPROVEMENT #1 & #2: Use gemma4 with concise prompt (already loaded for intent inference)
        response = ollama.chat(
            model='gemma4:e4b',  # Reuse same model as orchestrator
            messages=[{
                'role': 'user',
                'content': 'Describe this screenshot in 2-3 sentences. Focus on: open applications, visible windows, and key UI elements. Be concise.',
                'images': [img_data]
            }],
            options={
                'num_ctx': 2048,      # Reduce context for speed
                'num_predict': 100,   # Limit output tokens (faster)
                'temperature': 0.3,
                'num_gpu': 99,        # Use GPU layers for Intel Arc
            }
        )

        description = response['message']['content']

        # Clean up screenshot file
        try:
            os.remove(screenshot_path)
        except:
            pass

        return description

    except Exception as e:
        return f"Error capturing or analyzing screenshot: {str(e)}"

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

def focus_window_by_name(window_name: str) -> str:
    """Focus a window by its title or application name."""
    print(f"\n[SYSTEM] Focusing window: {window_name}...")

    try:
        # Get list of windows
        result = mcp_client.call_tool("list_windows", {})

        if result.startswith("Error"):
            return result

        windows = json.loads(result)

        # Find matching window (case-insensitive search)
        target_window = None
        window_name_lower = window_name.lower()

        for w in windows:
            title = w.get('title', '').lower()
            wm_class = w.get('wmClass', '').lower()

            if window_name_lower in title or window_name_lower in wm_class:
                target_window = w
                break

        if not target_window:
            return f"No window found matching '{window_name}'"

        # Focus the window
        window_id = target_window['id']
        result = mcp_client.call_tool("focus_window", {"window_id": window_id})

        return f"Focused window: {target_window.get('title', 'Unknown')}"

    except Exception as e:
        return f"Error focusing window: {str(e)}"

def close_window_by_name(window_name: str, force: bool = False) -> str:
    """Close a window by its title or application name.

    IMPROVEMENT #3: Handles dialogs and unsaved files.

    Args:
        window_name: Part of window title or app name to match
        force: If True, forcefully closes without saving
    """
    print(f"\n[SYSTEM] Closing window: {window_name}...")

    try:
        # Get list of windows
        result = mcp_client.call_tool("list_windows", {})

        if result.startswith("Error"):
            return result

        windows = json.loads(result)

        # Find matching window
        target_window = None
        window_name_lower = window_name.lower()

        for w in windows:
            title = w.get('title', '').lower()
            wm_class = w.get('wmClass', '').lower()

            if window_name_lower in title or window_name_lower in wm_class:
                target_window = w
                break

        if not target_window:
            return f"No window found matching '{window_name}'"

        window_id = target_window['id']
        window_title = target_window.get('title', 'Unknown')

        # IMPROVEMENT #3: First, try to close normally
        result = mcp_client.call_tool("close_window", {"window_id": window_id})

        # Wait a moment for potential dialogs
        time.sleep(0.5)

        # Check if window still exists (might have a dialog)
        result = mcp_client.call_tool("list_windows", {})
        if not result.startswith("Error"):
            windows_after = json.loads(result)
            window_still_exists = any(w['id'] == window_id for w in windows_after)

            if window_still_exists:
                print(f"[SYSTEM] Window still open, checking for dialogs...")

                # Look for dialog windows (alerts, confirmations)
                dialogs = [w for w in windows_after if 'alert' in w.get('roleName', '').lower() or
                          'dialog' in w.get('title', '').lower() or
                          'save' in w.get('title', '').lower()]

                if dialogs:
                    print(f"[SYSTEM] Found dialog, attempting to dismiss...")

                    if force:
                        # Press "Don't Save" or "Discard" button by pressing Tab+Enter or Escape
                        mcp_client.call_tool("key_combo", {"keys": "Escape"})
                        time.sleep(0.3)
                    else:
                        # Try pressing Escape to cancel and warn user
                        mcp_client.call_tool("key_combo", {"keys": "Escape"})
                        return f"Window '{window_title}' has unsaved changes. Say 'force close {window_name}' to close without saving."

                # Try pressing Ctrl+W as alternative
                mcp_client.call_tool("key_combo", {"keys": "Ctrl+w"})
                time.sleep(0.3)

                # Check again
                result = mcp_client.call_tool("list_windows", {})
                if not result.startswith("Error"):
                    windows_final = json.loads(result)
                    if any(w['id'] == window_id for w in windows_final):
                        # Last resort: kill the process
                        pid = target_window.get('pid')
                        if pid and force:
                            subprocess.run(['kill', str(pid)], stderr=subprocess.DEVNULL)
                            return f"Force closed window: {window_title}"
                        else:
                            return f"Unable to close window: {window_title}. Try 'force close {window_name}'."

        return f"Closed window: {window_title}"

    except Exception as e:
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
    print(f"\n[SYSTEM] Pressing key combo: {keys}...")

    try:
        result = mcp_client.call_tool("key_combo", {"keys": keys})
        return f"Pressed {keys}"

    except Exception as e:
        return f"Error pressing keys: {str(e)}"

# Available tools dictionary
available_tools = {
    "launch_application": launch_application,
    "describe_desktop": describe_desktop,
    "list_installed_applications": list_installed_applications,
    "list_open_windows": list_open_windows,
    "focus_window_by_name": focus_window_by_name,
    "close_window_by_name": close_window_by_name,
    "type_text_in_window": type_text_in_window,
    "press_key_combo": press_key_combo,
}

# Tool schema for Ollama
tool_schema = [
{
    "type": "function",
    "function": {
        "name": "launch_application",
        "description": "Launches a graphical application on the Linux desktop.",
        "parameters": {
            "type": "object",
            "properties": {
                "app_name": {
                    "type": "string",
                    "description": "The command name of the app"
                }
            },
            "required": ["app_name"]
        }
    }
},
{
    "type": "function",
    "function": {
        "name": "describe_desktop",
        "description": "Captures a screenshot of the desktop and describes what is visible using AI vision.",
        "parameters": {
            "type": "object",
            "properties": {}
        }
    }
},
{
    "type": "function",
    "function": {
        "name": "list_installed_applications",
        "description": "Lists all installed GUI applications available on the Linux system.",
        "parameters": {
            "type": "object",
            "properties": {}
        }
    }
},
{
    "type": "function",
    "function": {
        "name": "list_open_windows",
        "description": "Lists all currently open windows on the desktop.",
        "parameters": {
            "type": "object",
            "properties": {}
        }
    }
},
{
    "type": "function",
    "function": {
        "name": "focus_window_by_name",
        "description": "Focus and bring to front a window by its title or application name.",
        "parameters": {
            "type": "object",
            "properties": {
                "window_name": {
                    "type": "string",
                    "description": "Part of the window title or application name to match"
                }
            },
            "required": ["window_name"]
        }
    }
},
{
    "type": "function",
    "function": {
        "name": "close_window_by_name",
        "description": "Close a window by its title or application name. Handles unsaved file dialogs.",
        "parameters": {
            "type": "object",
            "properties": {
                "window_name": {
                    "type": "string",
                    "description": "Part of the window title or application name to match"
                },
                "force": {
                    "type": "boolean",
                    "description": "If true, forcefully close without saving. Default false.",
                    "default": False
                }
            },
            "required": ["window_name"]
        }
    }
},
{
    "type": "function",
    "function": {
        "name": "type_text_in_window",
        "description": "Type text into the currently focused window.",
        "parameters": {
            "type": "object",
            "properties": {
                "text": {
                    "type": "string",
                    "description": "The text to type"
                }
            },
            "required": ["text"]
        }
    }
},
{
    "type": "function",
    "function": {
        "name": "press_key_combo",
        "description": "Press a keyboard combination like Ctrl+C, Alt+Tab, Super+l, etc.",
        "parameters": {
            "type": "object",
            "properties": {
                "keys": {
                    "type": "string",
                    "description": "Key combination like 'Ctrl+c', 'Alt+Tab', 'Super+l'"
                }
            },
            "required": ["keys"]
        }
    }
}]

# ----------------------------------------
# Voice Setup
# ----------------------------------------
print("[SYSTEM] Loading Neural Voice...")
voice_model = PiperVoice.load("en_US-lessac-medium.onnx")
print("[SYSTEM] Voice ready.")

def speak(text: str):
    """Converts text to neural speech and plays it."""
    print(f"\n[Agent]: {text}")

    temp_audio_path = "/tmp/agent_response.wav"

    try:
        with wave.open(temp_audio_path, "wb") as wav_file:
            voice_model.synthesize_wav(text, wav_file)

        subprocess.run(["aplay", "-q", temp_audio_path], check=True)

    except Exception as e:
        print(f"[SYSTEM] Voice error: {e}")
        pass

# ----------------------------------------
# Voice Input
# ----------------------------------------
model = WhisperModel("medium.en", device="cpu", compute_type="int8")

def listen_and_transcribe():
    CHUNK = 1024
    FORMAT = pyaudio.paInt16
    CHANNELS = 1
    RATE = 16000
    p = pyaudio.PyAudio()

    stream = p.open(format=FORMAT, channels=CHANNELS, rate=RATE, input=True, frames_per_buffer=CHUNK)
    print("\n[SYSTEM] Faster-Whisper is listening...")

    frames = []
    for i in range(0, int(RATE / CHUNK * 4)):
        data = stream.read(CHUNK)
        frames.append(data)

    stream.stop_stream()
    stream.close()
    p.terminate()

    with wave.open("/tmp/temp.wav", 'wb') as wf:
        wf.setnchannels(CHANNELS)
        wf.setsampwidth(p.get_sample_size(FORMAT))
        wf.setframerate(RATE)
        wf.writeframes(b''.join(frames))

    segments, info = model.transcribe("/tmp/temp.wav",
        beam_size=5,
        vad_filter=True,
        vad_parameters=dict(min_silence_duration_ms=500))

    text = "".join([segment.text for segment in segments])

    print(f"You said: \"{text.strip()}\"")
    return text.strip()

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
# Orchestrator Loop
# ----------------------------------------
def run_agent():
    print("Agentic OS Initialized.")

    # Start MCP client connection
    print("[SYSTEM] Starting MCP client...")
    mcp_client.start()

    messages = [
        {
            "role": "system",
            "content": "You are a silent system orchestrator. Your ONLY job is to execute tool calls based on user intent. DO NOT output conversational text. DO NOT confirm actions. DO NOT be polite. If you need to use a tool, output ONLY the tool call. FORGET gedit and USE gnome-text-editor. When user says 'force close', set force=true in close_window_by_name."
        }
    ]

    while True:
        user_input = listen_and_transcribe()
        if not user_input:
            continue

        messages.append({"role": "user", "content": user_input})

        response = ollama.chat(
            model='gemma4:e4b',
            messages=messages,
            tools=tool_schema,
            keep_alive=-1,
            options={
                'temperature': 0.0,
                'top_p': 0.1
            }
        )

        message = response['message']
        messages.append(message)

        if message.get('tool_calls'):
            for tool_call in message['tool_calls']:
                tool_name = tool_call['function']['name']
                arguments = tool_call['function']['arguments']

                if tool_name in available_tools:
                    function_to_call = available_tools[tool_name]
                    result = function_to_call(**arguments)

                    print(f"\n[OS Feedback]: {result}")
                    speak(result)

                    messages = [messages[0]]  # Reset to system prompt only

if __name__ == "__main__":
    try:
        run_agent()
    except KeyboardInterrupt:
        print("\n[SYSTEM] Shutting down Agentic OS...")
