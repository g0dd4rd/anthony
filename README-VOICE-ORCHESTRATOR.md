# Voice-Driven Desktop Orchestrator - Quick Guide

## 🎯 Which Version Should I Use?

### ⭐ **RECOMMENDED: VAD Version**
**File:** `voice-driven-orchestrator-mcp-vad.py`

**Advantages:**
- ✅ No time limits - speak as long as you need
- ✅ Automatically detects when you start/stop speaking  
- ✅ 3-5x faster vision analysis
- ✅ Handles unsaved files properly
- ✅ Natural conversation flow

**Disadvantages:**
- Requires `torch` library (~200MB)
- VAD model downloads on first run (~2MB)

**Best for:** Daily use, complex commands, natural interaction

---

### 🔧 **Improved Version (No VAD)**
**File:** `voice-driven-orchestrator-mcp-improved.py`

**Advantages:**
- ✅ 3-5x faster vision analysis
- ✅ Handles unsaved files properly
- ✅ No extra dependencies
- ✅ Smaller memory footprint

**Disadvantages:**
- ❌ Still has 4-second input limit
- ❌ Must finish speaking within time window

**Best for:** Testing, systems without torch, simple commands

---

### 📦 **Original Version**
**File:** `voice-driven-orchestrator-mcp.py`

**Use only if:**
- The improved versions have issues
- You need to debug something
- You prefer the original behavior

---

## 🚀 Installation

### 1. Install Dependencies

```bash
# Core dependencies (required for all versions)
pip install ollama pyaudio faster-whisper piper-tts mcp

# VAD dependency (only for VAD version)
pip install torch
```

### 2. Download Models

```bash
# Vision model (gemma4)
ollama pull gemma4:e4b

# Whisper model (if not already downloaded)
# Will auto-download on first run of faster-whisper
```

### 3. Verify MCP Connection

```bash
# Test gnome-desktop-mcp extension
cd ~/anthony
./test_gnome_mcp.py
```

Should see:
```
✅ Ping result: Extension is alive
✅ Found 1 open windows
✅ Found 1 monitor(s)
```

---

## 🎤 Testing Voice Input

### Test VAD (Recommended)

```bash
cd ~/anthony
./voice_vad_listener.py
```

Speak naturally when you see:
```
🎤 [VAD] Listening... (speak anytime)
```

Expected behavior:
1. You start speaking → sees "🔴 Recording..."
2. You stop speaking (1 sec silence) → sees "⏹️ Silence detected, processing..."
3. Shows transcription: "✅ Transcribed: [your words]"

**Good signs:**
- Recording starts within 0.5s of speaking
- Stops within 1-2s after you stop
- Captures full sentence even if long

**Issues?**
- "Too short" warnings → Increase `MIN_SPEECH_DURATION` (line 19)
- Doesn't stop → Decrease `SILENCE_DURATION` (line 18)
- Cuts off early → Increase `SILENCE_DURATION`

### Test Fixed Duration (Fallback)

```bash
cd ~/anthony
./voice-driven-orchestrator-mcp-improved.py
```

You have exactly 4 seconds to speak after "Faster-Whisper is listening..."

---

## 📊 Performance Benchmarks

Run the vision speed test:

```bash
cd ~/anthony
./test_vision_speed.py
```

Expected results (P1 Gen 7 with Intel Arc):
```
Gemma4 + verbose:     8-15 seconds
Gemma4 + concise:     2-4 seconds   ← Using this
LLaVA:                3-5 seconds
Moondream:            1-2 seconds
```

---

## 🎮 Usage Examples

### Launch Application
Say: **"Launch Firefox"** or **"Open calculator"**

### Describe Desktop
Say: **"Describe the desktop"** or **"What's on screen"**

Response: 2-3 sentence description of visible apps

### Window Management
Say: **"Focus Firefox"** → Brings window to front  
Say: **"Close text editor"** → Closes normally  
Say: **"Force close text editor"** → Closes without saving

### List Windows
Say: **"List open windows"** → Shows all window titles

### Type Text
Say: **"Type hello world"** → Types into focused window

### Keyboard Shortcuts
Say: **"Press Ctrl+C"** → Copies selected text  
Say: **"Press Super+L"** → Locks screen

---

## 🐛 Troubleshooting

