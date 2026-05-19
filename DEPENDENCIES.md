# Anthony Dependencies

## Python packages
| Package | Purpose |
|---|---|
| faster-whisper | Speech-to-text (Whisper model) |
| piper-tts | Text-to-speech |
| sentence-transformers | Semantic embedding for tool routing |
| torch | ML backend for sentence-transformers |
| numpy | Array operations |
| pyaudio | Microphone input |
| sounddevice | Audio device enumeration |
| requests | HTTP calls to llama-server |
| ollama | Vision model (fallback) |
| webcolors | Color name lookup for pick_color |
| mcp | MCP client (Model Context Protocol) |

## System packages (Fedora/RHEL)
| Package | Purpose |
|---|---|
| alsa-utils | `aplay` for audio playback |
| xdg-utils | `xdg-open` for opening URLs/files |
| upower | Battery status queries |
| brightnessctl | Screen and keyboard backlight control |
| localsearch | GNOME file indexing (Tracker) |
| procps-ng | `pgrep` / `kill` for process management |

## GNOME components
| Component | Purpose |
|---|---|
| gnome-shell | Desktop environment |
| anthony-mcp extension | D-Bus bridge for window/input/settings control |
| anthony-mcp MCP server | Python MCP server wrapping the D-Bus interface |

## AI models
| Model | Purpose | Location |
|---|---|---|
| gemma-4-e4b (or similar) | Tool-calling LLM | llama-server (port 8081) |
| faster-whisper medium.en | Speech-to-text | Downloaded on first run |
| piper en_US-lessac-medium | Text-to-speech | Local .onnx file |
| all-MiniLM-L6-v2 | Sentence embeddings for routing | Downloaded on first run |
| minicpm-v (via ollama) | Vision model for screen description | Ollama |
