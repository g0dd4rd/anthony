# ANTHONY.md — Project Map for AI Agents

> **Audience:** LLMs and AI coding agents.
> Read this file first to understand the codebase before making changes.
> It describes the project structure, data flow, design patterns, and key conventions.

## What This Project Is

Anthony is a voice-driven desktop orchestrator for GNOME/Linux. Users speak natural language commands to control windows, launch apps, manage audio, take screenshots, and more. It runs a local LLM (gemma4 via llama-server) for intent parsing and tool calling, with no cloud dependency.

## Architecture Overview

```
Voice Input (mic)
    │
    ▼
┌──────────────┐     ┌─────────────────┐
│  voice_io.py │     │  orchestrator.py │ ◄── entry point
│  (STT + TTS) │────►│  (main loop)     │
└──────────────┘     └────────┬─────────┘
                              │
              ┌───────────────┼───────────────┐
              ▼               ▼               ▼
     ┌────────────┐  ┌──────────────┐  ┌─────────────┐
     │ command_    │  │  commands/   │  │ conversation │
     │ matcher.py  │  │  (13 @step  │  │ .py          │
     │ (routing)   │  │   modules)  │  │ (chat mode)  │
     └─────┬──────┘  └──────┬───────┘  └──────┬──────┘
           │                │                  │
           ▼                ▼                  ▼
     ┌──────────────────────────┐     ┌──────────────┐
     │    tools/ (facades +     │     │  llm_chain   │
     │    standalone actions)   │     │  .py (LLM)   │
     └────────────┬─────────────┘     └──────────────┘
                  │ MCP protocol (stdio)
                  ▼
     ┌──────────────────────────┐
     │  anthony-mcp (separate   │
     │  repo — GNOME extension  │
     │  + MCP server)           │
     └──────────────────────────┘
```

## Request Flow

1. **Voice capture** — `voice_io.py` uses Silero VAD for continuous listening, then Whisper (faster-whisper) for transcription
2. **Mode routing** — `orchestrator.py` checks current mode: `command` or `conversation`
3. **Command path** — `command_matcher.execute()`:
   - **Pattern matching** — `registry.match()` tries ~95 exact patterns from `commands/` @step handlers via the `parse` library
   - **Semantic fallback** — if no exact match, sentence-transformer embeddings find the closest command (cosine similarity, threshold 0.55)
   - Supports segment splitting ("open firefox and maximize it"), pronoun resolution, verb carry-forward
4. **Conversation path** — `conversation.py` handles chat mode via `llm_chain.run_chain()` (Gemma 4 LLM, up to 5 chained tool-calling steps)
5. **Tool execution** — @step handlers, facade tools (`tools/facades.py`), or standalone tools (`tools/standalone.py`) call anthony-mcp via MCP protocol
6. **Voice output** — `voice_io.py` synthesizes response with Piper TTS

## Module Map

### Core (root)

| File | Purpose |
|---|---|
| `orchestrator.py` | Entry point. Manages llama-server lifecycle, initializes all modules, runs the voice loop. CLI args: `--ptt`, `--debug`, `--restart-server`, `--kill-server` |
| `command_matcher.py` | Command routing: exact pattern matching via `registry.match()`, then semantic fallback via sentence-transformer embeddings. Handles segment splitting, pronoun resolution, verb carry-forward |
| `voice_io.py` | STT (faster-whisper + Silero VAD) and TTS (Piper). Exports `speak()`, `listen_and_transcribe()`, `check_audio_health()` |
| `command_router.py` | RAG context preparation with namespace retrieval + auto-focus |
| `llm_chain.py` | Agentic tool-calling loop for conversation mode and vision. Sends messages + filtered tool schemas to llama-server, processes tool_calls, chains results back |
| `conversation.py` | Chat mode. Multi-turn conversation handler using llm_chain |
| `app_index.py` | Application indexing via Gio.AppInfo + semantic search. Builds app name map, smart window matching, embedding model management |
| `dialog_handler.py` | Safe close handling via dogtail (a11y). Detects save/discard dialogs, reads options to user, activates buttons via keyboard |
| `mcp_client.py` | Standalone MCP client for testing. Thread-based async bridge with command/result queues |
| `utils.py` | Logging setup (rotating file handler) and `log_and_print()` helper |

### commands/

13 command modules with ~95 `@step` decorated handlers. Each handler defines one or more voice patterns and is registered in `CommandRegistry` at import time. The registry is used by `command_matcher.py` for pattern matching and semantic fallback.

