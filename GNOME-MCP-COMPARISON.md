# GNOME MCP Servers Comparison

You have two different MCP servers available for GNOME desktop automation:

## 1. gnome-desktop-mcp (Node.js) ✅ Currently Installed

**Language:** JavaScript/TypeScript (npm package)  
**Installation:** `npm install -g gnome-desktop-mcp`  
**Status:** ✅ Installed and working in orchestrator

### Tools (30 total)

#### Screenshots (4)
- `screenshot` - Full screen capture
- `screenshot_window` - Capture specific window
- `screenshot_area` - Capture rectangular region
- `pick_color` - Get pixel color at coordinates

#### Window Management (9)
- `list_windows` - List all windows
- `get_window` - Get window details
- `focus_window` - Focus and raise window
- `move_resize_window` - Move and resize
- `minimize_window` - Minimize
- `unminimize_window` - Restore minimized
- `maximize_window` - Maximize
- `unmaximize_window` - Restore maximized
- `close_window` - Close window

#### Workspace (2)
- `list_workspaces` - List all workspaces
- `activate_workspace` - Switch workspace

#### Keyboard (3)
- `key_press` - Press single key
- `key_combo` - Press key combination
- `type_text` - Type text

#### Mouse (7)
- `mouse_move` - Move cursor
- `mouse_click` - Click
- `mouse_double_click` - Double-click
- `mouse_down` - Press button
- `mouse_up` - Release button
- `mouse_drag` - Drag
- `mouse_scroll` - Scroll

#### System (5)
- `get_monitors` - Monitor info
- `ping` - Health check
- `get_enabled` - Check automation status
- `set_enabled` - Enable/disable automation
- `cleanup_screenshots` - Clean temp files

**Focus:** Low-level desktop automation, window control, mouse/keyboard simulation

---

## 2. gnome-mcp-server (Rust) 📦 Available but Not Built

**Language:** Rust  
**Installation:** `cargo install --path ~/gnome-mcp-server`  
**Status:** ⚠️ Source available, needs building

### Tools (9 total)

#### Notifications
- `send_notification` - Send desktop notification
  - `summary` (required) - Title
  - `body` (required) - Content

#### Applications
- `launch_application` - Launch app
  - `app_name` (required) - App name or executable
- `open_file` - Open file or URL
  - `path` (required) - File path or URL

#### Desktop Customization
- `set_wallpaper` - Change wallpaper
  - `image_path` (required) - Full path to JPG/PNG

#### Audio Control
- `set_volume` - Control system volume
  - `volume` (optional) - 0-100
  - `mute` (optional) - true/false
  - `relative` (optional) - Relative change
  - `direction` (optional) - "up"/"down"
  
- `media_control` - Control media playback
  - `action` (required) - play, pause, play_pause, stop, next, previous
  - `player` (optional) - Specific player name

#### Quick Settings
- `quick_settings` - Toggle GNOME quick settings
  - `setting` (required) - wifi, bluetooth, night_light, do_not_disturb, dark_style
  - `enabled` (required) - true/false

#### Screenshots
- `take_screenshot` - Screenshot with optional UI
  - `interactive` (optional) - Show selection dialog

#### Window Management
- `window_management` - Comprehensive window control
  - `action` (required) - list, focus, close, minimize, maximize, switch_workspace, move_to_workspace, get_geometry, set_geometry, set_position, set_size, snap
  - Various optional params depending on action
  - **Requires:** GNOME Shell unsafe mode

#### Security
- `keyring` - Secure password storage
  - `action` (required) - store, retrieve, delete
  - `label` (optional) - Human-readable name
  - `secret` (optional) - The secret value
  - `attributes` (optional) - JSON search attributes

### Resources (7 total)

Resources are read-only data sources:

#### Personal Information
- `calendar` - Calendar events
  - Configurable: days ahead/behind
  
- `tasks` - Task list
  - Configurable: completed, cancelled, due date filter
  
- `contacts` - Contact list
  - Configurable: email-only filter

#### System Information
- `applications` - Installed applications list
- `audio` - Audio devices and state
- `system_info` - System information

**Focus:** High-level GNOME integration, PIM data, system settings, security

---

## Comparison Table