### VAD doesn't start
```bash
# Check if torch is installed
python3 -c "import torch; print(torch.__version__)"

# Reinstall if needed
pip install --upgrade torch
```

### Vision is still slow
```bash
# Check GPU usage
ollama ps

# Should show "gemma4:e4b" with GPU layers
# If not, check Intel drivers:
sudo dnf install intel-opencl intel-level-zero
```

### MCP tools fail
```bash
# Verify extension is running
gnome-extensions info desktop-automation@gnomemcp.github.io

# Should show: State: ACTIVE

# Test D-Bus connection
gdbus call --session --dest org.gnome.Shell \
  --object-path /io/github/gnomemcp/DesktopAutomation \
  --method io.github.gnomemcp.DesktopAutomation.Ping

# Should return: (true,)
```

### Audio issues
```bash
# List audio devices
arecord -l

# Test microphone
arecord -d 3 test.wav && aplay test.wav

# Check PyAudio
python3 -c "import pyaudio; p=pyaudio.PyAudio(); print(f'{p.get_device_count()} devices')"
```

---

## 📝 Configuration Tuning

### Adjust VAD Sensitivity

Edit `voice-driven-orchestrator-mcp-vad.py`:

```python
VAD_THRESHOLD = 0.5              # Lower = more sensitive (0.3-0.7)
SILENCE_DURATION = 1.0           # Seconds to wait before stopping (0.5-2.0)
MIN_SPEECH_DURATION = 0.5        # Minimum speech length (0.3-1.0)
PRE_SPEECH_BUFFER = 0.3          # Pre-buffer duration (0.1-0.5)
```

**For noisy environments:** Increase `VAD_THRESHOLD` to 0.6-0.7  
**For quiet environments:** Decrease to 0.3-0.4  
**For fast speakers:** Decrease `SILENCE_DURATION` to 0.5-0.8  
**For slow speakers:** Increase `SILENCE_DURATION` to 1.5-2.0

### Adjust Vision Speed

Edit line 137-146:

```python
options={
    'num_ctx': 2048,      # Lower = faster (1024-4096)
    'num_predict': 100,   # Max output tokens (50-200)
    'temperature': 0.3,   # Consistency (0.0-0.5)
    'num_gpu': 99,        # GPU layers (99 = max)
}
```

**For faster results:** Set `num_predict=50`, `num_ctx=1024`  
**For better quality:** Set `num_predict=150`, `num_ctx=4096`

---

## 📚 Documentation

- **`changes.md`** - Detailed changelog of all improvements
- **`IMPROVEMENTS.md`** - Technical deep-dive and optimization guide
- **`test_vision_speed.py`** - Benchmark vision model performance
- **`test_gnome_mcp.py`** - Test MCP extension connectivity

---

## 🆘 Getting Help

### Check logs
```bash
# GNOME Shell logs (for MCP issues)
journalctl --user -f -u gnome-shell

# Ollama logs (for vision issues)
journalctl -u ollama -f
```

### Common Issues

**"Too short" warnings repeatedly:**
- You might be in a noisy environment
- Increase `MIN_SPEECH_DURATION` to 0.3
- Or increase `SILENCE_DURATION` to 1.5

**Recording doesn't start:**
- Check microphone permissions
- Test: `arecord -d 2 test.wav`
- Adjust `VAD_THRESHOLD` lower (0.3)

**Vision takes 10+ seconds:**
- Check GPU usage: `intel_gpu_top`
- Verify drivers: `clinfo | grep Arc`
- Try smaller model: `ollama pull moondream:1.8b`

**Close doesn't work with dialogs:**
- Some apps use custom dialogs
- Try: "Force close [app name]"
- Fallback: "Press Alt+F4"

---

## 🎯 Quick Command Reference

| Say This | Does This |
|----------|-----------|
| "Launch Firefox" | Opens Firefox browser |
| "Describe desktop" | AI describes what's on screen |
| "List windows" | Shows all open windows |
| "Focus Firefox" | Brings Firefox to front |
| "Close text editor" | Closes (asks about unsaved) |
| "Force close text editor" | Closes without saving |
| "Type hello world" | Types text in focused app |
| "Press Ctrl C" | Copies selection |
| "Press Super L" | Locks screen |

---

**Made with ❤️ for seamless desktop automation**
