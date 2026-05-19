# Installation Guide

## Quick Install

Run the automated installation script:

```bash
cd ~/anthony
./install.sh
```

The script will:
1. ✅ Install system packages (ALSA, PortAudio, Python dev headers)
2. ✅ Install Python packages (Ollama, PyAudio, Whisper, Piper, MCP, etc.)
3. ✅ Install Anthony MCP server
4. ✅ Install Ollama and download Gemma4 model
5. ✅ Download Piper voice model
6. ✅ Enable GNOME accessibility
7. ✅ Verify all dependencies

## What Gets Installed

### System Packages (via dnf)
- `alsa-utils` - Audio utilities
- `portaudio-devel` - Audio I/O library (required by PyAudio)
- `python3-devel` - Python development headers
- `nodejs` & `npm` - JavaScript runtime (for MCP server)

### Python Packages (via pip)
- `ollama` - Gemma4 LLM client
- `sounddevice` - ALSA warning suppression
- `pyaudio` - Audio recording
- `faster-whisper` - Speech recognition
- `piper-tts` - Neural text-to-speech
- `mcp` - Model Context Protocol
- `torch` - PyTorch (for Silero VAD)
- `numpy` - Numerical operations
- `dogtail` - GNOME accessibility/dialog handling

### Anthony MCP
- `anthony-mcp` - GNOME desktop automation server (installed from source)

### Models
- **Gemma4:e4b** - Vision + reasoning LLM (~9.6GB)
- **Piper en_US-lessac-medium** - Neural voice (~60MB)
- **Whisper medium.en** - Auto-downloads on first run (~1.5GB)
- **Silero VAD** - Auto-downloads on first run (~2MB)

## Manual Installation

If you prefer to install manually or the script fails:

### 1. System Packages
```bash
sudo dnf install -y alsa-utils portaudio-devel python3-devel nodejs npm
```

### 2. Python Packages
```bash
pip install ollama sounddevice pyaudio faster-whisper piper-tts mcp torch numpy dogtail
```

### 3. Anthony MCP
```bash
git clone https://github.com/g0dd4rd/anthony-mcp.git ~/anthony-mcp
cd ~/anthony-mcp && ./install.sh
```

### 4. Ollama + Gemma4
```bash
curl -fsSL https://ollama.com/install.sh | sh
ollama pull gemma4:e4b
```

### 5. Piper Voice Model
```bash
cd ~/anthony
wget https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/medium/en_US-lessac-medium.onnx
wget https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/medium/en_US-lessac-medium.onnx.json
```

### 6. Enable Accessibility
```bash
gsettings set org.gnome.desktop.interface toolkit-accessibility true
```

## Verification

Run verification checks manually:

```bash
# Check commands
which python3 pip node npm ollama anthony-mcp aplay

# Check Python modules
python3 -c "import ollama, sounddevice, pyaudio, faster_whisper, piper, mcp, torch, dogtail"

# Check Ollama models
ollama list | grep gemma4

# Check Piper model
ls -lh ~/anthony/en_US-lessac-medium.onnx*

# Check accessibility
gsettings get org.gnome.desktop.interface toolkit-accessibility
```

## First Run

After installation, run:

```bash
cd ~/anthony
./orchestrator.py
```

**First run will:**
- Download Whisper model (~1.5GB) - takes 2-5 minutes
- Download Silero VAD (~2MB) - takes a few seconds
- Verify accessibility is enabled
- Connect to Anthony MCP

## Troubleshooting

### PyAudio build fails
```bash
sudo dnf install portaudio-devel python3-devel
pip install --upgrade pip setuptools wheel
pip install pyaudio
```

### Ollama model not found
```bash
ollama pull gemma4:e4b
```

### MCP server not found
```bash
cd ~/anthony-mcp && pip install -e mcp-server
which anthony-mcp  # Should return a path
```

### Accessibility not working
```bash
# Enable it
gsettings set org.gnome.desktop.interface toolkit-accessibility true

# Verify
gsettings get org.gnome.desktop.interface toolkit-accessibility

# May need to log out/in for full effect
```

### ALSA warnings still appearing
Make sure `sounddevice` is imported before `pyaudio` in the script (already done in conversational version).

## System Requirements

- **OS**: Fedora (or compatible RPM-based distro)
- **RAM**: 16GB+ recommended (Gemma4 uses ~10GB)
- **Disk**: ~15GB free (for all models)
- **Audio**: Working microphone and speakers
- **Desktop**: GNOME (required for MCP and dogtail)

## Uninstallation

To remove everything:

```bash
# Python packages
pip uninstall ollama sounddevice pyaudio faster-whisper piper-tts mcp torch numpy dogtail

# MCP server
pip uninstall anthony-mcp

# Ollama (optional - removes all models)
sudo rm -rf /usr/local/bin/ollama ~/.ollama

# System packages (optional)
sudo dnf remove portaudio-devel python3-devel

# Models
rm -rf ~/anthony/en_US-lessac-medium.onnx*
rm -rf ~/.cache/huggingface
rm -rf ~/.cache/torch
```
