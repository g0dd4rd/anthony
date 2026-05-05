#!/usr/bin/env python3
"""
Voice-Driven Desktop Orchestrator with SAFE Dialog Handling

Features:
- ✅ VAD continuous listening
- ✅ Fast vision analysis (gemma4 + concise)
- ✅ SAFE close handling with dialog detection
- ✅ Reads dialog options to user via voice
- ✅ Waits for user's voice choice
- ✅ Verifies action succeeded
- ✅ Never loses user data without explicit consent
"""

import ollama, os
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
# Tool Functions
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

        print(f"[SYSTEM] 🤖 Running vision analysis with gemma4 (this may take 2-10 seconds)...")
        print(f"[SYSTEM] ⏳ Please wait...")

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

def focus_window_by_name(window_name: str) -> str:
    """Focus a window by its title or application name."""
    print(f"\n[SYSTEM] Focusing window: {window_name}...")
    try:
        result = mcp_client.call_tool("list_windows", {})
        if result.startswith("Error"):
            return result
        windows = json.loads(result)
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
        result = mcp_client.call_tool("focus_window", {"window_id": window_id})
        return f"Focused window: {target_window.get('title', 'Unknown')}"
    except Exception as e:
        return f"Error focusing window: {str(e)}"

def close_window_by_name(window_name: str) -> str:
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
    print(f"\n[SYSTEM] Closing window: {window_name}...")

    try:
        # Step 1: Find target window
        result = mcp_client.call_tool("list_windows", {})
        if result.startswith("Error"):
            return result

        windows = json.loads(result)
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
                    return f"Successfully closed {window_title}"

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
                    return f"Dialog closed. Window {window_title} is still open (you may have chosen Cancel)"
                else:
                    return f"Successfully closed {window_title}"

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
    print(f"\n[SYSTEM] Pressing key combo: {keys}...")
    try:
        result = mcp_client.call_tool("key_combo", {"keys": keys})
        return f"Pressed {keys}"
    except Exception as e:
        return f"Error pressing keys: {str(e)}"

# Available tools
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

# Tool schema (removed 'force' parameter from close_window_by_name)
tool_schema = [
{"type": "function", "function": {"name": "launch_application", "description": "Launches a graphical application on the Linux desktop.", "parameters": {"type": "object", "properties": {"app_name": {"type": "string", "description": "The command name of the app"}}, "required": ["app_name"]}}},
{"type": "function", "function": {"name": "describe_desktop", "description": "Captures a screenshot of the desktop and describes what is visible using AI vision.", "parameters": {"type": "object", "properties": {}}}},
{"type": "function", "function": {"name": "list_installed_applications", "description": "Lists all installed GUI applications available on the Linux system.", "parameters": {"type": "object", "properties": {}}}},
{"type": "function", "function": {"name": "list_open_windows", "description": "Lists all currently open windows on the desktop.", "parameters": {"type": "object", "properties": {}}}},
{"type": "function", "function": {"name": "focus_window_by_name", "description": "Focus and bring to front a window by its title or application name.", "parameters": {"type": "object", "properties": {"window_name": {"type": "string", "description": "Part of the window title or application name to match"}}, "required": ["window_name"]}}},
{"type": "function", "function": {"name": "close_window_by_name", "description": "Safely close a window. If unsaved changes exist, asks user via voice what to do (Save, Discard, Cancel).", "parameters": {"type": "object", "properties": {"window_name": {"type": "string", "description": "Part of the window title or application name to match"}}, "required": ["window_name"]}}},
{"type": "function", "function": {"name": "type_text_in_window", "description": "Type text into the currently focused window.", "parameters": {"type": "object", "properties": {"text": {"type": "string", "description": "The text to type"}}, "required": ["text"]}}},
{"type": "function", "function": {"name": "press_key_combo", "description": "Press a keyboard combination like Ctrl+C, Alt+Tab, Super+l, etc.", "parameters": {"type": "object", "properties": {"keys": {"type": "string", "description": "Key combination like 'Ctrl+c', 'Alt+Tab', 'Super+l'"}}, "required": ["keys"]}}}
]

# ----------------------------------------
# Voice Setup
# ----------------------------------------
print("[SYSTEM] Loading Neural Voice...")
voice_model = PiperVoice.load("en_US-lessac-medium.onnx")
print("[SYSTEM] Voice ready.")

def speak(text: str):
    """Converts text to neural speech and plays it."""
    print(f"\n[Agent]: {text}")

    # Skip TTS if text is empty
    if not text or text.strip() == "":
        print(f"[SYSTEM] ⚠️ Skipping TTS - empty text")
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
# Orchestrator Loop
# ----------------------------------------
def run_agent():
    print("\n" + "="*60)
    print("🛡️  SAFE Agentic OS with Dialog Handling")
    print("="*60)
    print("✅ VAD - unlimited voice input")
    print("✅ Safe close - never loses data without your consent")
    print("✅ Dialog detection - reads options to you")
    print("✅ Voice confirmation - you choose what to do\n")

    print("[SYSTEM] Starting MCP client...")
    mcp_client.start()

    messages = [
        {
            "role": "system",
            "content": "You are a silent system orchestrator. Your ONLY job is to execute tool calls based on user intent. DO NOT output conversational text. DO NOT confirm actions. DO NOT be polite. If you need to use a tool, output ONLY the tool call. FORGET gedit and USE gnome-text-editor."
        }
    ]

    try:
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

                        messages = [messages[0]]

    except KeyboardInterrupt:
        print("\n[SYSTEM] 🛑 Ctrl+C received, shutting down gracefully...")
        return

if __name__ == "__main__":
    try:
        run_agent()
    except KeyboardInterrupt:
        print("\n\n[SYSTEM] Shutting down Agentic OS...")
