# Accessibility (a11y) Setup for Dialog Handling

## Why Accessibility is Needed

**Dogtail** (the library we use for dialog detection) requires GNOME's assistive technology support to be enabled. This allows it to:

- Inspect the accessibility tree of running applications
- Find UI elements (buttons, labels, dialogs)
- Simulate clicks and interactions
- Read element properties (text, state, position)

**Without accessibility enabled:** Dogtail cannot see any UI elements, and dialog detection will fail.

---

## Current Status on Your System

✅ **Accessibility is already enabled** on your system:

```bash
$ gsettings get org.gnome.desktop.interface toolkit-accessibility
true
```

This is why the dialog handler works! 🎉

---

## How Accessibility Got Enabled

The **gnome-desktop-mcp extension does NOT enable accessibility**. I verified:

```bash
$ grep -r "accessibility" ~/.local/share/gnome-shell/extensions/desktop-automation@gnomemcp.github.io/
# No results
```

Possible reasons it's already enabled:
1. **Fedora default:** Some Fedora spins enable it by default
2. **Manual enable:** You or another tool enabled it previously
3. **System preference:** Accessibility was turned on in GNOME Settings

---

## Verifying Accessibility is Enabled

### Method 1: gsettings (command line)
```bash
gsettings get org.gnome.desktop.interface toolkit-accessibility
```

**Expected:** `true`

### Method 2: GNOME Settings (GUI)
1. Open **Settings**
2. Navigate to **Accessibility**
3. Check if any features are enabled

If any accessibility feature is on, toolkit-accessibility is usually enabled.

### Method 3: Check with Python
```python
import subprocess
result = subprocess.run(
    ['gsettings', 'get', 'org.gnome.desktop.interface', 'toolkit-accessibility'],
    capture_output=True, text=True
)
print(result.stdout.strip())  # Should be: true
```

---

## Enabling Accessibility (If Needed)

### Automatic (Our Scripts Do This)

The updated `dialog_handler.py` **automatically checks and enables** accessibility:

```python
def _ensure_accessibility_enabled(self):
    """Check and enable if needed"""
    result = subprocess.run(['gsettings', 'get', ...])
    if result.stdout.strip() != 'true':
        subprocess.run(['gsettings', 'set', 'toolkit-accessibility', 'true'])
        print("✅ Accessibility enabled")
```

When you run:
```bash
./dialog_handler.py
# or
./voice-driven-orchestrator-mcp-safe.py
```

The script will:
1. Check if accessibility is enabled
2. Enable it automatically if not
3. Warn you if apps need restart

---

### Manual Enable

If you want to enable it manually:

```bash
gsettings set org.gnome.desktop.interface toolkit-accessibility true
```

**That's it!** No restart needed for new apps, but running apps may need to be relaunched.

---

## Do I Need to Restart?

### ✅ No Restart Needed For:
- **System**: Setting takes effect immediately
- **New apps**: Will launch with a11y support
- **GNOME Shell**: No restart needed

### ⚠️ Restart Recommended For:
- **Running apps**: Apps that were open BEFORE enabling a11y
  - They may not expose accessibility tree until restarted
  - Example: Text editor opened before a11y was on

### 🔄 When to Log Out/In:
- **Full a11y support**: For maximum compatibility
- **Troubleshooting**: If dogtail can't see some apps
- **Not required**: Most apps work immediately

---

## Testing Accessibility

### Test 1: List Running Apps (Dogtail)

```bash
python3 -c "
from dogtail.tree import root
print('Accessible applications:')
for app in root.applications():
    print(f'  - {app.name}')
"
```

**Expected output:**
```
Accessible applications:
  - org.gnome.Shell
  - org.gnome.TextEditor
  - org.gnome.Nautilus
  - firefox
  ...
```

If you see apps listed → ✅ Accessibility working!

### Test 2: Inspect Text Editor

```bash
# Open text editor first
gnome-text-editor &

# Then inspect it
python3 -c "
from dogtail.tree import root
app = root.application('org.gnome.TextEditor')
print(f'Found: {app.name}')
for child in app.children[:5]:
    print(f'  {child.roleName}: {child.name}')
"
```

**Expected output:**
```
Found: Text Editor
  frame: Text Editor
  menu bar: 
  push button: Menu
  ...
```

### Test 3: Find a Dialog

