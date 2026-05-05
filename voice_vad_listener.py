#!/usr/bin/env python3
"""
VAD-based voice listener for continuous listening without time constraints.

Uses Silero VAD to detect when user starts/stops speaking, then transcribes with faster-whisper.
"""

import pyaudio
import wave
import numpy as np
import torch
from faster_whisper import WhisperModel
import collections
import time

class VADListener:
    """Voice Activity Detection based continuous listener"""

    def __init__(self, whisper_model: WhisperModel):
        self.whisper_model = whisper_model

        # Audio settings
        self.CHUNK = 512  # Smaller chunks for responsive VAD
        self.FORMAT = pyaudio.paInt16
        self.CHANNELS = 1
        self.RATE = 16000

        # VAD settings
        self.vad_model = None
        self.load_vad()

        # Speech detection parameters
        self.speech_threshold = 0.5      # Confidence threshold for speech
        self.silence_duration = 1.0      # Seconds of silence to stop recording
        self.min_speech_duration = 0.5   # Minimum speech duration to process
        self.pre_speech_buffer = 0.3     # Seconds to keep before speech starts

    def load_vad(self):
        """Load Silero VAD model"""
        try:
            # Download Silero VAD model
            self.vad_model, utils = torch.hub.load(
                repo_or_dir='snakers4/silero-vad',
                model='silero_vad',
                force_reload=False,
                onnx=False
            )
            self.get_speech_timestamps = utils[0]
            print("[VAD] Silero VAD model loaded successfully")
        except Exception as e:
            print(f"[VAD] Error loading VAD model: {e}")
            print("[VAD] Falling back to fixed-duration recording")
            self.vad_model = None

    def is_speech(self, audio_chunk):
        """Check if audio chunk contains speech using VAD"""
        if self.vad_model is None:
            return True  # Fallback: assume all audio is speech

        try:
            # Convert to float32 tensor
            audio_int16 = np.frombuffer(audio_chunk, dtype=np.int16)
            audio_float32 = audio_int16.astype(np.float32) / 32768.0
            audio_tensor = torch.from_numpy(audio_float32)

            # Get speech probability
            speech_prob = self.vad_model(audio_tensor, self.RATE).item()
            return speech_prob > self.speech_threshold

        except Exception as e:
            print(f"[VAD] Error in speech detection: {e}")
            return True  # Assume speech on error

    def listen_and_transcribe(self):
        """
        Listen continuously with VAD - starts recording on speech, stops on silence.
        Returns transcribed text.
        """
        p = pyaudio.PyAudio()
        stream = p.open(
            format=self.FORMAT,
            channels=self.CHANNELS,
            rate=self.RATE,
            input=True,
            frames_per_buffer=self.CHUNK
        )

        print("\n[VAD] Listening... (speak anytime)")

        # Pre-speech buffer (keeps last N chunks before speech detected)
        buffer_size = int(self.pre_speech_buffer * self.RATE / self.CHUNK)
        pre_buffer = collections.deque(maxlen=buffer_size)

        # Recording state
        recording = False
        frames = []
        silence_chunks = 0
        silence_threshold = int(self.silence_duration * self.RATE / self.CHUNK)

        try:
            while True:
                data = stream.read(self.CHUNK, exception_on_overflow=False)

                is_speech = self.is_speech(data)

                if not recording:
                    # Not recording yet - buffer audio and wait for speech
                    pre_buffer.append(data)

                    if is_speech:
                        # Speech detected! Start recording
                        recording = True
                        frames = list(pre_buffer)  # Include buffered audio
                        silence_chunks = 0
                        print("[VAD] 🎤 Speech detected, recording...")

                else:
                    # Currently recording
                    frames.append(data)

                    if is_speech:
                        # Speech continues
                        silence_chunks = 0
                    else:
                        # Silence detected
                        silence_chunks += 1

                        if silence_chunks >= silence_threshold:
                            # Enough silence - stop recording
                            print("[VAD] 🔇 Silence detected, processing...")

                            # Check if we recorded enough speech
                            duration = len(frames) * self.CHUNK / self.RATE
                            if duration >= self.min_speech_duration:
                                # Stop and transcribe
                                stream.stop_stream()
                                stream.close()
                                p.terminate()

                                return self._transcribe_frames(frames)
                            else:
                                # Too short, ignore and keep listening
                                print(f"[VAD] ⚠️  Too short ({duration:.1f}s), ignoring...")
                                recording = False
                                frames = []
                                silence_chunks = 0

        except KeyboardInterrupt:
            stream.stop_stream()
            stream.close()
            p.terminate()
            return ""

    def _transcribe_frames(self, frames):
        """Transcribe recorded audio frames using faster-whisper"""
        # Save to temporary WAV file
        temp_path = "/tmp/vad_recording.wav"

        p = pyaudio.PyAudio()
        with wave.open(temp_path, 'wb') as wf:
            wf.setnchannels(self.CHANNELS)
            wf.setsampwidth(p.get_sample_size(self.FORMAT))
            wf.setframerate(self.RATE)
            wf.writeframes(b''.join(frames))
        p.terminate()

        # Transcribe with faster-whisper
        segments, info = self.whisper_model.transcribe(
            temp_path,
            beam_size=5,
            vad_filter=True,  # Additional VAD filtering during transcription
            vad_parameters=dict(min_silence_duration_ms=500)
        )

        text = "".join([segment.text for segment in segments]).strip()

        print(f'[VAD] You said: "{text}"')
        return text

    def listen_with_timeout(self, timeout_seconds=10):
        """
        Fallback method: Listen for speech with maximum timeout.
        Useful if you want to prevent infinite waiting.
        """
        p = pyaudio.PyAudio()
        stream = p.open(
            format=self.FORMAT,
            channels=self.CHANNELS,
            rate=self.RATE,
            input=True,
            frames_per_buffer=self.CHUNK
        )

        print(f"\n[VAD] Listening (max {timeout_seconds}s)...")

        pre_buffer = collections.deque(maxlen=int(0.3 * self.RATE / self.CHUNK))
        recording = False
        frames = []
        silence_chunks = 0
        silence_threshold = int(1.0 * self.RATE / self.CHUNK)

        start_time = time.time()

        try:
            while time.time() - start_time < timeout_seconds:
                data = stream.read(self.CHUNK, exception_on_overflow=False)
                is_speech = self.is_speech(data)

                if not recording:
                    pre_buffer.append(data)
                    if is_speech:
                        recording = True
                        frames = list(pre_buffer)
                        silence_chunks = 0
                        print("[VAD] 🎤 Recording...")
                else:
                    frames.append(data)
                    if is_speech:
                        silence_chunks = 0
                    else:
                        silence_chunks += 1
                        if silence_chunks >= silence_threshold:
                            duration = len(frames) * self.CHUNK / self.RATE
                            if duration >= self.min_speech_duration:
                                stream.stop_stream()
                                stream.close()
                                p.terminate()
                                return self._transcribe_frames(frames)
                            else:
                                recording = False
                                frames = []

            # Timeout reached
            print("[VAD] ⏱️  Timeout reached")
            stream.stop_stream()
            stream.close()
            p.terminate()

            if frames and len(frames) * self.CHUNK / self.RATE >= self.min_speech_duration:
                return self._transcribe_frames(frames)
            return ""

        except KeyboardInterrupt:
            stream.stop_stream()
            stream.close()
            p.terminate()
            return ""


# Example usage
if __name__ == "__main__":
    print("Loading Whisper model...")
    whisper_model = WhisperModel("medium.en", device="cpu", compute_type="int8")

    print("Initializing VAD listener...")
    listener = VADListener(whisper_model)

    print("\n" + "="*60)
    print("VAD Listener Test")
    print("="*60)
    print("Speak naturally - no time limits!")
    print("The system will start recording when you speak")
    print("and stop when you're silent for 1 second.")
    print("Press Ctrl+C to exit.\n")

    while True:
        try:
            text = listener.listen_and_transcribe()
            if text:
                print(f"\n✅ Transcribed: {text}\n")
            else:
                print("\n⚠️  No speech detected\n")
        except KeyboardInterrupt:
            print("\n\nExiting...")
            break
