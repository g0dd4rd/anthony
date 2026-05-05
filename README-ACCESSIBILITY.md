# Accessibility & Dialog Handling - Quick Overview

## TL;DR

✅ **Your system is already set up correctly!**

- Accessibility is enabled: `true`
- gnome-desktop-mcp: Working (does NOT handle a11y)
- dogtail: Will work (needs a11y, which you have)
- Our scripts: Auto-check and enable a11y if needed

**You don't need to do anything!** Just run the scripts.

---

## What You Asked

> "btw dogtail needs enabled a11y to work, did you enable it via gsettings, or the gnome-desktop-mcp enables it itself perhaps via its gnome extension?"

**Answer:**

1. **Dogtail:** ✅ Requires `toolkit-accessibility true`
2. **Did I enable it?** ✅ Scripts NOW auto-check/enable (I added this)
3. **gnome-desktop-mcp:** ❌ Does NOT enable accessibility (confirmed via code inspection)

**Current state on your system:**
```bash
$ gsettings get org.gnome.desktop.interface toolkit-accessibility
true  # ← Already enabled (you or Fedora did this)
```

---

## How It Works Now

### gnome-desktop-mcp Extension
**Does:**
- ✅ Window management (list, focus, close, move, resize)
- ✅ Screenshots
- ✅ Keyboard/mouse input injection
- ✅ Monitor information

**Does NOT:**
- ❌ Enable accessibility
- ❌ Detect dialogs
- ❌ Inspect UI elements

**Method:** D-Bus API calls to GNOME Shell

---

### dialog_handler.py (Our Code)
**Does:**
- ✅ Auto-checks if accessibility is enabled
- ✅ Auto-enables if needed
- ✅ Detects dialogs via accessibility tree
- ✅ Reads dialog text and buttons
- ✅ Simulates button clicks

**Requires:**
- ✅ `toolkit-accessibility true`
- ✅ dogtail library
- ✅ Apps must support accessibility

**Method:** AT-SPI (Assistive Technology Service Provider Interface)

---

## Two Different Systems

| | gnome-desktop-mcp | dogtail |
|---|---|---|
| **Purpose** | Window/input control | UI inspection |
| **Protocol** | D-Bus | AT-SPI |
| **Requires** | GNOME Shell extension | Accessibility enabled |
| **Setup** | Install extension | Enable a11y setting |
| **Speed** | Fast | Moderate |
| **Scope** | All windows | Only a11y apps |
| **Dialog handling** | ❌ No | ✅ Yes |

**Why we use both:**
- MCP for fast window operations
- dogtail for detailed dialog inspection

They're complementary, not redundant!

---

## What Changed in Your Scripts

### Before (My Original Code)
```python
# dialog_handler.py
from dogtail.tree import root, SearchError

class DialogHandler:
    def __init__(self):
        self.last_dialog = None
        # ❌ No accessibility check!
```

**Problem:** Would fail silently if a11y was disabled.

### After (Updated Code)
```python
# dialog_handler.py
class DialogHandler:
    def __init__(self):
        self.last_dialog = None
        self._ensure_accessibility_enabled()  # ✅ Auto-check/enable

    def _ensure_accessibility_enabled(self):
        """Check and enable if needed"""
        result = subprocess.run(['gsettings', 'get', ...])
        if result.stdout.strip() != 'true':
            subprocess.run(['gsettings', 'set', ...])
            print("✅ Accessibility enabled")
```

**Benefits:**
- ✅ Automatic detection
- ✅ Automatic enablement
- ✅ Clear user feedback
- ✅ Graceful handling

---

## Testing

### Test 1: Verify Accessibility
```bash
gsettings get org.gnome.desktop.interface toolkit-accessibility
```

**Expected:** `true`

### Test 2: Run Dialog Handler
```bash
./dialog_handler.py
```

**Expected output:**
```
[A11Y] ✅ Accessibility already enabled
Press Enter when ready to test...
```

### Test 3: Run Safe Orchestrator
```bash
./voice-driven-orchestrator-mcp-safe.py
```

**Expected in startup:**
```
[SYSTEM] Initializing dialog handler...
[A11Y] ✅ Accessibility already enabled
[SYSTEM] Loading Neural Voice...
```

---

## If Accessibility Was Disabled

### Scenario: Fresh System
```bash
$ gsettings get org.gnome.desktop.interface toolkit-accessibility
false  # ← Not enabled
```

### What Our Scripts Do
```bash
$ ./dialog_handler.py

[A11Y] ⚠️  Accessibility not enabled. Enabling now...
[A11Y] ✅ Accessibility enabled.
[A11Y] ⚠️  NOTE: You may need to restart applications for full a11y support.
[A11Y]      For best results, log out and log back in.
```

**Then:**
- New apps: Work immediately
- Running apps: May need restart
- Full support: Log out/in recommended (not required)

---

## Why Accessibility Was Already Enabled

Possible reasons on your Fedora system:

1. **Fedora Workstation default:** May enable it out of box
2. **Previous setup:** You or another tool enabled it
3. **Accessibility features:** Using screen reader, magnifier, etc.
4. **Development tools:** Some dev tools enable it

**Doesn't matter why - it works!** 🎉

---

## Dependencies Summary

### System Level
```bash
# Required for dialog handling
gsettings set org.gnome.desktop.interface toolkit-accessibility true

# Required for gnome-desktop-mcp
# (GNOME Shell extension already installed and active)
```

### Python Level
```bash
# Required for dialog handling
pip install dogtail

# Required for VAD
pip install torch

# Already installed
pip install faster-whisper piper-tts mcp ollama pyaudio
```

---

## Documentation Files

- **`ACCESSIBILITY-SETUP.md`** - Detailed a11y explanation (what you asked about)
- **`README-ACCESSIBILITY.md`** - This file (quick overview)
- **`changes.md`** - All version changes
- **`TEST-SAFE-DIALOG.md`** - Testing guide

---

## Key Takeaways

1. ✅ **gnome-desktop-mcp:** Does NOT touch accessibility settings
2. ✅ **dogtail:** Requires accessibility (our scripts now handle this)
3. ✅ **Your system:** Already has a11y enabled
4. ✅ **Scripts:** Now auto-check and auto-enable
5. ✅ **No manual action needed:** Everything works!

---

## Quick Command Reference

```bash
# Check accessibility
gsettings get org.gnome.desktop.interface toolkit-accessibility

# Enable manually (our scripts do this automatically)
gsettings set org.gnome.desktop.interface toolkit-accessibility true

# Test dogtail
python3 -c "from dogtail.tree import root; print([a.name for a in root.applications()])"

# Test dialog handler
./dialog_handler.py

# Run safe orchestrator (includes a11y check)
./voice-driven-orchestrator-mcp-safe.py
```

---

**Bottom line:** You caught an important requirement that I initially missed. The scripts now properly handle it automatically. Thank you for the excellent question! 🙏
