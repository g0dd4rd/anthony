# Bugs and Ideas

| # | Item | Category | Status |
|---|------|----------|--------|
| 11 | Media controls (play, pause, next, prev, stop) | Testing | Tested: pass (next/prev n/a for Decibels) |
| 12 | Wallpaper | Testing | Tested: pass |
| 22 | Create different personas for the LLM for conversation mode | Feature | |
| 23 | i18n of Anthony speak output | Feature | |
| 24 | Extract JSON parts from orchestrator into separate files for readability | Refactor | Done (config/ module: tool_schemas, namespaces, prompts) |
| 26 | faster-whisper drops spaces from filenames ("bugs and ideas.txt") | Bug | |
| 27 | Implement tools for log out, restart, shut down | Feature | Done (with voice confirmation) |
| 28 | What features would benefit handicapped users the most? | Research | |
| 29 | "Undo last action" - safety net for voice commands | Feature | |
| 30 | "Read this to me" - read selected text or clipboard aloud | Feature | |
| 32 | What's the time, date? | Feature | Done |
| 33 | Use webcam + vision model to describe the room | Feature | |
| 34 | App shortcuts list per app, injected into LLM context | Feature | Done |
| 35 | Non-obtrusive push-to-speak key (currently Enter) | UX | |
| 36 | Fn+S takes a screenshot | Feature | |
| 37 | Install apps via Software | Feature | Done (flatpak+dnf search, voice confirmation, short-circuit) |
| 38 | Inject ARIA labels into inaccessible web pages | Feature | |
| 39 | Improve gnome/file search tool | Feature | |
| 40 | Battery status | Feature | Done |
| 41 | Read notifications | Feature | |
| 42 | Train GNOME desktop model or LoRA fine-tuning | Research | |
| 43 | Switch faster-whisper to medium model, or provide language settings | Feature | |
| 44 | Move as many tools as possible to the MCP server | Refactor | |
| 45 | Handle arbitrary app dialogs (exit/close already handled) | Feature | |
| 47 | Curate and verify app shortcuts JSON (name, version, correctness) | Maintenance | Done (15 apps, versions verified, routing aliases unified) |
| 48 | Webcam visual+audio guides for optimal camera positioning | Feature | |
| 49 | Figure out if gnome-shell unsafe mode is really necessary | Research | |
| 50 | Figure out GNOME integration (extension, system service?) | Architecture | |
| 51 | Create rpm/flatpak/docker/app image | Packaging | |
| 53 | Track flatpak apps + update list after install/uninstall | Feature | Done (Gio.AppInfo replaces manual .desktop scanning) — includes old #52 |
| 55 | Generalize command structure + help page | Architecture | Includes old #54 |
| 57 | Use dogtail/qecore/behave for in-app commands + action verification | Architecture | Includes old #56, #60 |
| 58 | Ensure all dependencies satisfied before first use, including models | Packaging | Partial: DEPENDENCIES.md created |
| 61 | Teach the orchestrator to auto-update app shortcuts | Feature | |
| 62 | Give the LLM ability to search the web (local model is not up-to-date) | Feature | |
| 63 | Safe word to stop the current command execution | Feature | |
| 64 | Fix the automation disabled bug | Bug | Done (indicator toggle syncs on D-Bus SetEnabled) |
| 65 | Rewrite to Rust? | Research | |
| 66 | Crash on truncated LLM JSON — needs try/except around tool call parsing | Bug | Done |
| 67 | Screenshot false positives — says taken but wasn't, no path in response | Bug | Done |
| 68 | Move/resize doesn't tile properly ("right half" just centered vertically) | Bug | Done |
| 69 | "Type hello world" fails | Bug | Done (works, types into focused window as expected) |
| 70 | LLM should report when app is already running | Enhancement | Done |
| 71 | LLM should announce already-focused window | Enhancement | Done |
| 72 | Workspace response uses 0-based index instead of user-friendly numbering | Bug | Done |
| 73 | TTS pronunciation issues ("crawl down" instead of "scroll down") | Bug | Done (pad short text with filler prefix) |
| 74 | Avoid coordinate-based click/double-click under Wayland — use AT-SPI | Architecture | From test: 3.5, 3.6 |
| 75 | Evaluate diffusion LLMs (LLaDA 2.0-mini: 16B/1.4B active, tool calling, open source) as Gemma replacement — 50-100x speedup potential, blocker is llama-server support | Research | |
| 76 | Client-server split for remote deployment (Beaker/GPU) — local: mic→STT→text, remote: text→orchestrator→LLM→GNOME. Needs socket-based input mode + audio streaming | Architecture | |
| 77 | Extract facade tools (window, input, audio, settings, vision, workspace) into tools/facades.py (~700 lines) | Refactor | |
| 78 | Extract standalone tools (battery, brightness, power, datetime, notifications, etc.) into tools/standalone.py (~250 lines) | Refactor | |
| 79 | Extract voice I/O (TTS, VAD, STT) into voice/ module (~340 lines) | Refactor | |
| 80 | Extract conversation mode (classifier, handler) into conversation.py (~90 lines) | Refactor | |
| 81 | Extract app index + routing (build_app_index, smart_match, aliases, embeddings) into app_index.py (~280 lines) | Refactor | |
| 82 | Break up run_agent() (743 lines) into dispatcher, tool executor, and LLM loop | Refactor | |
| 83 | End-to-end test harness: inject text commands into run_agent(), verify results with dogtail (AT-SPI) for UI state and D-Bus/gsettings for non-UI state (volume, wallpaper) | Testing | |
| 84 | Add skills to apps that lack them (papers, loupe, showtime, decibels, calculator, clocks, boxes, baobab, simple-scan) | Feature | |