| Feature | gnome-desktop-mcp | gnome-mcp-server |
|---------|------------------|------------------|
| **Language** | JavaScript | Rust |
| **Status** | ✅ Installed | ⚠️ Needs building |
| **Screenshots** | ✅ Advanced (full, window, area, color) | ✅ Basic (interactive) |
| **Window Management** | ✅ Detailed (9 tools) | ✅ Unified (1 tool, many actions) |
| **Mouse Control** | ✅ Yes (7 tools) | ❌ No |
| **Keyboard Control** | ✅ Yes (3 tools) | ❌ No |
| **Workspaces** | ✅ List & switch | ✅ Via window_management |
| **Notifications** | ❌ No | ✅ Yes |
| **Audio Control** | ❌ No | ✅ Yes (volume + media) |
| **Quick Settings** | ❌ No | ✅ Yes (wifi, BT, night light, etc.) |
| **Wallpaper** | ❌ No | ✅ Yes |
| **Calendar Access** | ❌ No | ✅ Yes (resource) |
| **Tasks Access** | ❌ No | ✅ Yes (resource) |
| **Contacts Access** | ❌ No | ✅ Yes (resource) |
| **Keyring/Secrets** | ❌ No | ✅ Yes |
| **System Info** | ✅ Monitor info | ✅ Full system info (resource) |
| **File Operations** | ❌ No | ✅ Open files/URLs |

---

## Use Cases

### Use gnome-desktop-mcp for:
- ✅ GUI automation (click, drag, type)
- ✅ Window positioning and management
- ✅ Screenshot analysis (vision AI workflows)
- ✅ Mouse-based interactions
- ✅ Low-level desktop control

**Current orchestrator uses:** screenshot, list_windows, focus_window, close_window, key_combo, type_text

### Use gnome-mcp-server for:
- ✅ Notifications ("Remind me...")
- ✅ Audio control ("Turn up volume", "Pause music")
- ✅ Calendar integration ("What's on my calendar?")
- ✅ Task management ("What tasks are due today?")
- ✅ Contact lookup ("Find John's email")
- ✅ Quick settings ("Enable dark mode", "Turn on wifi")
- ✅ Wallpaper changes
- ✅ Secure password storage
- ✅ High-level GNOME features

---

## Recommendation: Use Both!

They complement each other:

**gnome-desktop-mcp (low-level):**
- Window automation
- Mouse/keyboard simulation
- Vision + screenshot workflows

**gnome-mcp-server (high-level):**
- PIM integration (calendar, tasks, contacts)
- System settings (audio, wifi, dark mode)
- Notifications
- Secure secrets

### Installation

```bash
# gnome-desktop-mcp (already installed)
npm install -g gnome-desktop-mcp

# gnome-mcp-server (build from source)
cd ~/gnome-mcp-server
cargo install --path .

# Binary will be at: ~/.cargo/bin/gnome-mcp-server
```

### Orchestrator Integration

You could run **two MCP connections**:

```python
# Desktop automation
desktop_mcp = MCPClient("gnome-desktop-mcp", [])

# GNOME features
gnome_mcp = MCPClient("gnome-mcp-server", [])
```

Then route commands based on type:
- Window/mouse/keyboard → desktop_mcp
- Notifications/audio/calendar → gnome_mcp

---

## Building gnome-mcp-server

```bash
cd ~/gnome-mcp-server
cargo install --path .

# Add to PATH if needed
echo 'export PATH="$HOME/.cargo/bin:$PATH"' >> ~/.bashrc
source ~/.bashrc

# Verify
gnome-mcp-server --version
```

### Enable Window Management Features

For window_management tool to work:
1. Press `Alt+F2`
2. Type: `lg`
3. In console: `global.context.unsafe_mode = true`

---

## Configuration

Create `~/.config/gnome-mcp/config.json` to customize:

```json
{
  "calendar": {
    "days_ahead": 30,
    "days_behind": 0
  },
  "tasks": {
    "include_completed": true,
    "include_cancelled": false,
    "due_within_days": 0
  },
  "contacts": {
    "email_only": false
  },
  "audio": {
    "volume_step": 10
  },
  "screenshot": {
    "interactive": false
  }
}
```

Omit sections to disable features.

---

## Summary

- **gnome-desktop-mcp**: Low-level automation (windows, mouse, keyboard) ✅ Working
- **gnome-mcp-server**: High-level GNOME features (PIM, audio, settings) ⚠️ Available, needs build

Both are valuable and serve different purposes. The orchestrator could be enhanced significantly by using both!
