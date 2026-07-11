#!/bin/bash
#
# Uninstall script for Anthony - removes everything installed by install.sh,
# build_llama.sh, and download_model.sh
#
# Usage:
#   ./uninstall.sh           # interactive — asks before each step
#   ./uninstall.sh --all     # remove everything without prompting

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

FORCE=false
if [[ "${1:-}" == "--all" ]]; then
    FORCE=true
fi

print_header() {
    echo -e "\n${BLUE}======================================${NC}"
    echo -e "${BLUE}$1${NC}"
    echo -e "${BLUE}======================================${NC}\n"
}

print_step() { echo -e "${YELLOW}▶${NC} $1"; }
print_done() { echo -e "${GREEN}✓${NC} $1"; }
print_skip() { echo -e "${YELLOW}—${NC} $1"; }
print_warn() { echo -e "${YELLOW}⚠️${NC}  $1"; }

confirm() {
    if [ "$FORCE" = true ]; then
        return 0
    fi
    read -p "$1 (y/n) " -n 1 -r
    echo
    [[ $REPLY =~ ^[Yy]$ ]]
}

print_header "Anthony — Uninstall"
echo "This will remove Anthony and all its components."
echo ""

if [ "$FORCE" = false ]; then
    read -p "Continue? (y/n) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "Cancelled."
        exit 0
    fi
fi

# ========================================
# 1. Kill running processes
# ========================================
print_header "Step 1: Stop Running Processes"

if pgrep -f "llama-server.*--port" &>/dev/null; then
    if confirm "Kill running llama-server?"; then
        pkill -f "llama-server.*--port" || true
        sleep 1
        print_done "llama-server stopped"
    else
        print_skip "llama-server left running"
    fi
else
    print_done "No llama-server running"
fi

if pgrep -f "orchestrator.py" &>/dev/null; then
    if confirm "Kill running orchestrator?"; then
        pkill -f "orchestrator.py" || true
        print_done "Orchestrator stopped"
    else
        print_skip "Orchestrator left running"
    fi
else
    print_done "No orchestrator running"
fi

# ========================================
# 2. Python virtual environment
# ========================================
print_header "Step 2: Python Virtual Environment"

VENV_DIR="$SCRIPT_DIR/.venv"
if [ -d "$VENV_DIR" ]; then
    VENV_SIZE=$(du -sh "$VENV_DIR" 2>/dev/null | cut -f1)
    if confirm "Remove Python virtual environment ($VENV_SIZE)?"; then
        rm -rf "$VENV_DIR"
        print_done "Virtual environment removed"
    else
        print_skip "Virtual environment kept"
    fi
else
    print_done "No virtual environment found"
fi

# ========================================
# 3. Anthony MCP
# ========================================
print_header "Step 3: Anthony MCP"

if confirm "Uninstall anthony-mcp?"; then
    EXTENSION_UUID="desktop-automation@anthonymcp.github.io"
    EXTENSION_DIR="$HOME/.local/share/gnome-shell/extensions/$EXTENSION_UUID"
    if [ -e "$EXTENSION_DIR" ]; then
        rm -rf "$EXTENSION_DIR"
        print_done "GNOME extension removed"
    fi

    # KDE ydotool service override
    YDOTOOL_OVERRIDE="/etc/systemd/system/ydotool.service.d/socket-access.conf"
    if [ -f "$YDOTOOL_OVERRIDE" ]; then
        if confirm "Remove ydotool service override (needs sudo)?"; then
            sudo rm -f "$YDOTOOL_OVERRIDE"
            sudo rmdir /etc/systemd/system/ydotool.service.d 2>/dev/null || true
            sudo systemctl daemon-reload
            print_done "ydotool override removed"
        fi
    fi

    if [ -d "$HOME/anthony-mcp" ]; then
        if confirm "Remove $HOME/anthony-mcp/?"; then
            rm -rf "$HOME/anthony-mcp"
            print_done "anthony-mcp directory removed"
        else
            print_skip "anthony-mcp directory kept"
        fi
    fi
else
    print_skip "anthony-mcp kept"
fi

# ========================================
# 4. LLM models
# ========================================
print_header "Step 4: LLM Models"

