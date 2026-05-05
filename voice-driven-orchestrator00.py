import ollama, os
import pyaudio
import shutil, subprocess
import wave

from faster_whisper import WhisperModel
from piper.voice import PiperVoice

# ----------------------------------------
# 1. The Tool Executor
# ----------------------------------------
def launch_application(app_name: str) -> str:
    """Launches a graphical application in the background."""
    print(f"\n[SYSTEM] Executing command: Launching {app_name}...")

    #if shutil.which(app_name) is None:
        #error_msg = f"Execution failed. The binary '{app_name}' does not exist on this system. Try a different Linux binary name."
        #print(f"[SYSTEM] {error_msg}")
        # We return the error string back to Llama so it knows it failed and can retry!
        #return error_msg

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
    print(f"\n[SYSTEM] Capturing screenshot...")

    try:
        # Call the capture_screenshot.py script
        result = subprocess.run(
            ["/home/jprajzne/anthony/capture_screenshot.py"],
            capture_output=True,
            text=True,
            timeout=10
        )

        if result.returncode != 0:
            return "Failed to capture screenshot."

        # Parse the URI from output (format: file:///home/user/Pictures/...)
        screenshot_uri = result.stdout.strip()

        # Convert URI to path and get the actual file location
        if screenshot_uri.startswith("file://"):
            screenshot_path = screenshot_uri.replace("file://", "")
        else:
            # Fallback: find newest screenshot in ~/Pictures/
            pictures_dir = os.path.expanduser("~/Pictures")
            screenshots = sorted(
                [f for f in os.listdir(pictures_dir) if f.startswith("screenshot")],
                key=lambda x: os.path.getmtime(os.path.join(pictures_dir, x)),
                reverse=True
            )
            if not screenshots:
                return "No screenshot found."
            screenshot_path = os.path.join(pictures_dir, screenshots[0])

        print(f"[SYSTEM] Analyzing screenshot: {screenshot_path}")

        # Send screenshot to Ollama with vision model for description
        with open(screenshot_path, 'rb') as img_file:
            import base64
            img_data = base64.b64encode(img_file.read()).decode('utf-8')

        response = ollama.chat(
            model='gemma4:e4b',
            messages=[{
                'role': 'user',
                'content': 'Describe what you see in this screenshot in detail.',
                'images': [img_data]
            }]
        )

        description = response['message']['content']
        return description

    except Exception as e:
        return f"Error capturing or analyzing screenshot: {str(e)}"

def list_installed_applications() -> str:
    """Lists all installed GUI applications on the system."""
    print(f"\n[SYSTEM] Scanning for installed applications...")

    try:
        apps = get_installed_gui_apps()
        app_count = len(apps)

        # Create a natural language response
        if app_count == 0:
            return "No applications found."

        # Return a summary that's suitable for TTS
        return f"Found {app_count} installed applications including {', '.join(apps[:5])}, and others."

    except Exception as e:
        return f"Error listing applications: {str(e)}"

available_tools = {
    "launch_application": launch_application,
    "describe_desktop": describe_desktop,
    "list_installed_applications": list_installed_applications
}

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
}]

# 1. Load the model into memory exactly ONCE when the OS boots up.
# Do not put this inside the speak() function, or it will load the model every time!
print("[SYSTEM] Loading Neural Voice...")
voice_model = PiperVoice.load("en_US-lessac-medium.onnx")
print("[SYSTEM] Voice ready.")

def speak(text: str):
    """Converts text to neural speech and plays it."""
    print(f"\n[Agent]: {text}")
    
    # We use Linux's /tmp directory because it lives in RAM, making it blisteringly fast
    temp_audio_path = "/tmp/agent_response.wav"
    
    try:
        # 2. Synthesize the text into a WAV file
        with wave.open(temp_audio_path, "wb") as wav_file:
            voice_model.synthesize_wav(text, wav_file)
            
        # 3. Play the audio using ALSA (built into Fedora)
        # The -q flag keeps the terminal clean from audio playback logs
        subprocess.run(["aplay", "-q", temp_audio_path], check=True)
        
    except Exception as e:
        print(f"[SYSTEM] Voice error: {e}")
        # Fallback to text if the audio system crashes
        pass

