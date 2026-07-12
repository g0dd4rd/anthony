import collections
import os
import re
import subprocess
import time
import wave

import numpy as np
import pyaudio
import sounddevice  # noqa: F401 — suppresses ALSA verbose errors before pyaudio init
import torch

torch.backends.nnpack.enabled = False
from faster_whisper import WhisperModel

from utils import log_and_print

# ----------------------------------------
# TTS engine selection
# ----------------------------------------
_tts_engine = "neural"
_piper_voice = None


def init_tts(engine="neural"):
    global _tts_engine, _piper_voice
    _tts_engine = engine
    if engine == "neural":
        from piper.voice import PiperVoice

        model_name = "en_US-lessac-medium"
        model_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), f"{model_name}.onnx")
        if not os.path.isfile(model_path):
            log_and_print("[SYSTEM] Voice model not found, downloading...")
            from pathlib import Path

            from piper.download_voices import download_voice

            download_voice(model_name, Path(os.path.dirname(model_path)))
        log_and_print("[SYSTEM] Loading Piper neural voice...")
        _piper_voice = PiperVoice.load(model_path)
        log_and_print("[SYSTEM] Piper voice ready.", console=False)
    else:
        log_and_print("[SYSTEM] TTS: espeak-ng + mbrola")


def strip_markdown(text: str) -> str:
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    text = re.sub(r"__(.+?)__", r"\1", text)
    text = re.sub(r"\*(.+?)\*", r"\1", text)
    text = re.sub(r"_(.+?)_", r"\1", text)
    text = re.sub(r"`(.+?)`", r"\1", text)
    text = re.sub(r"^#+\s*", "", text, flags=re.MULTILINE)
    text = re.sub(r"^\s*[-*]\s+", "", text, flags=re.MULTILINE)
    text = re.sub(r"^\s*\d+\.\s+", "", text, flags=re.MULTILINE)
    return text


def _speak_espeak(text):
    subprocess.run(
        ["espeak-ng", "-v", "mb-us1", "-s", "160", "-p", "50", text],
        check=True,
    )


def _speak_piper(text):
    temp_path = os.path.join(os.environ.get("XDG_RUNTIME_DIR", "/tmp"), "anthony_tts.wav")
    with wave.open(temp_path, "wb") as wav_file:
        _piper_voice.synthesize_wav(text, wav_file)
    subprocess.run(["aplay", "-q", temp_path], check=True)


def speak(text: str):
    log_and_print(f"\n[Agent]: {text}")

    if not text or text.strip() == "":
        log_and_print("[SYSTEM] Skipping TTS - empty text", level="warning")
        return

    clean_text = strip_markdown(text)

    try:
        synth_start = time.time()
        if _tts_engine == "neural":
            _speak_piper(clean_text)
        else:
            _speak_espeak(clean_text)
        elapsed = time.time() - synth_start
        log_and_print(f"[TIMING] TTS ({_tts_engine}): {elapsed:.2f}s", console=False)
    except Exception as e:
        log_and_print(f"[SYSTEM] Voice error: {e}", level="error")


# ----------------------------------------
# STT - Whisper + Silero VAD
# ----------------------------------------
log_and_print("[SYSTEM] Loading Whisper model...")
whisper_model = WhisperModel("medium.en", device="cpu", compute_type="int8")

log_and_print("[SYSTEM] Loading Silero VAD model...")
_vad_cache = os.path.join(torch.hub.get_dir(), "snakers4_silero-vad_master")
if os.path.isdir(_vad_cache):
    vad_model, vad_utils = torch.hub.load(
        repo_or_dir=_vad_cache, model="silero_vad", source="local", onnx=True
    )
else:
    vad_model, vad_utils = torch.hub.load(
        repo_or_dir="snakers4/silero-vad", model="silero_vad", force_reload=False, onnx=True
    )
log_and_print("[SYSTEM] VAD model loaded.", console=False)

VAD_THRESHOLD = 0.5
SILENCE_DURATION = 0.5
MIN_SPEECH_DURATION = 0.5
PRE_SPEECH_BUFFER = 0.3


def is_speech(audio_chunk, vad_model, rate=16000, threshold=0.5):
    try:
        audio_int16 = np.frombuffer(audio_chunk, dtype=np.int16)
        audio_float32 = audio_int16.astype(np.float32) / 32768.0
        audio_tensor = torch.from_numpy(audio_float32)
        speech_prob = vad_model(audio_tensor, rate).item()
        return speech_prob > threshold
    except Exception:
        return True


