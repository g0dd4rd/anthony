# Fixes for Ctrl+C and Screen Description Issues

## Problems Identified

### Problem 1: Can't Exit with Ctrl+C

**Root Cause:**
```python
# In listen_and_transcribe() line 513-517
except KeyboardInterrupt:
    stream.stop_stream()
    stream.close()
    p.terminate()
    return ""  # ❌ Returns empty string instead of exiting!
```

**Result:**
- Ctrl+C during listening returns ""
- Main loop does `if not user_input: continue`
- Loop just restarts listening
- Agent never exits!

**Fix:** Re-raise KeyboardInterrupt instead of returning ""

---

### Problem 2: No Output for Screen Description

**Potential Causes:**

1. **Ollama hanging (most likely)**
   ```python
   # Line 147-160: No timeout!
   response = ollama.chat(model='gemma4:e4b', ...)
   # If ollama is unresponsive, hangs forever
   ```

2. **No progress output**
   - User doesn't know vision analysis is running
   - Could take 2-4 seconds with no feedback
   - Looks like nothing is happening

3. **Model not loaded**
   - gemma4:e4b might not be loaded in ollama
   - First call loads model (can take 10-30 seconds)
   - No progress indicator

4. **Tool not being called**
   - Ollama orchestrator might not recognize "describe screen"
   - Need to check if tool_call is actually happening

---

## Solutions

### Fix 1: Ctrl+C Handling

**Change in `listen_and_transcribe()`:**

```python
except KeyboardInterrupt:
    stream.stop_stream()
    stream.close()
    p.terminate()
    raise  # ✅ Re-raise instead of returning ""
```

**Change in main loop:**

```python
while True:
    try:
        user_input = listen_and_transcribe()
        if not user_input:
            continue
        
        # ... rest of processing
        
    except KeyboardInterrupt:
        print("\n[SYSTEM] Shutting down...")
        break  # Exit the loop
```

---

### Fix 2: Screen Description Debugging

**Add progress output:**

```python
def describe_desktop() -> str:
    print(f"\n[SYSTEM] Capturing screenshot with MCP...")
    
    # Capture
    result = mcp_client.call_tool("screenshot", ...)
    screenshot_path = result.strip()
    print(f"[SYSTEM] ✅ Screenshot saved: {screenshot_path}")
    
    # Load image
    print(f"[SYSTEM] 📊 Loading screenshot for analysis...")
    with open(screenshot_path, 'rb') as img_file:
        img_data = base64.b64encode(img_file.read()).decode('utf-8')
    
    # Analyze (this is the slow part)
    print(f"[SYSTEM] 🤖 Analyzing with gemma4 vision (2-4 seconds)...")
    
    response = ollama.chat(...)
    
    print(f"[SYSTEM] ✅ Analysis complete!")
    return description
```

**Add timeout to ollama call:**

Unfortunately, ollama Python library doesn't have a timeout parameter, but we can:
1. Check if ollama is running
2. Check if model is loaded
3. Use subprocess timeout wrapper

---

## Quick Fixes to Apply

### File: `voice-driven-orchestrator-mcp-safe.py`

**Location 1: Line 513-517**

Change:
```python
except KeyboardInterrupt:
    stream.stop_stream()
    stream.close()
    p.terminate()
    return ""
```

To:
```python
except KeyboardInterrupt:
    stream.stop_stream()
    stream.close()
    p.terminate()
    print("\n[VAD] Ctrl+C detected")
    raise  # Re-raise to exit main loop
```

---

**Location 2: Line 550-592 (main loop)**

Change:
```python
def run_agent():
    # ... setup ...
    
    while True:
        user_input = listen_and_transcribe()
        if not user_input:
            continue
        
        # ... processing ...
```

To:
```python
def run_agent():
    # ... setup ...
    
    try:
        while True:
            user_input = listen_and_transcribe()
            if not user_input:
                continue
            
            # ... processing ...
    
    except KeyboardInterrupt:
        print("\n[SYSTEM] Received Ctrl+C, shutting down...")
```

---

**Location 3: Line 141-160 (describe_desktop)**

Add progress output:

```python
screenshot_path = result.strip()
print(f"[SYSTEM] ✅ Screenshot: {screenshot_path}")

with open(screenshot_path, 'rb') as img_file:
    import base64
    img_data = base64.b64encode(img_file.read()).decode('utf-8')

print(f"[SYSTEM] 🤖 Running vision analysis (please wait 2-4 seconds)...")

response = ollama.chat(
    model='gemma4:e4b',
    # ... rest
)

print(f"[SYSTEM] ✅ Vision analysis complete")
description = response['message']['content']
```

---

## Debugging Screen Description

### Test 1: Check if gemma4 is loaded

```bash
ollama list | grep gemma4
```

