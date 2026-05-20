# Anthony Dependencies

## Python packages
| Package | Purpose |
|---|---|
| faster-whisper | Speech-to-text (Whisper model) |
| piper-tts | Text-to-speech (Piper neural voice) |
| sentence-transformers | Semantic embedding for tool routing |
| torch | ML backend for Silero VAD + sentence-transformers |
| numpy | Array operations |
| pyaudio | Microphone input |
| sounddevice | Audio device enumeration / ALSA warning suppression |
| requests | HTTP calls to llama-server |
| webcolors | Color name lookup for pick_color |
| mcp | MCP client (Model Context Protocol) |
| dogtail | GNOME accessibility / dialog detection via AT-SPI |

## System packages (Fedora/RHEL)
| Package | Purpose |
|---|---|
| alsa-utils | `aplay` for TTS audio playback |
| portaudio-devel | Build dependency for PyAudio |
| pipewire-utils | `pactl` for volume control |
| playerctl | MPRIS media player control |
| xdg-utils | `xdg-open` for opening URLs/files |
| localsearch | GNOME file indexing (Tracker) |
| procps-ng | `pgrep` / `kill` for process management |

## GNOME components
| Component | Purpose |
|---|---|
| gnome-shell | Desktop environment |
| anthony-mcp extension | D-Bus bridge for window/input/settings/system control |
| anthony-mcp MCP server | Python MCP server wrapping the D-Bus interface |

## AI models
| Model | Purpose | Location |
|---|---|---|
| Gemma 4 E4B (Q4_K_M) | Tool-calling + vision LLM | llama-server on port 8081 (Vulkan GPU) |
| faster-whisper medium.en | Speech-to-text | Auto-downloads on first run (~1.5GB) |
| Piper en_US-lessac-medium | Text-to-speech | Local .onnx file (~60MB) |
| all-MiniLM-L6-v2 | Sentence embeddings for RAG routing | Auto-downloads on first run (~80MB) |
| Silero VAD | Voice activity detection | Auto-downloads on first run (~2MB) |
