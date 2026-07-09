#!/bin/bash
# Build llama.cpp from source with GPU backend auto-detection or explicit selection.
#
# Usage:
#   ./build_llama.sh                        # auto-detect: CUDA > ROCm > Vulkan > CPU
#   ./build_llama.sh --backend openvino     # build with OpenVINO (Intel CPU/GPU/NPU)
#   ./build_llama.sh --backend vulkan       # build with Vulkan
#   ./build_llama.sh --backend cuda         # build with CUDA
#   ./build_llama.sh --backend rocm         # build with ROCm/HIP
#   ./build_llama.sh --update               # pull latest llama.cpp + rebuild
#   ./build_llama.sh --update --backend openvino  # update + rebuild with OpenVINO

set -euo pipefail

LLAMA_DIR="$HOME/llama.cpp"
UPDATE=false
BACKEND="auto"

for arg in "$@"; do
    case "$arg" in
        --update) UPDATE=true ;;
        --backend)  :;; # value handled below
        openvino|vulkan|cuda|rocm|auto)
            BACKEND="$arg" ;;
        *)
            echo "Unknown argument: $arg"
            echo "Usage: $0 [--update] [--backend auto|cuda|rocm|openvino|vulkan]"
            exit 1 ;;
    esac
done

# OpenVINO uses a separate build dir so both backends can coexist
if [ "$BACKEND" = "openvino" ]; then
    BUILD_DIR="$LLAMA_DIR/build_ov"
else
    BUILD_DIR="$LLAMA_DIR/build"
fi

# Build dependencies
PACKAGES_TO_INSTALL=()
if ! command -v cmake &>/dev/null; then
    PACKAGES_TO_INSTALL+=("cmake")
fi
if ! command -v g++ &>/dev/null; then
    PACKAGES_TO_INSTALL+=("gcc-c++")
fi
if ! command -v gcc &>/dev/null; then
    PACKAGES_TO_INSTALL+=("gcc")
fi

if [ ${#PACKAGES_TO_INSTALL[@]} -gt 0 ]; then
    echo "Installing build dependencies: ${PACKAGES_TO_INSTALL[*]}"
    sudo dnf install -y "${PACKAGES_TO_INSTALL[@]}"
fi

# Clone or update
if [ ! -d "$LLAMA_DIR" ]; then
    echo "Cloning llama.cpp..."
    git clone https://github.com/ggerganov/llama.cpp.git "$LLAMA_DIR"
elif [ "$UPDATE" = true ]; then
    echo "Updating llama.cpp..."
    git -C "$LLAMA_DIR" pull --ff-only
fi

CMAKE_ARGS=()

if [ "$BACKEND" != "auto" ]; then
    # Explicit backend selection
    case "$BACKEND" in
        cuda)
            echo "Building with CUDA support (explicit)"
            if ! command -v nvcc &>/dev/null; then
                echo "CUDA toolkit not found — installing..."
                sudo dnf install -y cuda-nvcc cuda-cudart-devel libcublas-devel
            fi
            CMAKE_ARGS+=(-DGGML_CUDA=ON)
            ;;
        rocm)
            echo "Building with ROCm/HIP support (explicit)"
            GFX_TARGET=$(rocminfo 2>/dev/null | grep -oP 'gfx\d+' | head -1)
            if [ -z "$GFX_TARGET" ]; then
                echo "Error: ROCm not found or no AMD GPU detected"
                exit 1
            fi
            CMAKE_ARGS+=(-DGGML_HIP=ON -DAMDGPU_TARGETS="$GFX_TARGET")
            ;;
        openvino)
            echo "Building with OpenVINO support"
            # Find and source OpenVINO setupvars.sh
            OV_SETUP=""
            if [ -n "${INTEL_OPENVINO_DIR:-}" ] && [ -f "$INTEL_OPENVINO_DIR/setupvars.sh" ]; then
                OV_SETUP="$INTEL_OPENVINO_DIR/setupvars.sh"
            else
                for candidate in /opt/intel/openvino_*/setupvars.sh; do
                    if [ -f "$candidate" ]; then
                        OV_SETUP="$candidate"
                    fi
                done
            fi
            if [ -z "$OV_SETUP" ]; then
                echo "Error: OpenVINO not found."
                echo "Install from: https://docs.openvino.ai/2024/get-started/install-openvino.html"
                exit 1
            fi
            echo "Sourcing $OV_SETUP"
            source "$OV_SETUP"
            CMAKE_ARGS+=(-DGGML_OPENVINO=ON)
            ;;
        vulkan)
            echo "Building with Vulkan support (explicit)"
            if ! rpm -q vulkan-headers &>/dev/null; then
                echo "Installing Vulkan development headers..."
                sudo dnf install -y vulkan-headers vulkan-loader-devel
            fi
            CMAKE_ARGS+=(-DGGML_VULKAN=ON)
            ;;
    esac
else
    # Auto-detect: CUDA > ROCm > Vulkan > CPU

    # CUDA (NVIDIA)
    if nvidia-smi &>/dev/null && command -v nvcc &>/dev/null; then
        echo "CUDA GPU detected — building with CUDA support"
        CMAKE_ARGS+=(-DGGML_CUDA=ON)
    elif nvidia-smi &>/dev/null && ! command -v nvcc &>/dev/null; then
        echo "NVIDIA GPU detected but CUDA toolkit missing — installing..."
        sudo dnf install -y cuda-nvcc cuda-cudart-devel libcublas-devel
        if command -v nvcc &>/dev/null; then
            echo "CUDA toolkit installed — building with CUDA support"
            CMAKE_ARGS+=(-DGGML_CUDA=ON)
        else
            echo "CUDA toolkit install failed — falling back"
        fi
    fi

    # ROCm/HIP (AMD)
    if [ ${#CMAKE_ARGS[@]} -eq 0 ] && command -v rocminfo &>/dev/null; then
        GFX_TARGET=$(rocminfo 2>/dev/null | grep -oP 'gfx\d+' | head -1)
        if [ -n "$GFX_TARGET" ]; then
            echo "AMD ROCm GPU detected ($GFX_TARGET) — building with HIP support"
            CMAKE_ARGS+=(-DGGML_HIP=ON -DAMDGPU_TARGETS="$GFX_TARGET")
        fi
    fi

    # Vulkan (any GPU)
    if [ ${#CMAKE_ARGS[@]} -eq 0 ]; then
        if vulkaninfo --summary 2>&1 | grep -q "deviceName" && ! vulkaninfo --summary 2>&1 | grep -q "PHYSICAL_DEVICE_TYPE_CPU"; then
            echo "Vulkan GPU detected — building with Vulkan support"
            CMAKE_ARGS+=(-DGGML_VULKAN=ON)

            if ! rpm -q vulkan-headers &>/dev/null; then
                echo "Installing Vulkan development headers..."
                sudo dnf install -y vulkan-headers vulkan-loader-devel
            fi
        else
            echo "No GPU detected — building CPU-only"
        fi
    fi
fi

# Configure + build
echo "Configuring..."
cmake -B "$BUILD_DIR" -S "$LLAMA_DIR" \
    -DCMAKE_BUILD_TYPE=Release \
    "${CMAKE_ARGS[@]}"

THREADS=$(nproc)
echo "Building with $THREADS threads..."
cmake --build "$BUILD_DIR" --config Release -j"$THREADS" -- llama-server

echo ""
echo "Done! Binary at: $BUILD_DIR/bin/llama-server"
"$BUILD_DIR/bin/llama-server" --version
