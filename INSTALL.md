# Installation Guide

## Quick Install

Run the automated installation script:

```bash
cd ~/anthony
./install.sh
```

The script will:
1. Install system packages (ALSA, PortAudio, PipeWire utils, playerctl)
2. Install Python packages (PyAudio, Whisper, Piper, MCP, sentence-transformers, etc.)
3. Install Anthony MCP server (GNOME extension + MCP bridge)
4. Download Piper voice model
5. Enable GNOME accessibility (required for dialog detection)
6. Verify all dependencies

## What Gets Installed

### System Packages (via dnf)
- `alsa-utils` - Audio playback (aplay for TTS)
- `portaudio-devel` - Audio I/O library (required by PyAudio)
- `python3-devel` - Python development headers
- `pipewire-utils` - Volume control (pactl)
- `playerctl` - Media player control (MPRIS)

### Python Packages (via pip)
- `faster-whisper` - Speech-to-text (Whisper medium.en)
- `piper-tts` - Neural text-to-speech
- `torch` - PyTorch (for Silero VAD + sentence-transformers)
- `sentence-transformers` - Semantic embeddings for tool routing
- `pyaudio` - Microphone recording
- `sounddevice` - ALSA warning suppression
- `numpy` - Numerical operations
- `requests` - HTTP calls to llama-server
- `webcolors` - Color name lookup for pick_color
- `mcp` - Model Context Protocol client
- `dogtail` - GNOME accessibility / dialog handling
- `parse` - Pattern matching for command pipeline
- `torchaudio` - Audio processing (required by Silero VAD)

### Anthony MCP
- GNOME Shell extension for window/input/settings/media control
- Python MCP server wrapping the D-Bus interface
- System control tools (battery, brightness, power profile, lock, power actions)

### Models
- **Piper en_US-lessac-medium** - Neural voice (~60MB, downloaded by install script)
- **Whisper medium.en** - STT (~1.5GB, auto-downloads on first run)
- **Silero VAD** - Voice activity detection (~2MB, auto-downloads on first run)
- **all-MiniLM-L6-v2** - Sentence embeddings (~80MB, auto-downloads on first run)

You also need a Gemma 4 model running via llama-server (not installed by this script). See `start_llama_server.sh`.

## Manual Installation

If you prefer to install manually or the script fails:

### 1. System Packages
```bash
sudo dnf install -y alsa-utils portaudio-devel python3-devel pipewire-utils playerctl
```

### 2. Python Packages
```bash
pip install sounddevice pyaudio faster-whisper piper-tts mcp torch torchaudio numpy \
    sentence-transformers requests webcolors dogtail parse
```

### 3. Anthony MCP
```bash
git clone https://github.com/g0dd4rd/anthony-mcp.git ~/anthony-mcp
cd ~/anthony-mcp && ./install.sh
```

### 4. Piper Voice Model
```bash
cd ~/anthony
python3 -m piper.download_voices --download-dir . en_US-lessac-medium
```

### 5. Enable Accessibility
```bash
gsettings set org.gnome.desktop.interface toolkit-accessibility true
```

### 6. llama-server (Gemma 4)

Anthony uses Gemma 4 as its LLM for conversation mode and vision. It runs via llama-server with Vulkan GPU acceleration.

#### Build llama.cpp

```bash
git clone https://github.com/ggerganov/llama.cpp.git ~/llama.cpp
cd ~/llama.cpp
cmake -B build -DGGML_VULKAN=ON
cmake --build build --config Release -j$(nproc)
```

#### Download and convert the model

Download a Gemma 4 model from [Hugging Face](https://huggingface.co/google) in safetensors format. Two recommended variants:

| Variant | Quantization | GGUF size | Speed |
|---------|-------------|-----------|-------|
| **Gemma 4 E2B** | Q8_0 | ~3GB | ~12-15 tok/s |
| **Gemma 4 E4B** | Q4_K_M | ~5GB | ~6-7 tok/s |

Convert and quantize (example for E4B):

```bash
mkdir -p ~/models

# Convert HF safetensors to GGUF
python3 ~/llama.cpp/convert_hf_to_gguf.py <model_dir> --outfile ~/models/gemma4-e4b.gguf

# Quantize the base model
~/llama.cpp/build/bin/llama-quantize ~/models/gemma4-e4b.gguf ~/models/gemma4-e4b-q4km.gguf Q4_K_M

# Convert and quantize the vision projector (for screen description)
python3 ~/llama.cpp/convert_hf_to_gguf.py <model_dir> --mmproj --outfile ~/models/mmproj-gemma4-e4b.gguf
~/llama.cpp/build/bin/llama-quantize ~/models/mmproj-gemma4-e4b.gguf ~/models/mmproj-gemma4-e4b-q8.gguf Q8_0
```

#### Start the server

```bash
./start_llama_server.sh          # default: E2B
./start_llama_server.sh e4b      # E4B variant
```

The orchestrator auto-starts llama-server if it's not already running. To change model paths or GPU settings, edit the `LLAMA_SERVER_CONFIG` section in `orchestrator.py`.

## Verification

```bash
# Check commands
which python3 pip anthony-mcp aplay pactl playerctl

# Check Python modules
python3 -c "import sounddevice, pyaudio, faster_whisper, piper, mcp, torch, torchaudio, \
    sentence_transformers, requests, webcolors, dogtail, parse"

# Check Piper model
ls -lh ~/anthony/en_US-lessac-medium.onnx*

# Check accessibility
gsettings get org.gnome.desktop.interface toolkit-accessibility

# Check llama-server
curl -s http://localhost:8081/health
```

## First Run

```bash
cd ~/anthony
./orchestrator.py
```

First run will auto-download Whisper, Silero VAD, and sentence-transformer models.

## Troubleshooting

### PyAudio build fails
```bash
sudo dnf install portaudio-devel python3-devel
pip install --upgrade pip setuptools wheel
pip install pyaudio
```

### MCP server not found
```bash
cd ~/anthony-mcp && pip install -e mcp-server
which anthony-mcp  # Should return a path
```

### Accessibility not working
```bash
gsettings set org.gnome.desktop.interface toolkit-accessibility true
# May need to log out/in for full effect
```

## System Requirements

- **OS**: Fedora (or compatible RPM-based distro)
- **RAM**: 16GB+ recommended
- **GPU**: Vulkan-capable (tested on Intel Arc A770M)
- **Disk**: ~5GB free (for voice/embedding models)
- **Audio**: Working microphone and speakers
- **Desktop**: GNOME with Wayland or X11

## Uninstallation

```bash
# Python packages
pip uninstall sounddevice pyaudio faster-whisper piper-tts mcp torch torchaudio numpy \
    sentence-transformers requests webcolors dogtail parse

# MCP server
pip uninstall anthony-mcp

# System packages (optional)
sudo dnf remove portaudio-devel python3-devel

# Models and caches
rm -rf ~/anthony/en_US-lessac-medium.onnx*
rm -rf ~/.cache/huggingface
rm -rf ~/.cache/torch
```
