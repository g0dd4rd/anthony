# Testing Safe Dialog Handling

## 🧪 Test Suite for Dialog Handler

### Prerequisites
```bash
# Verify dependencies
python3 -c "import dogtail; print('✅ dogtail OK')"
python3 -c "import torch; print('✅ torch OK')"
python3 -c "from faster_whisper import WhisperModel; print('✅ whisper OK')"
```

---

## Test 1: Dialog Detection (Standalone)

### Setup
```bash
cd ~/anthony
./dialog_handler.py
```

### Steps
1. Script will prompt: "Press Enter when ready to test..."
2. Open gnome-text-editor: `gnome-text-editor &`
3. Type some text (e.g., "Hello World")
4. Press **Ctrl+Q** or click the close button (X)
5. **DO NOT click any buttons in the dialog yet**
6. Go back to terminal and press Enter

### Expected Output
```
✅ Dialog detected!

Dialog: Save Changes?
Message: Save changes to document before closing?
Options: Cancel, Discard, Save

Available buttons:
  1. Cancel
  2. Discard
  3. Save

Enter button text to click (or 'cancel' to skip):
```

### Test Cases

**Test 1a: Click "Save"**
- Type: `save`
- Expected: ✅ Dialog closed successfully

**Test 1b: Click "Discard"**
- Repeat setup, type: `discard`
- Expected: ✅ Dialog closed successfully

**Test 1c: Click "Cancel"**
- Repeat setup, type: `cancel`
- Expected: ✅ Dialog closed successfully, text editor still open

**Test 1d: Fuzzy matching**
- Repeat setup, type: `don't save` (alternative to "Discard")
- Expected: Should click "Discard" button

---

## Test 2: Full Voice Orchestrator (Safe Version)

### Setup
```bash
cd ~/anthony
./voice-driven-orchestrator-mcp-safe.py
```

### Wait for initialization
```
[SYSTEM] MCP connected to gnome-desktop-mcp
[SYSTEM] VAD model loaded.
🎤 [VAD] Listening...
```

---

### Test 2a: Close without unsaved changes

**Steps:**
1. Say: **"Launch text editor"**
2. Wait for app to open
3. Say: **"Close text editor"**

**Expected:**
```
[SYSTEM] Attempting to close: Text Editor
[SYSTEM] Checking for save dialog...
✅ Successfully closed Text Editor
```

No dialog should appear (no unsaved changes).

---

### Test 2b: Close with unsaved changes - SAVE

**Steps:**
1. Say: **"Launch text editor"**
2. Manually type some text in the editor
3. Say: **"Close text editor"**

**Expected:**
```
[SYSTEM] 💬 Save dialog detected!
[Agent]: The window has unsaved changes. Options: Cancel, Discard, Save. What would you like to do?

🎤 [VAD] Listening...
```

4. Say: **"Save"**

**Expected:**
```
✅ You said: "Save"
[DIALOG] User chose: Save
[DIALOG] Clicking button: Save
✅ Successfully closed Text Editor
```

Text editor should close, file saved (or save-as dialog appears if new file).

---

### Test 2c: Close with unsaved changes - DISCARD

**Steps:**
1. Say: **"Launch text editor"**
2. Manually type some text in the editor
3. Say: **"Close text editor"**
4. Wait for voice prompt
5. Say: **"Discard"** or **"Don't save"**

**Expected:**
```
✅ You said: "Discard"
[DIALOG] User chose: Discard
[DIALOG] Clicking button: Discard
✅ Successfully closed Text Editor
```

Text editor should close without saving.

---

### Test 2d: Close with unsaved changes - CANCEL

**Steps:**
1. Say: **"Launch text editor"**
2. Manually type some text in the editor
3. Say: **"Close text editor"**
4. Wait for voice prompt
5. Say: **"Cancel"**

**Expected:**
```
✅ You said: "Cancel"
[DIALOG] User chose: Cancel
[DIALOG] Clicking button: Cancel
Dialog closed. Window Text Editor is still open (you may have chosen Cancel)
```

Dialog should close but text editor remains open with your text intact.

---

### Test 2e: No response to dialog prompt

**Steps:**
1. Say: **"Close text editor"** (with unsaved changes)
2. Wait for voice prompt
3. **Don't say anything** (let it timeout)

**Expected:**
```
[Agent]: The window has unsaved changes. Options: Cancel, Discard, Save. What would you like to do?
🎤 [VAD] Listening...
⚠️  Too short (0.3s), ignoring...
[Agent]: No response heard. Canceling close operation.
Close operation canceled - no user input
```

