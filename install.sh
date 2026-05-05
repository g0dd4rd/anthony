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
echo "  - Text-to-speech (Piper)"
echo "  - Desktop automation (MCP)"
echo "  - Conversational AI (Gemma4)"
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

if ! rpm -q alsa-utils &> /dev/null; then
    PACKAGES_TO_INSTALL+=("alsa-utils")
fi

if ! rpm -q portaudio-devel &> /dev/null; then
    PACKAGES_TO_INSTALL+=("portaudio-devel")
fi

if ! rpm -q python3-devel &> /dev/null; then
    PACKAGES_TO_INSTALL+=("python3-devel")
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
    "ollama"
    "sounddevice"
    "pyaudio"
    "faster-whisper"
    "piper-tts"
    "mcp"
    "torch"
    "numpy"
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
# 3. Node.js & MCP Server
# ========================================
print_header "Step 3: Installing GNOME Desktop MCP"

if ! command -v node &> /dev/null; then
    print_warning "Node.js is not installed. Installing..."
    sudo dnf install -y nodejs npm
fi

if ! command -v gnome-desktop-mcp &> /dev/null; then
    print_step "Installing gnome-desktop-mcp..."
    npm install -g gnome-desktop-mcp
    print_success "gnome-desktop-mcp installed"
else
    print_success "gnome-desktop-mcp already installed"
fi

# ========================================
# 4. Ollama & Models
# ========================================
print_header "Step 4: Installing Ollama & Gemma4"

if ! command -v ollama &> /dev/null; then
    print_step "Installing Ollama..."
    curl -fsSL https://ollama.com/install.sh | sh
    print_success "Ollama installed"
else
    print_success "Ollama already installed"
fi

print_step "Checking if Gemma4 model is available..."
if ! ollama list | grep -q "gemma4:e4b"; then
    print_step "Pulling Gemma4 model (this may take several minutes)..."
    ollama pull gemma4:e4b
    print_success "Gemma4 model downloaded"
else
    print_success "Gemma4 model already available"
fi

# ========================================
# 5. Piper Voice Model
# ========================================
print_header "Step 5: Downloading Piper Voice Model"

PIPER_MODEL_DIR="$HOME/anthony"
PIPER_MODEL_FILE="$PIPER_MODEL_DIR/en_US-lessac-medium.onnx"
PIPER_CONFIG_FILE="$PIPER_MODEL_DIR/en_US-lessac-medium.onnx.json"

mkdir -p "$PIPER_MODEL_DIR"

if [ ! -f "$PIPER_MODEL_FILE" ]; then
    print_step "Downloading Piper voice model..."
    wget -q --show-progress -O "$PIPER_MODEL_FILE" \
        "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/medium/en_US-lessac-medium.onnx"
    print_success "Piper model downloaded"
else
    print_success "Piper model already exists"
fi

if [ ! -f "$PIPER_CONFIG_FILE" ]; then
    print_step "Downloading Piper model config..."
    wget -q --show-progress -O "$PIPER_CONFIG_FILE" \
        "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/medium/en_US-lessac-medium.onnx.json"
    print_success "Piper config downloaded"
else
    print_success "Piper config already exists"
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
check_command "node" || VERIFICATION_FAILED=1
check_command "npm" || VERIFICATION_FAILED=1
check_command "ollama" || VERIFICATION_FAILED=1
check_command "gnome-desktop-mcp" || VERIFICATION_FAILED=1
check_command "aplay" || VERIFICATION_FAILED=1

echo ""
print_step "Checking Python modules..."
check_python_module "ollama" || VERIFICATION_FAILED=1
check_python_module "sounddevice" || VERIFICATION_FAILED=1
check_python_module "pyaudio" || VERIFICATION_FAILED=1
check_python_module "faster_whisper" || VERIFICATION_FAILED=1
check_python_module "piper" || VERIFICATION_FAILED=1
check_python_module "mcp" || VERIFICATION_FAILED=1
check_python_module "torch" || VERIFICATION_FAILED=1
check_python_module "numpy" || VERIFICATION_FAILED=1
check_python_module "dogtail.tree" || VERIFICATION_FAILED=1

echo ""
print_step "Checking Ollama models..."
if ollama list | grep -q "gemma4:e4b"; then
    print_success "Gemma4 model is available"
else
    print_error "Gemma4 model is not available"
    VERIFICATION_FAILED=1
fi

echo ""
print_step "Checking Piper voice model..."
if [ -f "$PIPER_MODEL_FILE" ] && [ -f "$PIPER_CONFIG_FILE" ]; then
    print_success "Piper voice model exists"
else
    print_error "Piper voice model missing"
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

# ========================================
# Final Report
# ========================================
print_header "Installation Complete"

if [ $VERIFICATION_FAILED -eq 0 ]; then
    print_success "All dependencies installed and verified!"
    echo ""
    echo "You can now run the orchestrator:"
    echo -e "  ${GREEN}cd ~/anthony${NC}"
    echo -e "  ${GREEN}./voice-driven-orchestrator-mcp-conversational.py${NC}"
    echo ""
    echo "First run will download additional models:"
    echo "  - Whisper medium.en (~1.5GB)"
    echo "  - Silero VAD (~2MB)"
    echo ""
    exit 0
else
    print_error "Some verification checks failed!"
    echo ""
    echo "Please review the errors above and fix them before running the orchestrator."
    echo ""
    exit 1
fi
