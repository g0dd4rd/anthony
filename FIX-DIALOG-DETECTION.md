# Fixing Dialog Detection Issues

## 🐛 Problem Summary

From your test:
```
[SYSTEM] Checking for save dialog...
[OS Feedback]: Window hello world (Draft) - Text Editor closed (or dialog handling needed)
```

**What happened:**
1. Close command sent to text editor
2. Dialog appeared (you saw it)
3. Our code said "no dialog detected"
4. You manually tried "press the save button" → interpreted as Ctrl+S instead

**Root cause:** Dialog detection is failing!

## 🔍 Debug Changes Applied

### 1. Added Verbose Logging

The dialog_handler now prints:
- How many dialogs found
- What app each dialog belongs to
- Dialog title, message, buttons
- Whether it matches save dialog criteria

### 2. Increased Timeout

- **Before:** 1.5 seconds
- **Now:** 3 seconds (first try), 5 seconds (retry)

### 3. Removed App Filter

- **Before:** Filtered by app name (might be too strict)
- **Now:** Checks ALL dialogs (more reliable)

## 🧪 Test to Run

### Test 1: Standalone Dialog Detection

```bash
cd ~/anthony
./test_dialog_detection.py
```

**Steps:**
1. Open text editor: `gnome-text-editor &`
2. Type some text
3. Press Ctrl+Q (don't click anything in dialog)
4. Switch to terminal and press Enter

**Expected output:**
```
[TEST] Found 1 dialogs

Dialog 1:
  Name: Save Changes?
  Role: alert
  App: org.gnome.TextEditor
  Message: Save changes to document...
  Buttons: ['Cancel', 'Discard', 'Save']

✅ detect_save_dialog() WORKS!
```

**If it shows 0 dialogs:**
- Accessibility issue
- Dialog not accessible
- Need to check dogtail setup

---

### Test 2: Full Orchestrator

```bash
./voice-driven-orchestrator-mcp-safe.py
```

**Say:** "open text editor"
**Type** some text manually
**Say:** "close text editor"

**Expected output (NEW with debug logging):**
```
[SYSTEM] Attempting to close: hello world (Draft) - Text Editor
[SYSTEM] Checking for save dialog (app: org.gnome.TextEditor)...
[Dialog] Searching for dialogs (timeout: 3.0s, app filter: none)...
[Dialog] Check #1: Found 1 dialog(s)
[Dialog]   - Dialog in 'org.gnome.TextEditor': 'Save Changes?'
[Dialog]     Title: Save Changes?
[Dialog]     Message: Save changes to document before closing?
[Dialog]     Buttons: ['Cancel', 'Discard', 'Save']
[Dialog]     ✅ MATCH! This looks like a save dialog
[SYSTEM] 💬 Save dialog detected!

[Agent]: The window has unsaved changes. Options: Cancel, Discard, Save. What would you like to do?

🎤 [VAD] Listening...
```

**Then say:** "save" or "discard" or "cancel"

**Expected:**
```
✅ You said: "save"
[Dialog] Clicking button: Save
✅ Successfully closed Text Editor
```

---

## 🔧 Possible Issues & Fixes

### Issue 1: No dialogs found

**Symptoms:**
```
[Dialog] Check #1: Found 0 dialog(s)
[Dialog] No save dialog found after 30 checks over 3.0s
```

**Causes:**
1. **Accessibility not enabled** 
   ```bash
   gsettings get org.gnome.desktop.interface toolkit-accessibility
   # Should be: true
   ```

2. **Text editor not accessible**
   ```bash
   python3 -c "
   from dogtail.tree import root
   apps = [app.name for app in root.applications()]
   print(apps)
   "
   # Should include 'org.gnome.TextEditor' or similar
   ```

3. **Dialog appears too late**
   - Text editor might be slow
   - Increase timeout to 10 seconds

**Fix:**
```python
# In voice-driven-orchestrator-mcp-safe.py, line ~300
dialog = dialog_handler.detect_save_dialog(app_name=None, timeout=10.0)
```

---

### Issue 2: Dialog found but not matched

**Symptoms:**
```
[Dialog] Found 1 dialog(s)
[Dialog]   - Dialog in 'org.gnome.TextEditor': 'Close Document'
[Dialog]     Not a save dialog (no matching keywords)
```

**Cause:** Dialog text doesn't contain our keywords

**Fix:** Add more keywords in `dialog_handler.py` line ~180:

```python
save_keywords = [
    'save', 'discard', 'changes', 'close without saving',
    'don\'t save', 'cancel', 'without saving', 'unsaved',
    'close document', 'keep changes'
]
```

---

### Issue 3: Dialog filtered out by app name

This shouldn't happen anymore (we removed app filter), but if it does:

**Check what app name dogtail sees:**
```bash
./test_dialog_detection.py
# Look at "App:" field
```

Might be:
- `org.gnome.TextEditor`
- `TextEditor`
- `gnome-text-editor`

---

### Issue 4: Buttons not found

**Symptoms:**
```
Dialog appeared but no buttons found
```

**Cause:** Button detection failing

**Debug:**
```python
from dogtail.tree import root
app = root.application('org.gnome.TextEditor')

def print_tree(elem, indent=0):
    print("  " * indent + f"{elem.roleName}: {elem.name}")
    for child in elem.children:
        print_tree(child, indent + 1)

print_tree(app)
```

Look for buttons - they might have different roleName.

**Fix:** Update button detection in `dialog_handler.py` line ~138:

```python
buttons = dialog_element.findChildren(
    lambda x: x.roleName in ['push button', 'button'] and x.showing,
    recursive=True
)
```

---

## 🎯 Expected Behavior (When Working)

1. **You say:** "close text editor"
2. **Agent does:**
   - Sends close command
   - Detects dialog (3-5 seconds)
   - Reads dialog to you via TTS
3. **You hear:** "The window has unsaved changes. Options: Cancel, Discard, Save. What would you like to do?"
4. **You say:** "save" (or your choice)
5. **Agent does:**
   - Clicks Save button via dogtail
   - Verifies window closed
6. **You hear:** "Successfully closed Text Editor"

---

## 📊 Debugging Checklist

Run these in order:

- [ ] **Check accessibility:** `gsettings get org.gnome.desktop.interface toolkit-accessibility` = true
- [ ] **Test dogtail:** `./test_dialog_detection.py` finds dialogs
- [ ] **Check timeout:** See if increasing to 10s helps
- [ ] **Check keywords:** Dialog text matches our keywords
- [ ] **Check buttons:** Buttons are detected
- [ ] **Test orchestrator:** Full end-to-end with debug output

---

## 🚀 Quick Fix Attempts

### Try 1: Increase Timeout
```python
# Line ~300 in voice-driven-orchestrator-mcp-safe.py
dialog = dialog_handler.detect_save_dialog(app_name=None, timeout=10.0)
```

### Try 2: More Keywords
```python
# Line ~180 in dialog_handler.py
save_keywords = ['save', 'discard', 'changes', 'cancel', 'without saving', 
                'unsaved', 'close', 'keep']
```

### Try 3: Different Button Detection
```python
# Line ~138 in dialog_handler.py
buttons = dialog_element.findChildren(
    lambda x: 'button' in x.roleName.lower() and x.showing,
    recursive=True
)
```

---

## 📝 Next Steps

1. Run `./test_dialog_detection.py` and share output
2. Run orchestrator with new debug logging
3. Share the `[Dialog]` debug output
4. We'll see exactly where detection fails
5. Apply targeted fix

The debug logging will show us EXACTLY what's happening!
