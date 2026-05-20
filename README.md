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
./orchestrator.py
```

The install script handles system packages, Python dependencies, the Piper voice model, and anthony-mcp setup. First run downloads the Whisper STT model (~1.5GB) and Silero VAD (~2MB) automatically.

llama-server with a Gemma 4 model must be running on port 8081. See `start_llama_server.sh` for the recommended launch command.

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
| "describe the screen" | Vision analysis via Gemma 4 |
| "what time is it" | Instant response (no LLM) |
| "set brightness to 70" | Screen brightness via MCP |

See [commands.txt](commands.txt) for the full command reference.

## How It Works

1. **Silero VAD** detects speech, **Faster-Whisper** transcribes it
2. **Short-circuit router** handles 20+ common patterns instantly (<100ms)
3. For everything else, **RAG** selects relevant tool namespaces, then **Gemma 4** plans and executes tool calls via the agentic loop
4. Tools execute through **anthony-mcp** (GNOME Shell extension) or direct system calls
5. **Piper TTS** speaks the result

The system is split into 10 Python modules (~3.4K lines). See [architecture.html](architecture.html) for the full data flow, dependency graph, and module details.

## Project Structure

```
orchestrator.py         Main entry point, server lifecycle, agent loop
command_router.py       Short-circuit patterns, RAG context, app auto-focus
llm_chain.py            Agentic LLM tool-calling loop
voice_io.py             VAD, STT (Whisper), TTS (Piper)
app_index.py            App indexing, window matching, RAG retrieval
conversation.py         Chat mode with conversation history
dialog_handler.py       Save dialog detection via AT-SPI
mcp_client.py           MCP protocol client
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
