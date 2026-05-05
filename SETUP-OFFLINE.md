# Offline Setup for Voice Orchestrator

The voice orchestrator uses a semantic embedding model for intelligent tool selection. This requires a **one-time download** of the model, after which the system works completely offline.

## One-Time Setup (Requires Internet)

Run this once to download and cache the embedding model:

```bash
python3 << 'EOF'
from sentence_transformers import SentenceTransformer
print("Downloading embedding model (one-time, ~80MB)...")
model = SentenceTransformer('all-MiniLM-L6-v2')
print("✓ Model cached successfully!")
print(f"✓ Location: {model.model_card_data.model_name}")
EOF
```

**What this does:**
- Downloads `all-MiniLM-L6-v2` model from HuggingFace
- Caches it in `~/.cache/huggingface/hub/`
- Size: ~80MB
- Required once per user account

## After Setup

Once cached, the orchestrator runs **fully offline**:
- No internet checks
- No HuggingFace API calls
- Uses cached model only

The code sets these environment variables:
```python
os.environ['TRANSFORMERS_OFFLINE'] = '1'
os.environ['HF_HUB_OFFLINE'] = '1'
```

## Verify Offline Mode

Test that the model works offline:

```bash
# Disconnect from internet or use:
python3 -c "
import os
os.environ['TRANSFORMERS_OFFLINE'] = '1'
os.environ['HF_HUB_OFFLINE'] = '1'

from sentence_transformers import SentenceTransformer
model = SentenceTransformer('all-MiniLM-L6-v2')
print('✓ Works offline!')
"
```

## Troubleshooting

**Error: "OSError: Can't load tokenizer"**
- Model not cached yet
- Run the one-time setup above

**Warning: "You are sending unauthenticated requests"**
- This warning should not appear with offline mode enabled
- If you see it, the environment variables aren't set correctly

## Alternative: Fully Offline Installation

If you need to install on a machine without internet access:

1. On a machine **with internet**, download the model:
   ```bash
   python3 -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"
   ```

2. Copy the cache directory to the offline machine:
   ```bash
   # Source machine (with internet)
   tar -czf sentence-transformer-model.tar.gz -C ~/.cache/huggingface hub/models--sentence-transformers--all-MiniLM-L6-v2
   
   # Transfer file to offline machine
   
   # Target machine (offline)
   mkdir -p ~/.cache/huggingface/hub
   tar -xzf sentence-transformer-model.tar.gz -C ~/.cache/huggingface
   ```

3. Verify on offline machine:
   ```bash
   ls ~/.cache/huggingface/hub/models--sentence-transformers--all-MiniLM-L6-v2
   ```

## Model Details

- **Name:** all-MiniLM-L6-v2
- **Purpose:** Semantic text embedding for tool namespace matching
- **Size:** ~80MB
- **License:** Apache 2.0
- **Source:** HuggingFace / sentence-transformers
- **URL:** https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2
