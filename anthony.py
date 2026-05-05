import os
import json
import sys
import subprocess
import base64
import ollama
from vosk import Model, KaldiRecognizer
import pyaudio
from dogtail.rawinput import typeText, pressKey
from dogtail.tree import root
from datetime import datetime

# --- Configuration ---
MODEL_PATH = "/home/jprajzne/python/vosk-models/vosk-model-en-us-0.42-gigaspeech" # Path to the unzipped Vosk model folder
LLAMA_MODEL = "llava" # The Ollama multimodal model (ensure you ran 'ollama pull llava')
DOGTAIL_APP_NAME = "gnome-terminal-server"

# --- TTS Function ---
def speak(text):
    """Gives vocal feedback using the espeak-ng command line utility."""
    # -v: voice (e.g., english-us), -s: speed (words per minute)
    subprocess.run(["espeak-ng", "-v", "en-us", "-s", "140", text], check=False)
    print(f"[ASSISTANT]: {text}")

# --- AI Image Description Function ---
def describe_screen(image_path="screenshot.png"):
    """
    Captures the current screen and asks the local LLaVA model via Ollama
    to generate a description.
    """
    try:
        # 1. Capture the screen using scrot
        subprocess.run(["scrot", image_path], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        speak("Analyzing the screen now.")

        # 2. Prepare the image for Ollama API (Base64 encoding)
        with open(image_path, "rb") as f:
            image_data = f.read()
        encoded_image = base64.b64encode(image_data).decode("utf-8")

        # 3. Send image and prompt to local Ollama server
        response = ollama.chat(
            model=LLAMA_MODEL,
            messages=[
                {
                    "role": "user",
                    "content": "Describe the content of this image concisely. Focus on the main elements and any text visible.",
                    "images": [encoded_image],
                }
            ],
        )
       
        # 4. Extract and speak the description
        description = response['message']['content']
        speak(f"The screen shows: {description}")

    except FileNotFoundError:
        speak("Error: Please ensure the 'scrot' and 'ollama' commands are installed and in your system path.")
    except subprocess.CalledProcessError:
        speak("Error: Could not take a screenshot. Check permissions or the scrot installation.")
    except Exception as e:
        speak(f"Error during AI analysis. Is the Ollama service running? Error: {e}")
    finally:
        # Clean up the screenshot file
        if os.path.exists(image_path):
            os.remove(image_path)


# --- Command Execution Logic ---
def execute_command(command_text):
    """Parses transcribed text and executes the corresponding action."""
    print(f"Executing command: {command_text}")
    command_executed = False
   
    try:
        if "shutdown" in command_text:
            speak("Initiating system shutdown. Goodbye.")
            # D-Bus command to shut down the system
            subprocess.run(["dbus-send", "--system", "--type=method_call",
                            "--dest=org.freedesktop.login1", "/org/freedesktop/login1",
                            "org.freedesktop.login1.Manager.PowerOff", "boolean:true"], check=True)
            command_executed = True

        elif "open terminal" in command_text:
            subprocess.run(["gnome-terminal"], check=True)
            speak("Opening terminal emulator.")
            command_executed = True

        elif "describe screen" in command_text or "what is on the screen" in command_text:
            describe_screen()
            command_executed = True # Output is handled within describe_screen

        elif "type hello world" in command_text:
            # Dogtail/GUI interaction example
            app = root.application(DOGTAIL_APP_NAME)
            if app:
                typeText("Hello, World!")
                pressKey("Enter")
                speak("Typed the phrase and pressed enter.")
                command_executed = True
            else:
                speak(f"Error: Could not find the application named {DOGTAIL_APP_NAME}.")

        if command_executed and "describe screen" not in command_text:
            # Only give generic success if no vocal feedback was given above
            pass
        elif not command_executed:
            speak(f"I heard {command_text}, but the command was not recognized.")

    except subprocess.CalledProcessError:
        speak("The command failed to execute. Please check the system process status.")
    except Exception as e:
        speak(f"An unexpected error occurred during command execution: {e}")

# --- Vosk Setup and Main Loop (same as before) ---
if not os.path.exists(MODEL_PATH):
    print(f"Please download the Vosk model and unpack it to '{MODEL_PATH}'")
    sys.exit(1)

model = Model(MODEL_PATH)
rec = KaldiRecognizer(model, 16000)

p = pyaudio.PyAudio()
stream = p.open(format=pyaudio.paInt16,
                channels=1,
                rate=16000,
                input=True,
                frames_per_buffer=8000)

speak("Voice assistant initializing. I am now listening for commands.")

try:
    while True:
        data = stream.read(4000, exception_on_overflow=False) # Add error handling for buffer overflow
        if rec.AcceptWaveform(data):
            result = rec.Result()
            text = json.loads(result).get('text')
           
            if text:
                execute_command(text)
               
except KeyboardInterrupt:
    speak("Stopping voice assistant. Goodbye.")
except Exception as e:
    speak(f"A fatal error occurred: {e}")
finally:
    stream.stop_stream()
    stream.close()
    p.terminate()

