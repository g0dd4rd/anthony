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

You also need a Gemma 4 model running via llama-server. Use `./build_llama.sh` and `./download_model.sh` to set these up.

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

### 6. llama.cpp + LLM Model

```bash
cd ~/anthony
./build_llama.sh        # auto-detects CUDA / ROCm / Vulkan / CPU
./download_model.sh     # downloads Gemma 4 E2B QAT from Unsloth (no login required)
./download_model.sh -m e4b  # or E4B for higher quality (larger)
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
