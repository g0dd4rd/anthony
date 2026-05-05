# Diagnosing Empty Vision Response

## Problem Summary

The vision analysis runs but returns **empty description**:

```
[SYSTEM] ✅ Vision analysis complete!
[OS Feedback]:           ← Empty!
[Agent]:                 ← Empty!
[SYSTEM] Voice error: # channels not specified  ← TTS fails on empty text
```

## What We Know

✅ Screenshot captured successfully  
✅ Image loaded and encoded (342.8 KB)  
✅ Ollama responds (no timeout)  
✅ gemma4:e4b supports vision  
❌ But description is empty  

## Diagnostic Steps

### Step 1: Run Debug Script

This will show exactly what gemma4 returns:

```bash
cd ~/anthony
./debug_gemma_response.py
```

**Look for:**
- Is `content` empty or has text?
- What does the full response object look like?
- Are there any error fields?

---

### Step 2: Test with Simple Image

```bash
./simple_vision_test.py
```

This tests with a simple "HELLO WORLD" image (no complex screenshot).

**If this works:**
- gemma4 vision is working
- Problem is with screenshot analysis specifically
- Maybe screenshots are too complex or large

**If this fails too:**
- gemma4 vision isn't working at all
- Ollama configuration issue
- Model needs to be re-pulled

---

### Step 3: Check Ollama Logs

```bash
journalctl -u ollama -f
```

In another terminal, run the orchestrator and say "describe screen".

**Look for:**
- Vision errors
- Model loading errors
- Out of memory errors
- GPU/VRAM issues

---

### Step 4: Test Ollama CLI Directly

```bash
# Take a screenshot first
gnome-screenshot -f /tmp/test.png

# Test with ollama CLI
ollama run gemma4:e4b
```

Then at the prompt, you can't easily pass images via CLI, but try:

```bash
# Alternative: Use curl
curl http://localhost:11434/api/chat -d '{
  "model": "gemma4:e4b",
  "messages": [{
    "role": "user",
    "content": "Describe this image",
    "images": ["'$(base64 -w0 /tmp/test.png)'"]
  }],
  "stream": false
}'
```

---

## Potential Causes

### Cause 1: Thinking Mode Interference

gemma4 supports "thinking" mode which might interfere with vision output.

**Fix:** Disable thinking for vision (already added):

```python
options={
    'thinking': False,  # Added this
    # ... other options
}
```

---

### Cause 2: num_predict Too Low

With `num_predict: 100`, model stops after 100 tokens (~75 words).

If model uses some tokens for thinking/processing, might have 0 left for output.

**Fix:** Increase to 200:

```python
options={
    'num_predict': 200,  # Increased from 100
}
```

---

### Cause 3: Temperature Too Low

`temperature: 0.3` might make model too conservative with vision.

**Fix:** Try 0.7:

```python
options={
    'temperature': 0.7,  # Increased from 0.3
}
```

---

### Cause 4: Image Too Large

342 KB encoded image might be too large for the context window.

**Fix:** Resize screenshot before encoding:

```python
# After capturing screenshot
from PIL import Image
img = Image.open(screenshot_path)
img.thumbnail((800, 600))  # Resize to max 800x600
img.save('/tmp/resized.png')
# Then encode /tmp/resized.png
```

---

### Cause 5: Model Not Fully Loaded

First vision request might need model to fully load.

**Fix:** Pre-warm model at startup:

```python
# After loading whisper model, before main loop
print("[SYSTEM] Pre-loading gemma4 vision...")
try:
    ollama.chat(
        model='gemma4:e4b',
        messages=[{'role': 'user', 'content': 'test'}],
        options={'num_predict': 1}
    )
    print("[SYSTEM] ✅ Model loaded")
except Exception as e:
    print(f"[SYSTEM] ⚠️ Pre-load failed: {e}")
```

---

### Cause 6: Ollama Version Issue

Older ollama versions might not properly support vision.

**Check version:**
```bash
ollama --version
```

**Update if needed:**
```bash
curl -fsSL https://ollama.com/install.sh | sh
```

---

### Cause 7: Model Corruption

gemma4:e4b might be corrupted.

**Fix:** Re-pull model:

```bash
ollama rm gemma4:e4b
ollama pull gemma4:e4b
```

---

## Quick Fixes to Try

### Fix 1: Increase Token Limit

Edit `voice-driven-orchestrator-mcp-safe.py` line ~167:

```python
'num_predict': 200,  # Was 100
```

### Fix 2: Remove Restrictive Options

Try minimal options:

```python
response = ollama.chat(
    model='gemma4:e4b',
    messages=[{
        'role': 'user',
        'content': 'Describe what you see.',
        'images': [img_data]
    }]
    # No options at all!
)
```

### Fix 3: Different Prompt

Maybe "screenshot" confuses the model. Try:

```python
'content': 'What do you see in this image?',
```

---

## Expected Debug Output

When you run `./debug_gemma_response.py`, you should see:

**If working:**
```
CONTENT:
  Type: <class 'str'>
  Length: 145
  Value: 'The screenshot shows a terminal window running Claude Code...'
```

**If broken:**
```
CONTENT:
  Type: <class 'str'>
  Length: 0
  Value: ''

⚠️  WARNING: Content is EMPTY!
```

---

## Next Steps Based on Results

### If debug script shows content
→ Problem is in how result is passed/displayed  
→ Check main loop tool call handling  

### If debug script shows empty
→ Gemma4 vision not working  
→ Try fixes above (increase num_predict, remove options, re-pull model)  

### If simple test works but screenshot fails
→ Screenshot-specific issue  
→ Try resizing screenshots  
→ Try different image format  

### If nothing works
→ Use different vision model (llava, minicpm-v)  
→ Or use cloud API (Claude API with vision)  

---

## Manual Test

The absolute simplest test:

```python
import ollama, base64

# Create simple test image
import subprocess
subprocess.run(['convert', '-size', '200x100', 'xc:red', '/tmp/red.png'])

with open('/tmp/red.png', 'rb') as f:
    img = base64.b64encode(f.read()).decode()

r = ollama.chat(
    model='gemma4:e4b',
    messages=[{'role': 'user', 'content': 'What color?', 'images': [img]}]
)

print(r['message']['content'])
```

**Expected:** "red" or "The image is red" or similar  
**If empty:** Gemma4 vision definitely broken  

---

## Workaround: Use Different Model

If gemma4 vision doesn't work, try:

```bash
# Faster, smaller
ollama pull moondream:1.8b-v2-q4_K_M

# Better quality
ollama pull llava:13b
```

Then change model in code:
```python
model='moondream:1.8b-v2-q4_K_M',  # Instead of gemma4:e4b
```

---

Run the diagnostic scripts and let me know what you find!
