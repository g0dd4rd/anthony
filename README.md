# Anthony

Voice-driven desktop orchestrator for GNOME, powered by local LLM inference.

Anthony listens to natural voice commands and controls the GNOME desktop -- managing windows, typing text, adjusting settings, launching apps, describing the screen, and more. Everything runs locally: speech recognition, language model, and text-to-speech. No cloud services, no API keys.

## Requirements

- Fedora (or RPM-based distro) with GNOME desktop
- 16GB+ RAM
- Vulkan-capable GPU (tested on Intel Arc A770M)
- Working microphone and speakers
- [anthony-mcp](https://github.com/g0dd4rd/anthony-mcp) -- GNOME Shell extension + MCP server

## Quick Start

```bash
git clone https://github.com/g0dd4rd/anthony.git ~/anthony
cd ~/anthony
./install.sh
./build_llama.sh
./download_model.sh
./orchestrator.py
```

The install script handles system packages, Python dependencies, the Piper voice model, and anthony-mcp setup. First run downloads the Whisper STT model (~1.5GB) and Silero VAD (~2MB) automatically.

`build_llama.sh` clones and builds llama.cpp with auto-detected GPU support (CUDA, ROCm, Vulkan, or CPU). `download_model.sh` downloads the Gemma 4 E2B model and vision projector (~3.4GB total) from Unsloth -- no Hugging Face login required. Run `./download_model.sh -m e4b` for the larger E4B variant, or `./download_model.sh --help` for all options.

The orchestrator auto-starts llama-server if it's not already running.

## Usage

Speak naturally -- Anthony uses voice activity detection (no wake word). Say "switch to chat mode" for open-ended conversation, "switch to command mode" to return to desktop control.

```
./orchestrator.py           # continuous listening
./orchestrator.py --ptt     # push-to-talk (press Enter to record)
./orchestrator.py --debug   # verbose logging
```

## Voice Commands

| Say this | Does this |
|----------|-----------|
| "open firefox" | Launches or focuses Firefox |
| "close terminal" | Closes the window (with save dialog handling) |
| "tile left" | Snaps the focused window to the left half |
| "take a screenshot" | Full-screen screenshot |
| "type hello world" | Types into the focused application |
| "mute" / "volume to 50" | Audio control via PulseAudio/MPRIS |
| "turn on dark mode" | Toggles GNOME dark theme |
| "next tab" / "previous tab" | App-aware tab switching |
| "copy" / "paste" / "select all" | App-aware clipboard shortcuts |
| "describe the screen" | Vision analysis via Gemma 4 |
| "what time is it" | Instant response (no LLM) |
| "set brightness to 70" | Screen brightness via MCP |

See [commands.txt](commands.txt) for the full command reference.

## How It Works

1. **Silero VAD** detects speech, **Faster-Whisper** transcribes it
2. **Pattern matching** tries exact command patterns via the `parse` library (~95 patterns across 13 command modules)
3. **Semantic fallback** uses sentence-transformer embeddings to find the closest matching command when no exact pattern matches
4. **LLM tool-calling** (Gemma 4) handles conversation mode and vision tasks (screen description, image analysis)
5. Tools execute through **anthony-mcp** (GNOME Shell extension) or direct system calls
6. **Piper TTS** speaks the result

The system is split across ~7.1K lines of Python. See [architecture.html](architecture.html) for the full data flow, dependency graph, and module details.

## Project Structure

```
orchestrator.py         Main entry point, server lifecycle, voice loop
command_matcher.py      Pattern matching + semantic fallback command routing
command_router.py       RAG context preparation, app auto-focus
llm_chain.py            Agentic LLM tool-calling loop (conversation/vision)
voice_io.py             VAD, STT (Whisper), TTS (Piper)
app_index.py            App indexing, window matching, embedding model
conversation.py         Chat mode with conversation history
dialog_handler.py       Save dialog detection via AT-SPI
mcp_client.py           MCP protocol client
commands/               13 command modules with ~95 @step pattern handlers
tools/facades.py        6 facade tools wrapping 36+ MCP operations
tools/standalone.py     8 standalone tools (datetime, apps, shortcuts, etc.)
config/                 Tool schemas, namespaces, prompts, aliases
shortcuts/              Curated keyboard shortcut data per app
```

## Documentation

- [commands.txt](commands.txt) -- Full voice command reference
- [architecture.html](architecture.html) -- Interactive architecture overview
- [INSTALL.md](INSTALL.md) -- Detailed installation guide
- [DEPENDENCIES.md](DEPENDENCIES.md) -- Complete dependency list
- [SETUP-OFFLINE.md](SETUP-OFFLINE.md) -- Offline setup for embedding model

## Related

- [anthony-mcp](https://github.com/g0dd4rd/anthony-mcp) -- GNOME Shell extension and MCP server