**Expected:**
```
gemma4:e4b    c6eb396dbd59    9.6 GB    4 days ago
```

If not listed, pull it:
```bash
ollama pull gemma4:e4b
```

---

### Test 2: Test ollama directly

```bash
# Test text generation
ollama run gemma4:e4b "Say hello"

# Should respond quickly (model already loaded)
```

If this hangs, ollama service might be stuck:
```bash
# Check ollama status
systemctl status ollama

# Restart if needed
systemctl restart ollama
```

---

### Test 3: Test vision function directly

```python
# test_vision.py
import ollama
import base64

# Take a screenshot first
with open('/tmp/test_screenshot.png', 'rb') as f:
    img_data = base64.b64encode(f.read()).decode('utf-8')

print("Sending to ollama...")

response = ollama.chat(
    model='gemma4:e4b',
    messages=[{
        'role': 'user',
        'content': 'Describe this image briefly.',
        'images': [img_data]
    }]
)

print("Response:", response['message']['content'])
```

---

### Test 4: Check tool is being called

Add debug output in main loop:

```python
if message.get('tool_calls'):
    print(f"[DEBUG] Tool calls detected: {len(message['tool_calls'])}")
    
    for tool_call in message['tool_calls']:
        tool_name = tool_call['function']['name']
        print(f"[DEBUG] Calling tool: {tool_name}")
        arguments = tool_call['function']['arguments']
        print(f"[DEBUG] Arguments: {arguments}")
        
        # ... rest
```

This will show if the orchestrator is actually calling describe_desktop or not.

---

## Common Issues

### Issue: "describe desktop" not triggering tool

**Cause:** Ollama orchestrator might not understand the phrase.

**Solution:** Try exact phrases:
- ✅ "describe the desktop"
- ✅ "what's on screen"
- ✅ "take screenshot and describe"
- ❌ "describe desktop" (too short, might not trigger)

Or add to tool description:

```python
{
    "name": "describe_desktop",
    "description": "Captures a screenshot of the desktop and describes what is visible. Use when user asks 'what's on screen', 'describe desktop', 'what do you see', or similar vision requests.",
    # ...
}
```

---

### Issue: Ollama timeout/hang

**Symptoms:**
- Script stops at "Running vision analysis"
- No error message
- Ctrl+C doesn't work

**Cause:** Ollama process stuck or overloaded.

**Solution:**
```bash
# Check ollama processes
ps aux | grep ollama

# Kill and restart
pkill ollama
systemctl restart ollama

# Or restart service
sudo systemctl restart ollama
```

---

### Issue: Model loading very slow

**Symptoms:**
- First request takes 30+ seconds
- Subsequent requests fast

**Cause:** Model needs to load into RAM/VRAM first time.

**Solution:**
Pre-load model at startup:

```python
# Add after line 420
print("[SYSTEM] Pre-loading gemma4 vision model...")
try:
    ollama.chat(
        model='gemma4:e4b',
        messages=[{'role': 'user', 'content': 'ping'}],
        options={'num_predict': 1}
    )
    print("[SYSTEM] ✅ Model loaded")
except Exception as e:
    print(f"[SYSTEM] ⚠️ Model pre-load failed: {e}")
```

---

## Testing the Fixes

### Test Ctrl+C Fix

```bash
./voice-driven-orchestrator-mcp-safe.py

# Wait for "🎤 [VAD] Listening..."
# Press Ctrl+C

# Expected:
[VAD] Ctrl+C detected
[SYSTEM] Received Ctrl+C, shutting down...
# (exits cleanly)
```

### Test Screen Description

```bash
./voice-driven-orchestrator-mcp-safe.py

# Say: "describe the desktop"

# Expected output:
[SYSTEM] Executing command: describe_desktop...
[SYSTEM] Capturing screenshot with MCP...
[SYSTEM] ✅ Screenshot: /tmp/gnome-desktop-screenshot-xyz.png
[SYSTEM] 🤖 Running vision analysis (please wait 2-4 seconds)...
[SYSTEM] ✅ Vision analysis complete

[OS Feedback]: The desktop shows Claude Code terminal window in the center...
```

If it hangs at "Running vision analysis", check ollama service.

---

## Summary

**Fix Ctrl+C:**
1. Change `return ""` to `raise` in listen_and_transcribe exception handler
2. Wrap main loop in try/except KeyboardInterrupt
3. Break out of loop on Ctrl+C

**Fix Screen Description:**
1. Add progress output (let user know it's working)
2. Check ollama service is running
3. Verify gemma4 model is loaded
4. Add debug output to see if tool is called
5. Test ollama vision directly to isolate issue

**Quick diagnostic:**
```bash
# Is ollama running?
ollama list

# Does gemma4 respond?
ollama run gemma4:e4b "test"

# Can vision work?
# (run test_vision.py with a screenshot)
```
