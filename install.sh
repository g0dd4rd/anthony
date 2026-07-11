#!/bin/bash
#
# Installation script for Voice-Driven Orchestrator (Conversational Mode)
#
# This script installs all dependencies and verifies the installation.
#

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Helper functions
print_header() {
    echo -e "\n${BLUE}======================================${NC}"
    echo -e "${BLUE}$1${NC}"
    echo -e "${BLUE}======================================${NC}\n"
}

print_step() {
    echo -e "${YELLOW}▶${NC} $1"
}

print_success() {
    echo -e "${GREEN}✅${NC} $1"
}

print_error() {
    echo -e "${RED}❌${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}⚠️${NC}  $1"
}

check_command() {
    if command -v "$1" &> /dev/null; then
        print_success "$1 is installed"
        return 0
    else
        print_error "$1 is not installed"
        return 1
    fi
}

check_python_module() {
    if python3 -c "import $1" &> /dev/null; then
        print_success "Python module '$1' is installed"
        return 0
    else
        print_error "Python module '$1' is not installed"
        return 1
    fi
}

# Start installation
print_header "Voice-Driven Orchestrator - Installation"

echo "This script will install all dependencies for:"
echo "  - Voice recognition (Whisper)"
echo "  - Text-to-speech (Piper neural + espeak-ng/mbrola synthetic)"
echo "  - Desktop automation (MCP)"
echo "  - LLM tool calling (Gemma4 via llama-server)"
echo "  - Volume & media control (PipeWire/PulseAudio, playerctl)"
echo ""
read -p "Continue? (y/n) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Installation cancelled."
    exit 0
fi

# ========================================
# 1. System Packages
# ========================================
print_header "Step 1: Installing System Packages"

print_step "Checking for required system packages..."

PACKAGES_TO_INSTALL=()

if ! rpm -q git &> /dev/null; then
    PACKAGES_TO_INSTALL+=("git")
fi

if ! rpm -q alsa-utils &> /dev/null; then
    PACKAGES_TO_INSTALL+=("alsa-utils")
fi

if ! rpm -q portaudio-devel &> /dev/null; then
    PACKAGES_TO_INSTALL+=("portaudio-devel")
fi

if ! rpm -q python3-devel &> /dev/null; then
    PACKAGES_TO_INSTALL+=("python3-devel")
fi

# For volume control (PipeWire/PulseAudio)
if ! rpm -q pipewire-utils &> /dev/null; then
    PACKAGES_TO_INSTALL+=("pipewire-utils")
fi

# For media control (play/pause/next/previous)
if ! rpm -q playerctl &> /dev/null; then
    PACKAGES_TO_INSTALL+=("playerctl")
fi

# For synthetic TTS (espeak-ng + mbrola)
if ! rpm -q espeak-ng &> /dev/null; then
    PACKAGES_TO_INSTALL+=("espeak-ng")
fi