if [ -d "$HOME/models" ] && ls "$HOME/models/"*.gguf &>/dev/null 2>&1; then
    echo "Model files in $HOME/models/:"
    ls -lh "$HOME/models/"*.gguf
    echo ""
    if confirm "Delete all model files in $HOME/models/?"; then
        rm -f "$HOME/models/"*.gguf
        rmdir "$HOME/models" 2>/dev/null || true
        print_done "Model files removed"
    else
        print_skip "Model files kept"
    fi
else
    print_done "No model files found"
fi

# ========================================
# 5. llama.cpp
# ========================================
print_header "Step 5: llama.cpp"

if [ -d "$HOME/llama.cpp" ]; then
    LLAMA_SIZE=$(du -sh "$HOME/llama.cpp" 2>/dev/null | cut -f1)
    if confirm "Remove $HOME/llama.cpp/ ($LLAMA_SIZE)?"; then
        rm -rf "$HOME/llama.cpp"
        print_done "llama.cpp removed"
    else
        print_skip "llama.cpp kept"
    fi
else
    print_done "No llama.cpp directory found"
fi

# ========================================
# 6. Cached models (Whisper, Silero VAD)
# ========================================
print_header "Step 6: Cached Models"

WHISPER_CACHE="$HOME/.cache/huggingface/hub/models--Systran--faster-whisper-medium.en"
SILERO_CACHE="$HOME/.cache/torch/hub/snakers4_silero-vad_master"

if [ -d "$WHISPER_CACHE" ]; then
    WHISPER_SIZE=$(du -sh "$WHISPER_CACHE" 2>/dev/null | cut -f1)
    if confirm "Remove Whisper model cache ($WHISPER_SIZE)?"; then
        rm -rf "$WHISPER_CACHE"
        print_done "Whisper cache removed"
    else
        print_skip "Whisper cache kept"
    fi
else
    print_done "No Whisper cache found"
fi

if [ -d "$SILERO_CACHE" ]; then
    if confirm "Remove Silero VAD cache?"; then
        rm -rf "$SILERO_CACHE"
        print_done "Silero VAD cache removed"
    else
        print_skip "Silero VAD cache kept"
    fi
else
    print_done "No Silero VAD cache found"
fi

# ========================================
# 7. Piper voice model
# ========================================
print_header "Step 7: Piper Voice Model"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PIPER_MODEL="$SCRIPT_DIR/en_US-lessac-medium.onnx"
PIPER_JSON="$SCRIPT_DIR/en_US-lessac-medium.onnx.json"

if [ -f "$PIPER_MODEL" ]; then
    if confirm "Remove Piper voice model?"; then
        rm -f "$PIPER_MODEL" "$PIPER_JSON"
        print_done "Piper model removed"
    else
        print_skip "Piper model kept"
    fi
else
    print_done "No Piper model found"
fi

# ========================================
# 8. MBROLA
# ========================================
print_header "Step 8: MBROLA"

if command -v mbrola &>/dev/null; then
    if confirm "Remove mbrola binary (/usr/local/bin/mbrola)?"; then
        sudo rm -f /usr/local/bin/mbrola
        print_done "mbrola binary removed"
    else
        print_skip "mbrola binary kept"
    fi
else
    print_done "No mbrola binary found"
fi

if [ -d "/usr/share/mbrola" ]; then
    if confirm "Remove mbrola voice data (/usr/share/mbrola)?"; then
        sudo rm -rf /usr/share/mbrola
        print_done "mbrola voices removed"
    else
        print_skip "mbrola voices kept"
    fi
else
    print_done "No mbrola voices found"
fi

# ========================================
# 9. Anthony itself
# ========================================
print_header "Step 9: Anthony"

if confirm "Remove anthony directory ($SCRIPT_DIR)?"; then
    print_warn "Removing $SCRIPT_DIR after this script finishes..."
    (sleep 1 && rm -rf "$SCRIPT_DIR") &
    print_done "anthony scheduled for removal"
else
    print_skip "anthony directory kept"
fi

# ========================================
# Done
# ========================================
print_header "Uninstall Complete"

echo "Note: System packages (git, alsa-utils, portaudio-devel, espeak-ng, etc.)"
echo "were NOT removed, as they may be used by other applications."
echo ""
print_done "Anthony has been uninstalled."