Dialog should close (Escape pressed), text editor remains open.

---

## Test 3: Different Applications

### Test 3a: LibreOffice Writer

**Steps:**
1. Launch: `libreoffice --writer &`
2. Type some text
3. Say: **"Close LibreOffice"**

**Expected:**
Should detect save dialog and read options (might be "Save Document?", "Yes, No, Cancel").

### Test 3b: gedit

**Steps:**
1. Launch: `gedit &`
2. Type some text
3. Say: **"Close gedit"**

**Expected:**
Should detect save dialog and handle appropriately.

### Test 3c: Firefox (unsaved form data)

**Note:** Firefox may not show accessibility dialogs via dogtail. This is a known limitation.

---

## Test 4: Edge Cases

### Test 4a: Multiple dialogs

**Steps:**
1. Open two text editors with unsaved changes
2. Say: **"Close text editor"**

**Expected:**
Closes the focused one, handles its dialog.

### Test 4b: No microphone input

**Setup:**
Mute microphone or disconnect it temporarily.

**Expected:**
VAD should timeout, operation canceled gracefully.

### Test 4c: Ambiguous voice input

**Steps:**
1. Close text editor with unsaved changes
2. When prompted, say something unclear: **"Maybe save it"**

**Expected:**
Should attempt fuzzy matching with "save". If no match, reports error and suggests Escape.

---

## Troubleshooting

### Dialog not detected
```bash
# Check if dogtail can see the app
python3 -c "
from dogtail.tree import root
for app in root.applications():
    print(app.name)
"
```

Should show running applications. If text editor not listed, it may not be accessibility-enabled.

### Buttons not found
```bash
# Debug dialog structure
python3 -c "
from dogtail.tree import root
app = root.application('org.gnome.TextEditor')
for child in app.children:
    print(f'{child.roleName}: {child.name}')
"
```

### Voice recognition fails
- Check microphone: `arecord -d 2 test.wav && aplay test.wav`
- Adjust VAD threshold in `voice-driven-orchestrator-mcp-safe.py`:
  ```python
  VAD_THRESHOLD = 0.3  # Lower = more sensitive
  ```

### Dialog closes but window doesn't
This is **correct behavior** if user chose "Cancel". The dialog should close and window stays open.

---

## Success Criteria

✅ Dialog detected within 1.5 seconds of close attempt  
✅ All buttons (Save, Discard, Cancel) correctly identified  
✅ Options spoken clearly via TTS  
✅ User voice input recognized correctly  
✅ Chosen button clicked successfully  
✅ Window state verified after action  
✅ No data lost without user consent  
✅ Graceful handling of no user input  

---

## Known Limitations

1. **App must be accessibility-enabled**
   - Most GNOME apps: ✅ Work
   - Some Qt apps: ⚠️ May not work
   - Electron apps: ⚠️ Hit or miss

2. **Dialog timing**
   - 1.5 second window to detect dialog
   - If app is very slow, might miss it
   - Adjust timeout in `close_window_by_name()`:
     ```python
     dialog = dialog_handler.detect_save_dialog(app_name=app_name, timeout=3.0)
     ```

3. **Voice recognition accuracy**
   - Depends on microphone quality
   - Background noise can affect VAD
   - Accents may need prompt tuning

4. **Custom dialogs**
   - Some apps use non-standard dialogs
   - May not be detected by dogtail
   - Fallback: manual Escape key

---

## Reporting Issues

If a test fails, gather this info:

```bash
# 1. Check accessibility
gsettings get org.gnome.desktop.interface toolkit-accessibility

# Should be: true

# 2. Test dogtail manually
python3 dialog_handler.py

# 3. Check GNOME Shell logs
journalctl --user -u gnome-shell --since "1 minute ago"

# 4. Check audio devices
arecord -l
```

Include test name, expected vs actual behavior, and above outputs.

---

## Quick Reference

| Test | Command | Expected Result |
|------|---------|-----------------|
| Standalone dialog test | `./dialog_handler.py` | Detects and lists buttons |
| Full orchestrator | `./voice-driven-orchestrator-mcp-safe.py` | Voice interaction works |
| Save option | Say "Save" | Saves and closes |
| Discard option | Say "Discard" | Closes without saving |
| Cancel option | Say "Cancel" | Keeps window open |
| No response | (silence) | Cancels operation |

---

**Safety First:** This version ensures you never lose data accidentally! 🛡️