```bash
# 1. Open text editor, type text, try to close (DON'T click dialog yet)
gnome-text-editor &
# (type something, then Ctrl+Q)

# 2. Run test script
./dialog_handler.py
```

Should detect the save dialog and list buttons.

---

## Troubleshooting

### Problem: "No applications found"

**Cause:** Accessibility not enabled or apps started before it was enabled.

**Solution:**
```bash
# 1. Verify it's enabled
gsettings get org.gnome.desktop.interface toolkit-accessibility

# 2. If false, enable it
gsettings set org.gnome.desktop.interface toolkit-accessibility true

# 3. Restart the app you're trying to inspect
killall gnome-text-editor
gnome-text-editor &
```

### Problem: "Some apps visible, some not"

**Cause:** Not all apps support accessibility.

**Apps with good a11y support:**
- ✅ Most GNOME apps (GTK4, GTK3)
- ✅ LibreOffice
- ✅ Firefox (with `accessibility.force_disabled = false` in about:config)

**Apps with poor/no a11y support:**
- ❌ Some Electron apps
- ❌ Some Qt apps (unless built with accessibility)
- ❌ Chrome/Chromium (by default)

**Solution:**
Focus on GNOME native apps for dialog handling. For non-accessible apps, fall back to keyboard shortcuts (Escape, Alt+F4).

### Problem: Dialog detected but buttons not found

**Cause:** App uses custom non-standard dialogs.

**Debug:**
```python
from dogtail.tree import root
app = root.application('YourApp')

def print_tree(element, indent=0):
    try:
        print("  " * indent + f"{element.roleName}: {element.name}")
        for child in element.children:
            print_tree(child, indent + 1)
    except:
        pass

print_tree(app)
```

Look for the dialog and button elements. They may have different roleNames than expected.

### Problem: Performance is slow

**Cause:** Accessibility tree can be expensive to traverse on complex apps.

**Solution:**
- Filter by app name (we already do this)
- Use shorter timeouts
- Cache dialog references when possible

---

## Performance Impact

**Q: Does enabling accessibility slow down my system?**

**A:** Minimal impact.

- **At-rest:** Nearly zero overhead
- **When tools query:** Small CPU/memory increase during tree traversal
- **For normal use:** Not noticeable

The accessibility tree is only built/exposed when tools like dogtail request it.

---

## Security Considerations

**Q: Is it safe to enable accessibility?**

**A:** Yes, but be aware:

- **Accessibility APIs** can read screen content
- **Assistive tools** (like dogtail) have broad UI access
- **Only run trusted scripts** that use dogtail

In our case:
- Scripts only read dialog content when YOU trigger close
- No data sent externally
- All local processing
- Open source code you can review

---

## Comparison: gnome-desktop-mcp vs dogtail

| Feature | gnome-desktop-mcp | dogtail |
|---------|-------------------|---------|
| **Method** | D-Bus API calls | Accessibility tree |
| **Requires** | GNOME Shell extension | Accessibility enabled |
| **Can do** | Window management, input, screenshots | UI inspection, element interaction |
| **Dialog handling** | ❌ Cannot detect dialogs | ✅ Can detect and read dialogs |
| **Performance** | Fast | Moderate (tree traversal) |
| **App support** | All windows (via WM) | Only a11y-enabled apps |

**Why we use both:**
- **MCP** for window operations (fast, universal)
- **dogtail** for dialog detection (detailed, interactive)

Best of both worlds! 🎯

---

## Summary

✅ **Accessibility is already enabled on your system**  
✅ **Our scripts auto-enable if needed**  
✅ **gnome-desktop-mcp does NOT enable it** (you enabled it or Fedora did)  
✅ **No restart needed** (but recommended for running apps)  
✅ **Minimal performance impact**  
✅ **Required for safe dialog handling**  

**Bottom line:** Everything is set up correctly! The dialog handler will work as expected. 🎉

---

## Quick Reference

```bash
# Check status
gsettings get org.gnome.desktop.interface toolkit-accessibility

# Enable manually
gsettings set org.gnome.desktop.interface toolkit-accessibility true

# Test dogtail
python3 -c "from dogtail.tree import root; print([app.name for app in root.applications()])"

# Our scripts auto-enable
./dialog_handler.py  # Checks and enables if needed
```

---

**Note:** If you ever need to disable accessibility (not recommended while using dialog handler):

```bash
gsettings set org.gnome.desktop.interface toolkit-accessibility false
```

But keep it enabled for the dialog handling feature to work! 🛡️