| File | Patterns | Purpose |
|---|---|---|
| `__init__.py` | — | `CommandRegistry` class, `step` decorator, `registry.match()` |
| `shortcuts.py` | 15 | App-aware shortcuts: tab navigation, clipboard, undo/redo, zoom, find |
| `window.py` | 14 | Window control: focus, close, minimize, tile, move |
| `audio.py` | 13 | Volume, mute, media playback |
| `system.py` | 10 | Date/time, notifications, system info |
| `brightness.py` | 10 | Screen and keyboard brightness |
| `input.py` | 8 | Key press, type text, mouse click, scroll, drag |
| `vision.py` | 7 | Screenshot, screen description, color pick |
| `power.py` | 5 | Suspend, shutdown, restart, logout, lock |
| `apps.py` | 3 | Launch/focus applications |
| `search.py` | 3 | Open files, URLs, search |
| `settings.py` | 3 | Dark mode, wallpaper, night light |
| `workspace.py` | 2 | Workspace switching |
| `help.py` | 2 | Help and command listing |

### tools/

| File | Purpose |
|---|---|
| `facades.py` | 6 facade functions that consolidate 34 MCP tools into clean namespaces: `window_control`, `input_control`, `audio_control`, `system_settings`, `vision_control`, `workspace_control`. Each dispatches to MCP tools via `_mcp_client.call_tool()` |
| `standalone.py` | Independent tools that don't map to a single MCP namespace: `get_datetime`, `list_installed_applications`, `send_notification`, `cleanup_screenshots`, `search_apps`, `run_install`, `run_uninstall`, `get_app_shortcuts` |

### config/

| File | Purpose |
|---|---|
| `tool_schemas.py` | OpenAI-format tool definitions (13 tools) sent to the LLM. This is what the model sees |
| `namespaces.py` | RAG namespace definitions — maps semantic descriptions to tool groups for retrieval filtering |
| `prompts.py` | System prompts: command classifier, command mode system message, conversation mode prompt |
| `aliases.py` | `APP_SHORTCUT_ALIASES` — maps friendly names ("text editor") to shortcut JSON keys ("text-editor") |

### shortcuts/

| File | Purpose |
|---|---|
| `gnome_shortcuts.py` | Reads keyboard shortcuts from gsettings schemas at runtime (GNOME WM, Shell, Mutter, Ptyxis) |
| `app_shortcuts.json` | Curated per-app shortcut database with `_skills` for multi-step operations |

## Key Design Patterns

### Facade Pattern (tools)
34 individual MCP tools are consolidated into 6 facade functions + 4 standalone tools + 3 direct MCP tools = 13 total tools exposed to the LLM. This reduces inference time by 2-3x while preserving all functionality.

### RAG Tool Retrieval (app_index.py)
Instead of sending all 13 tools to the LLM, semantic similarity + verb-based routing selects the top 2 relevant namespaces (~4-6 tools). This further reduces LLM context and improves accuracy.

### Hybrid Routing (command_matcher.py)
`registry.match()` tries exact `parse` patterns first (~95 patterns across 13 `commands/` modules). If no exact match, sentence-transformer embeddings find the closest command via cosine similarity (threshold 0.55). Most commands resolve in <100ms without calling the LLM. The LLM is only used for conversation mode and vision tasks.

### Dependency Injection
Modules use `init()` functions to receive runtime dependencies (mcp_client, speak, etc.) rather than circular imports. The orchestrator wires everything together at startup.

### Safe Close Protocol (dialog_handler.py + facades.py)
When closing a window, the system checks for save dialogs via a11y (dogtail), reads button options to the user via TTS, listens for voice response, and activates the chosen button via keyboard shortcuts or Tab/arrow fallback.

## External Dependencies

### ML Models (loaded at startup)
- **faster-whisper** `medium.en` — speech-to-text (CPU, int8)
- **Silero VAD** — voice activity detection (torch)
- **Piper** `en_US-lessac-medium` — text-to-speech (ONNX)
- **sentence-transformers** `all-MiniLM-L6-v2` — tool retrieval embeddings (CPU)

### LLM Server (separate process)
- **llama-server** (llama.cpp) running Gemma 4 with Vulkan GPU acceleration on port 8081
- OpenAI-compatible HTTP API with vision support (mmproj)
- Two supported variants: E2B (Q8_0, ~3GB, faster) or E4B (Q4_K_M, ~5GB, higher quality)
- Models stored in `~/models/`, converted from HF safetensors via `convert_hf_to_gguf.py` and quantized with `llama-quantize`
- See `start_llama_server.sh` for launch commands and `INSTALL.md` for full build/convert/quantize steps

### Companion Repo
- **anthony-mcp** — GNOME Shell extension + MCP server providing desktop automation tools (window management, input simulation, screenshots, system settings, etc.)

## Running

```bash
# Default: continuous VAD listening
python orchestrator.py

# Push-to-talk mode
python orchestrator.py --ptt

# With debug output
python orchestrator.py --debug

# Force restart llama-server
python orchestrator.py --restart-server
```

Requires: llama-server running (auto-started if not), anthony-mcp installed, GNOME accessibility enabled (auto-enabled at startup).