# ----------------------------------------
# 2. The Sensory Loop (Voice Input)
# ----------------------------------------
model = WhisperModel("medium.en", device="cpu", compute_type="int8")
def listen_and_transcribe():
    
    # 1. Record Audio (Simplified PyAudio Loop)
    CHUNK = 1024
    FORMAT = pyaudio.paInt16
    CHANNELS = 1
    RATE = 16000
    p = pyaudio.PyAudio()
    
    stream = p.open(format=FORMAT, channels=CHANNELS, rate=RATE, input=True, frames_per_buffer=CHUNK)
    print("\n[SYSTEM] Faster-Whisper is listening...")
    
    frames = []
    # Note: In a real Agent OS, you'd use a VAD library (like silero-vad) here 
    # to stop recording when the user stops talking. For testing, we record 4 seconds.
    for i in range(0, int(RATE / CHUNK * 4)): 
        data = stream.read(CHUNK)
        frames.append(data)
        
    stream.stop_stream()
    stream.close()
    p.terminate()

    # Save to a temporary buffer
    with wave.open("/tmp/temp.wav", 'wb') as wf:
        wf.setnchannels(CHANNELS)
        wf.setsampwidth(p.get_sample_size(FORMAT))
        wf.setframerate(RATE)
        wf.writeframes(b''.join(frames))

    # 2. Transcribe rapidly
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
                # Strip the .desktop extension to get the standard binary/app name
                app_name = filename.replace(".desktop", "")
                
                # Filter out complex sub-apps or KDE remnants if needed
                if "org.gnome." in app_name:
                    app_name = app_name.replace("org.gnome.", "")
                    
                installed_apps.append(app_name)
    except Exception as e:
        return ["firefox", "gnome-calculator", "nautilus"] # Fallback list
       
    return installed_apps 
    #return list(set(installed_apps)) # Remove duplicates

# Inject it into your orchestrator
live_app_list = get_installed_gui_apps()
print(get_installed_gui_apps())

# ----------------------------------------
# 3. The Orchestrator Loop
# ----------------------------------------
def run_agent():
    print("Agentic OS Initialized.")
    
    # 1. The System Prompt: Tell Llama to shut up and just be a router.
    messages = [
        {
            "role": "system", 
            "content": "You are a silent system orchestrator. Your ONLY job is to execute tool calls based on user intent. DO NOT output conversational text. DO NOT confirm actions. DO NOT be polite. If you need to use a tool, output ONLY the tool call. FORGET gedit and USE gnome-text-editor."
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
        
        # 2. The Execution Loop
        if message.get('tool_calls'):
            for tool_call in message['tool_calls']:
                tool_name = tool_call['function']['name']
                arguments = tool_call['function']['arguments']
                
                if tool_name in available_tools:
                    function_to_call = available_tools[tool_name]
                    result = function_to_call(**arguments) # Executes the tool
                    
                    # 3. THE MAGIC TRICK: Python speaks, not Llama!
                    # Do not pass the result back to Llama to summarize. 
                    # Just pass the hardcoded Python result directly to your TTS engine.
                    
                    print(f"\n[OS Feedback]: {result}")
                    # -> Insert your TTS function here: text_to_speech(result) <-
                    speak(result)
                    
                    # We still append the tool result to the message history 
                    # so Llama retains the context of what happened, but we SKIP 
                    # the second `ollama.chat()` call entirely.
                    #messages.append({
                        #"role": "tool",
                        #"content": result,
                        #"name": tool_name
                    #})
                    messages = [messages[0]]  # keep only the system prompt; stay a list
        #else:
            # If the user asked a general question that didn't require a tool,
            # (e.g. "What time is it?"), allow Llama to speak.
            #print(f"\nAgent: {message['content']}")
            # -> Insert your TTS function here: text_to_speech(message['content']) <-
            #speak(message['content'])

if __name__ == "__main__":
    try:
        run_agent()
    except KeyboardInterrupt:
        print("\n[SYSTEM] Shutting down Agentic OS...")

