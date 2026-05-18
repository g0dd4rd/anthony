import os
import re
import subprocess
import time
import wave
import collections

import numpy as np
import sounddevice  # noqa: F401 — suppresses ALSA verbose errors before pyaudio init
import pyaudio
import torch
from faster_whisper import WhisperModel
from piper.voice import PiperVoice

from utils import log_and_print

# ----------------------------------------
# TTS - Neural Voice
# ----------------------------------------
log_and_print("[SYSTEM] Loading Neural Voice...")
voice_model = PiperVoice.load("en_US-lessac-medium.onnx")
log_and_print("[SYSTEM] Voice ready.")


def strip_markdown(text: str) -> str:
    """Remove markdown formatting from text for TTS."""
    text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)
    text = re.sub(r'__(.+?)__', r'\1', text)
    text = re.sub(r'\*(.+?)\*', r'\1', text)
    text = re.sub(r'_(.+?)_', r'\1', text)
    text = re.sub(r'`(.+?)`', r'\1', text)
    text = re.sub(r'^#+\s*', '', text, flags=re.MULTILINE)
    text = re.sub(r'^\s*[-*]\s+', '', text, flags=re.MULTILINE)
    text = re.sub(r'^\s*\d+\.\s+', '', text, flags=re.MULTILINE)
    return text


_TTS_FILLERS = ["Okay,", "Done,", "Alright,", "Sure,"]
_tts_filler_index = 0


def _pad_short_text(text: str) -> str:
    """Pad short text with a filler prefix to avoid piper mispronunciation."""
    global _tts_filler_index
    if len(text.split()) < 5:
        filler = _TTS_FILLERS[_tts_filler_index % len(_TTS_FILLERS)]
        _tts_filler_index += 1
        text = f"{filler} {text[0].lower()}{text[1:]}"
    if not text.endswith(('.', '!', '?')):
        text += '.'
    return text


def speak(text: str):
    """Converts text to neural speech and plays it."""
    log_and_print(f"\n[Agent]: {text}")

    if not text or text.strip() == "":
        log_and_print(f"[SYSTEM] Skipping TTS - empty text", level='warning')
        return

    clean_text = strip_markdown(text)
    clean_text = _pad_short_text(clean_text)

    temp_audio_path = "/tmp/agent_response.wav"
    try:
        with wave.open(temp_audio_path, "wb") as wav_file:
            voice_model.synthesize_wav(clean_text, wav_file)
        subprocess.run(["aplay", "-q", temp_audio_path], check=True)
    except Exception as e:
        log_and_print(f"[SYSTEM] Voice error: {e}", level='error')


# ----------------------------------------
# STT - Whisper + Silero VAD
# ----------------------------------------
log_and_print("[SYSTEM] Loading Whisper model...")
whisper_model = WhisperModel("medium.en", device="cpu", compute_type="int8")

log_and_print("[SYSTEM] Loading Silero VAD model...")
vad_model, vad_utils = torch.hub.load(
    repo_or_dir='snakers4/silero-vad',
    model='silero_vad',
    force_reload=False,
    onnx=False
)
log_and_print("[SYSTEM] VAD model loaded.")

VAD_THRESHOLD = 0.5
SILENCE_DURATION = 1.0
MIN_SPEECH_DURATION = 0.5
PRE_SPEECH_BUFFER = 0.3


def is_speech(audio_chunk, vad_model, rate=16000, threshold=0.5):
    """Check if audio chunk contains speech using Silero VAD."""
    try:
        audio_int16 = np.frombuffer(audio_chunk, dtype=np.int16)
        audio_float32 = audio_int16.astype(np.float32) / 32768.0
        audio_tensor = torch.from_numpy(audio_float32)
        speech_prob = vad_model(audio_tensor, rate).item()
        return speech_prob > threshold
    except Exception:
        return True


def get_default_input_device():
    """Get the current system default input device index."""
    try:
        p = pyaudio.PyAudio()
        default_device_info = p.get_default_input_device_info()
        device_index = default_device_info['index']
        device_name = default_device_info['name']
        log_and_print(f"[AUDIO] Using input device: {device_name} (index {device_index})")
        p.terminate()
        return device_index
    except Exception as e:
        log_and_print(f"[AUDIO] Warning: Could not get default input device: {e}", level='warning')
        log_and_print(f"[AUDIO] Falling back to system default")
        return None


def listen_and_transcribe():
    """VAD-based continuous listening."""
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
            frames_per_buffer=CHUNK
        )
    except Exception as e:
        log_and_print(f"[AUDIO] Error opening device {device_index}: {e}", level='error')
        log_and_print(f"[AUDIO] Retrying with system default...")
        stream = p.open(
            format=FORMAT,
            channels=CHANNELS,
            rate=RATE,
            input=True,
            frames_per_buffer=CHUNK
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

                            temp_path = "/tmp/vad_recording.wav"
                            p_temp = pyaudio.PyAudio()
                            with wave.open(temp_path, 'wb') as wf:
                                wf.setnchannels(CHANNELS)
                                wf.setsampwidth(p_temp.get_sample_size(FORMAT))
                                wf.setframerate(RATE)
                                wf.writeframes(b''.join(frames))
                            p_temp.terminate()

                            whisper_start = time.time()
                            segments, info = whisper_model.transcribe(
                                temp_path,
                                beam_size=5,
                                temperature=0.2,
                                word_timestamps=True,
                                vad_filter=True,
                                vad_parameters=dict(min_silence_duration_ms=500),
                                initial_prompt="Commands for opening files, applications, and websites. Files may have spaces in names like 'bugs and ideas.txt' or 'practical presentation advice.txt'."
                            )
                            whisper_elapsed = time.time() - whisper_start

                            text = "".join([segment.text for segment in segments]).strip()
                            log_and_print(f'⏱️  Whisper transcription: {whisper_elapsed:.2f}s')
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
