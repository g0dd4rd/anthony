import ollama
import subprocess
import speech_recognition as sr

# ----------------------------------------
# 1. The Tool Executor
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

available_tools = {
    "launch_application": launch_application
}

tool_schema = [{
    "type": "function",
    "function": {
        "name": "launch_application",
        "description": "Launches a graphical application on the Linux desktop.",
        "parameters": {
            "type": "object",
            "properties": {
                "app_name": {
                    "type": "string",
                    "description": "The command name of the app (e.g., 'gnome-calculator', 'firefox')"
                }
            },
            "required": ["app_name"]
        }
    }
}]

# ----------------------------------------
# 2. The Sensory Loop (Voice Input)
# ----------------------------------------
def listen_and_transcribe():
    """Listens to the microphone and transcribes audio to text using local Whisper."""
    r = sr.Recognizer()
    
    with sr.Microphone() as source:
        # Dynamically adjust to ambient room noise
        r.adjust_for_ambient_noise(source, duration=0.5)
        print("\n[SYSTEM] Microphone active. Listening... ")
        
        try:
            # Captures audio until you stop speaking
            audio = r.listen(source, timeout=5, phrase_time_limit=15)
            print("[SYSTEM] Processing audio...")
            
            # Transcribe locally using the 'base.en' Whisper model (fast on CPU)
            # The first time this runs, it will download a ~140MB model file to your PC.
            text = r.recognize_whisper(audio, model="large-v3")
            
            # Ignore empty transcriptions
            if not text or text.isspace():
                return None
                
            print(f"You said: \"{text.strip()}\"")
            return text.strip()
            
        except sr.WaitTimeoutError:
            # Triggered if no speech is detected within the timeout
            return None
        except Exception as e:
            print(f"[SYSTEM] Audio error: {e}")
            return None

#import json
#import pyaudio
#from vosk import Model, KaldiRecognizer

#def listen_and_transcribe():
#    """Listens to the microphone and transcribes via local Vosk model."""
#    # Loads the model from the local folder named "model"
#    model = Model("./vosk-models/vosk-model-en-us-0.42-gigaspeech/")
#    
    # 16000 Hz is the standard sample rate for Vosk models
#    recognizer = KaldiRecognizer(model, 16000)
    
#    p = pyaudio.PyAudio()
#    
    # Open the microphone stream
#    stream = p.open(format=pyaudio.paInt16, 
#                    channels=1, 
#                    rate=16000, 
#                    input=True, 
#                    frames_per_buffer=8000)
    
#    stream.start_stream()
#    print("\n[SYSTEM] Vosk is listening... (Speak now)")
    
#    try:
#        while True:
            # Read audio data in small chunks
#            data = stream.read(4000, exception_on_overflow=False)
            
            # AcceptWaveform acts as Voice Activity Detection. 
            # It returns True when it detects a natural pause in your speech!
#            if recognizer.AcceptWaveform(data):
                # Extract the JSON result
#                result = json.loads(recognizer.Result())
#                text = result.get("text", "")
                
#                if text:
#                    print(f"You said: \"{text}\"")
                    
                    # Clean up the audio stream before returning
#                    stream.stop_stream()
#                    stream.close()
#                    p.terminate()
                    
#                    return text
                    
#    except KeyboardInterrupt:
#        stream.stop_stream()
#        stream.close()
#        p.terminate()
#        return None

# ----------------------------------------
# 3. The Orchestrator Loop
# ----------------------------------------
def run_agent():
    print("Agentic OS Initialized. (Press Ctrl+C to quit)")
    messages = []
    
    while True:
        # Replaced input() with our voice function
        user_input = listen_and_transcribe()
        
        # If the user didn't say anything, restart the listening loop
        if not user_input:
            continue
            
        messages.append({"role": "user", "content": user_input})
        
        # Query Llama 3.2
        response = ollama.chat(
            model='llama3.2',
            messages=messages,
            tools=tool_schema
        )
        
        message = response['message']
        messages.append(message)
        
        # Check for tool execution
        if message.get('tool_calls'):
            for tool_call in message['tool_calls']:
                tool_name = tool_call['function']['name']
                arguments = tool_call['function']['arguments']
                
                if tool_name in available_tools:
                    function_to_call = available_tools[tool_name]
                    result = function_to_call(**arguments)
                    
                    print(f"[SYSTEM] Tool Result: {result}")
                    
                    messages.append({
                        "role": "tool",
                        "content": result,
                        "name": tool_name
                    })
                    
                    final_response = ollama.chat(
                        model='llama3.2',
                        messages=messages
                    )
                    
                    print(f"\nAgent: {final_response['message']['content']}")
                    messages.append(final_response['message'])
        else:
            print(f"\nAgent: {message['content']}")

if __name__ == "__main__":
    try:
        run_agent()
    except KeyboardInterrupt:
        print("\n[SYSTEM] Shutting down Agentic OS...")