def check_audio_health():
    try:
        result = subprocess.run(
            ["pactl", "get-sink-mute", "@DEFAULT_SINK@"], capture_output=True, text=True, timeout=5
        )
        output_muted = "yes" in result.stdout.lower()
        if output_muted:
            log_and_print("[AUDIO] Output is muted, unmuting to deliver warnings")
            subprocess.run(["pactl", "set-sink-mute", "@DEFAULT_SINK@", "0"], timeout=5)
    except Exception as e:
        log_and_print(f"[AUDIO] Could not check output mute state: {e}", level="warning")

    try:
        result = subprocess.run(
            ["pactl", "get-source-mute", "@DEFAULT_SOURCE@"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        mic_muted = "yes" in result.stdout.lower()
        if mic_muted:
            log_and_print("[AUDIO] Microphone is muted!", level="warning")
            speak("Warning: your microphone is muted. Please unmute it.")
            return False
    except Exception as e:
        log_and_print(f"[AUDIO] Could not check mic mute state: {e}", level="warning")

    try:
        p = pyaudio.PyAudio()
        p.get_default_input_device_info()
        p.terminate()
    except Exception:
        log_and_print("[AUDIO] No microphone device found!", level="warning")
        speak("Warning: no microphone detected. Please connect one.")
        return False

    return True


def get_default_input_device():
    try:
        p = pyaudio.PyAudio()
        default_device_info = p.get_default_input_device_info()
        device_index = default_device_info["index"]
        device_name = default_device_info["name"]
        log_and_print(
            f"[AUDIO] Using input device: {device_name} (index {device_index})", console=False
        )
        p.terminate()
        return device_index
    except Exception as e:
        log_and_print(f"[AUDIO] Warning: Could not get default input device: {e}", level="warning")
        log_and_print("[AUDIO] Falling back to system default")
        return None


def listen_and_transcribe():
    CHUNK = 512
    FORMAT = pyaudio.paInt16
    CHANNELS = 1
    RATE = 16000

    device_index = get_default_input_device()

    p = pyaudio.PyAudio()

    try:
        stream = p.open(
            format=FORMAT,
            channels=CHANNELS,
            rate=RATE,
            input=True,
            input_device_index=device_index,
            frames_per_buffer=CHUNK,
        )
    except Exception as e:
        log_and_print(f"[AUDIO] Error opening device {device_index}: {e}", level="error")
        log_and_print("[AUDIO] Retrying with system default...")
        stream = p.open(
            format=FORMAT, channels=CHANNELS, rate=RATE, input=True, frames_per_buffer=CHUNK
        )

    log_and_print("\n🎤 [VAD] Listening...")

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
                    log_and_print("🔴 Recording...")
            else:
                frames.append(data)
                if speech_detected:
                    silence_chunks = 0
                else:
                    silence_chunks += 1
                    if silence_chunks >= silence_threshold:
                        duration = len(frames) * CHUNK / RATE
                        if duration >= MIN_SPEECH_DURATION:
                            log_and_print("⏹️  Processing...")
                            stream.stop_stream()
                            stream.close()
                            p.terminate()

                            audio_data = (
                                np.frombuffer(b"".join(frames), dtype=np.int16).astype(np.float32)
                                / 32768.0
                            )

                            whisper_start = time.time()
                            segments, info = whisper_model.transcribe(
                                audio_data,
                                beam_size=5,
                                temperature=0.2,
                                word_timestamps=True,
                                vad_filter=True,
                                vad_parameters=dict(min_silence_duration_ms=500),
                                initial_prompt=(
                                    "Commands for opening files,"
                                    " applications, and websites."
                                    " Files may have spaces in names"
                                    " like 'bugs and ideas.txt' or"
                                    " 'practical presentation"
                                    " advice.txt'."
                                ),
                            )
                            whisper_elapsed = time.time() - whisper_start

                            text = "".join([segment.text for segment in segments]).strip()
                            log_and_print(
                                f"⏱️  Whisper transcription: {whisper_elapsed:.2f}s", console=False
                            )
                            log_and_print(f'✅ You said: "{text}"\n')
                            return text
                        else:
                            recording = False
                            frames = []
                            silence_chunks = 0

    except KeyboardInterrupt:
        log_and_print("\n[VAD] Ctrl+C detected, shutting down...")
        stream.stop_stream()
        stream.close()
        p.terminate()
        raise