if [ ${#PACKAGES_TO_INSTALL[@]} -gt 0 ]; then
    print_step "Installing: ${PACKAGES_TO_INSTALL[*]}"
    sudo dnf install -y "${PACKAGES_TO_INSTALL[@]}"
    print_success "System packages installed"
else
    print_success "All system packages already installed"
fi

# ========================================
# 2. Python Packages
# ========================================
print_header "Step 2: Installing Python Packages"

print_step "Installing Python dependencies..."

# Install packages one by one to better track progress
PYTHON_PACKAGES=(
    "sounddevice"
    "pyaudio"
    "faster-whisper"
    "piper-tts"
    "mcp"
    "torch"
    "torchaudio"
    "numpy"
    "parse"
    "sentence-transformers"
    "requests"
    "webcolors"
    "dogtail"
)

for pkg in "${PYTHON_PACKAGES[@]}"; do
    print_step "Installing $pkg..."
    pip install --quiet "$pkg" || {
        print_error "Failed to install $pkg"
        exit 1
    }
done

print_success "All Python packages installed"

# ========================================
# 3. GNOME Desktop MCP Server
# ========================================
print_header "Step 3: Installing Anthony MCP Server"

if ! command -v anthony-mcp &> /dev/null; then
    print_step "Installing anthony-mcp..."

    # Check if local development version exists
    if [ -d "$HOME/anthony-mcp" ]; then
        print_step "Found local anthony-mcp, installing from source..."
        cd "$HOME/anthony-mcp"
        ./install.sh
        print_success "anthony-mcp installed from local source"
    else
        print_step "Cloning anthony-mcp from GitHub..."
        cd "$HOME"
        git clone https://github.com/g0dd4rd/anthony-mcp.git
        cd anthony-mcp
        ./install.sh
        print_success "anthony-mcp installed from GitHub"
    fi

    cd "$HOME/anthony"
else
    print_success "anthony-mcp already installed"
fi

# ========================================
# 4. Piper Voice Model
# ========================================
print_header "Step 4: Downloading Piper Voice Model"

PIPER_MODEL_DIR="$HOME/anthony"
PIPER_MODEL_FILE="$PIPER_MODEL_DIR/en_US-lessac-medium.onnx"

if [ ! -f "$PIPER_MODEL_FILE" ]; then
    print_step "Downloading Piper voice model..."
    python3 -m piper.download_voices --download-dir "$PIPER_MODEL_DIR" en_US-lessac-medium
    print_success "Piper model downloaded"
else
    print_success "Piper model already exists"
fi

# ========================================
# 5. MBROLA (synthetic TTS voice)
# ========================================
print_header "Step 5: Installing MBROLA"

if command -v mbrola &> /dev/null; then
    print_success "mbrola already installed"
else
    print_step "Building mbrola from source..."
    MBROLA_BUILD_DIR=$(mktemp -d)
    git clone --depth 1 https://github.com/numediart/MBROLA.git "$MBROLA_BUILD_DIR/MBROLA"
    make -C "$MBROLA_BUILD_DIR/MBROLA"
    sudo cp "$MBROLA_BUILD_DIR/MBROLA/Bin/mbrola" /usr/local/bin/mbrola
    rm -rf "$MBROLA_BUILD_DIR"
    print_success "mbrola installed"
fi

MBROLA_VOICE_DIR="/usr/share/mbrola/us1"
if [ -f "$MBROLA_VOICE_DIR/us1" ]; then
    print_success "mbrola us1 voice already installed"
else
    print_step "Downloading mbrola us1 voice..."
    sudo mkdir -p "$MBROLA_VOICE_DIR"
    MBROLA_VOICES_DIR=$(mktemp -d)
    git clone --depth 1 --filter=blob:none --sparse https://github.com/numediart/MBROLA-voices.git "$MBROLA_VOICES_DIR"
    cd "$MBROLA_VOICES_DIR"
    git sparse-checkout set data/us1
    sudo cp data/us1/us1 "$MBROLA_VOICE_DIR/us1"
    cd "$HOME/anthony"
    rm -rf "$MBROLA_VOICES_DIR"
    print_success "mbrola us1 voice installed"
fi

# ========================================
# 6. GNOME Accessibility
# ========================================
print_header "Step 6: Configuring GNOME Accessibility"

ACCESSIBILITY=$(gsettings get org.gnome.desktop.interface toolkit-accessibility)

if [ "$ACCESSIBILITY" != "true" ]; then
    print_step "Enabling GNOME accessibility..."
    gsettings set org.gnome.desktop.interface toolkit-accessibility true
    print_success "Accessibility enabled"
    print_warning "Note: You may need to log out and back in for full accessibility support"
else
    print_success "Accessibility already enabled"
fi

# ========================================
# 7. Verification
# ========================================
print_header "Step 7: Verifying Installation"

VERIFICATION_FAILED=0

print_step "Checking system commands..."
check_command "python3" || VERIFICATION_FAILED=1
check_command "pip" || VERIFICATION_FAILED=1
check_command "git" || VERIFICATION_FAILED=1
check_command "anthony-mcp" || VERIFICATION_FAILED=1
check_command "aplay" || VERIFICATION_FAILED=1
check_command "pactl" || VERIFICATION_FAILED=1
check_command "playerctl" || VERIFICATION_FAILED=1
check_command "espeak-ng" || VERIFICATION_FAILED=1
check_command "mbrola" || VERIFICATION_FAILED=1

echo ""
print_step "Checking Python modules..."
check_python_module "sounddevice" || VERIFICATION_FAILED=1
check_python_module "pyaudio" || VERIFICATION_FAILED=1
check_python_module "faster_whisper" || VERIFICATION_FAILED=1
check_python_module "piper" || VERIFICATION_FAILED=1
check_python_module "mcp" || VERIFICATION_FAILED=1
check_python_module "torch" || VERIFICATION_FAILED=1
check_python_module "torchaudio" || VERIFICATION_FAILED=1
check_python_module "numpy" || VERIFICATION_FAILED=1
check_python_module "sentence_transformers" || VERIFICATION_FAILED=1
check_python_module "requests" || VERIFICATION_FAILED=1
check_python_module "webcolors" || VERIFICATION_FAILED=1
check_python_module "dogtail.tree" || VERIFICATION_FAILED=1

echo ""
print_step "Checking Piper voice model..."
if [ -f "$PIPER_MODEL_FILE" ]; then
    print_success "Piper voice model exists"
else
    print_error "Piper voice model missing"
    VERIFICATION_FAILED=1
fi

echo ""
print_step "Checking mbrola voice..."
if [ -f "/usr/share/mbrola/us1/us1" ]; then
    print_success "mbrola us1 voice exists"
else
    print_error "mbrola us1 voice missing"
    VERIFICATION_FAILED=1
fi

echo ""
print_step "Checking GNOME accessibility..."
if gsettings get org.gnome.desktop.interface toolkit-accessibility | grep -q "true"; then
    print_success "GNOME accessibility enabled"
else
    print_error "GNOME accessibility not enabled"
    VERIFICATION_FAILED=1
fi

echo ""
print_step "Checking external setup (warnings only)..."

LLAMA_OK=false
if [ -x "$HOME/llama.cpp/build/bin/llama-server" ]; then
    print_success "llama-server binary found"
    LLAMA_OK=true
else
    print_warning "llama-server not built yet"
fi

MODEL_OK=false
if ls "$HOME/models/"*.gguf &> /dev/null; then
    print_success "LLM model found"
    MODEL_OK=true
else
    print_warning "LLM model not downloaded yet"
fi

MMPROJ_OK=false
if ls "$HOME/models/mmproj-"*.gguf &> /dev/null; then
    print_success "Vision projector found"
    MMPROJ_OK=true
else
    print_warning "Vision projector not downloaded yet"
fi

EXT_OK=false
if [[ "${XDG_CURRENT_DESKTOP:-}" == *"GNOME"* ]]; then
    EXT_UUID="desktop-automation@anthonymcp.github.io"
    if gnome-extensions info "$EXT_UUID" 2>/dev/null | grep -q "State: ENABLED"; then
        print_success "GNOME Shell extension enabled"
        EXT_OK=true
    else
        print_warning "GNOME Shell extension not active (may need log out/in)"
    fi
else
    EXT_OK=true
fi

# ========================================
# Final Report
# ========================================
print_header "Next Steps"

if [ $VERIFICATION_FAILED -ne 0 ]; then
    print_error "Some dependency checks failed! Review the errors above."
    echo ""
    exit 1
fi

print_success "All dependencies installed and verified!"
echo ""

ALL_READY=true

echo -e "  ${GREEN}✓${NC}  Dependencies installed"

if [[ "${XDG_CURRENT_DESKTOP:-}" == *"GNOME"* ]]; then
    if [ "$EXT_OK" = true ]; then
        echo -e "  ${GREEN}✓${NC}  GNOME Shell extension active"
    else
        echo -e "  ${RED}✗${NC}  Log out and back in              ${YELLOW}(extension needs Shell restart)${NC}"
        ALL_READY=false
    fi
fi

if [ "$LLAMA_OK" = true ]; then
    echo -e "  ${GREEN}✓${NC}  llama-server built"
else
    echo -e "  ${RED}✗${NC}  Build llama-server                ${YELLOW}→ ./build_llama.sh${NC}"
    ALL_READY=false
fi

if [ "$MODEL_OK" = true ] && [ "$MMPROJ_OK" = true ]; then
    echo -e "  ${GREEN}✓${NC}  LLM model downloaded"
else
    echo -e "  ${RED}✗${NC}  Download LLM model                ${YELLOW}→ ./download_model.sh${NC}"
    ALL_READY=false
fi

echo ""
if [ "$ALL_READY" = true ]; then
    echo -e "  ${GREEN}All set!${NC} Run:"
    echo -e "    ${GREEN}./orchestrator.py${NC}"
else
    echo "  First run will also download:"
    echo "    - Whisper medium.en (~1.5GB)"
    echo "    - Silero VAD (~2MB)"
    echo ""
    echo -e "  When all steps show ${GREEN}✓${NC}, run:"
    echo -e "    ${GREEN}./orchestrator.py${NC}"
fi
echo ""
exit 0
