#!/bin/bash
# Download Gemma 4 GGUF models from Unsloth (no login required)
set -euo pipefail

show_help() {
    cat << 'HELP'
Usage: download_model.sh [OPTIONS]

Download Gemma 4 GGUF models from Unsloth's Hugging Face repos.

Options:
  -m, --model MODEL    Model size: e2b (default) or e4b
  -q, --quant QUANT    Quantization (default: Q4_K_XL)
  --qat                Force QAT variant (default for UD-/XL quants)
  --no-qat             Force regular (non-QAT) variant
  --force              Re-download even if files exist
  -h, --help           Show this help

Quantization guide:
  QAT (Quantization-Aware Training) models preserve more quality at
  low bit widths. The QAT repo only has UD- (Unsloth Dynamic) quants.
  Regular repo has both standard and UD- quants.

  If the quant name contains _XL, QAT is used by default.
  Standard quants (Q4_K_M, Q8_0, etc.) use the regular repo.
  Use --qat / --no-qat to override.

  Standard quants:  Q3_K_S, Q3_K_M, Q4_K_S, Q4_K_M, Q5_K_S, Q5_K_M,
                    Q6_K, Q8_0, BF16
  UD quants:        Q2_K_XL, Q3_K_XL, Q4_K_XL, Q5_K_XL, Q6_K_XL, Q8_K_XL

Examples:
  ./download_model.sh                          # E2B QAT Q4_K_XL (default)
  ./download_model.sh -m e2b -q Q4_K_M         # E2B regular Q4_K_M
  ./download_model.sh -m e4b -q Q4_K_XL        # E4B QAT Q4_K_XL
  ./download_model.sh -m e2b -q Q4_K_XL --no-qat  # E2B regular UD-Q4_K_XL
  ./download_model.sh --force                   # re-download default model
HELP
}

MODEL="e2b"
QUANT="Q4_K_XL"
QAT_OVERRIDE=""
FORCE=false

while [[ $# -gt 0 ]]; do
    case "$1" in
        -m|--model) MODEL="${2,,}"; shift 2 ;;
        -q|--quant) QUANT="$2"; shift 2 ;;
        --qat) QAT_OVERRIDE="yes"; shift ;;
        --no-qat) QAT_OVERRIDE="no"; shift ;;
        --force) FORCE=true; shift ;;
        -h|--help) show_help; exit 0 ;;
        *)
            echo "Unknown option: $1"
            echo "Run with --help for usage."
            exit 1
            ;;
    esac
done

if [[ "$MODEL" != "e2b" && "$MODEL" != "e4b" ]]; then
    echo "Error: model must be e2b or e4b (got: $MODEL)"
    exit 1
fi

# Determine QAT vs regular: XL quants default to QAT, others to regular
if [[ -n "$QAT_OVERRIDE" ]]; then
    USE_QAT="$QAT_OVERRIDE"
elif [[ "$QUANT" == *_XL ]]; then
    USE_QAT="yes"
else
    USE_QAT="no"
fi

# Build repo name and filename
MODEL_UPPER="${MODEL^^}"  # e2b -> E2B
HF_BASE="https://huggingface.co/unsloth"

if [[ "$USE_QAT" == "yes" ]]; then
    REPO="gemma-4-${MODEL_UPPER}-it-QAT-GGUF"
    MODEL_FILE="gemma-4-${MODEL_UPPER}-it-qat-UD-${QUANT}.gguf"
    LABEL="QAT"
else
    REPO="gemma-4-${MODEL_UPPER}-it-GGUF"
    if [[ "$QUANT" == *_XL ]]; then
        MODEL_FILE="gemma-4-${MODEL_UPPER}-it-UD-${QUANT}.gguf"
    else
        MODEL_FILE="gemma-4-${MODEL_UPPER}-it-${QUANT}.gguf"
    fi
    LABEL="regular"
fi

# mmproj is the same across QAT and regular repos
MMPROJ_REMOTE="mmproj-BF16.gguf"
MMPROJ_LOCAL="mmproj-${MODEL}-bf16.gguf"

MODEL_URL="$HF_BASE/$REPO/resolve/main/$MODEL_FILE"
MMPROJ_URL="$HF_BASE/$REPO/resolve/main/$MMPROJ_REMOTE"

MODELS_DIR="$HOME/models"
mkdir -p "$MODELS_DIR"

echo "=================================================="
echo "Downloading Gemma 4 ${MODEL_UPPER} ${QUANT} (${LABEL})"
echo "=================================================="
echo "Repo:   $REPO"
echo "Model:  $MODEL_FILE"
echo "mmproj: $MMPROJ_REMOTE → $MMPROJ_LOCAL"
echo "Target: $MODELS_DIR/"
echo ""

download_file() {
    local url="$1"
    local dest="$2"
    local label="$3"

    if [ -f "$dest" ] && [ "$FORCE" = false ]; then
        echo "✓ $label already exists, skipping (use --force to re-download)"
        return 0
    fi

    echo "Downloading $label..."
    if curl -L -C - --progress-bar -o "$dest" "$url"; then
        local size
        size=$(stat --format=%s "$dest" 2>/dev/null || stat -f%z "$dest" 2>/dev/null)
        echo "✓ $label downloaded ($(( size / 1048576 )) MB)"
    else
        echo "✗ Failed to download $label"
        rm -f "$dest"
        return 1
    fi
}

download_file "$MODEL_URL" "$MODELS_DIR/$MODEL_FILE" "$MODEL_FILE"
download_file "$MMPROJ_URL" "$MODELS_DIR/$MMPROJ_LOCAL" "$MMPROJ_LOCAL"

echo ""
echo "Done! Models are in $MODELS_DIR/"
ls -lh "$MODELS_DIR/"*.gguf 2>/dev/null
