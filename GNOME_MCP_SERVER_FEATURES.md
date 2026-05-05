# GNOME MCP Server (Rust) - Feature List

**Location:** `/home/jprajzne/gnome-mcp-server`  
**Language:** Rust  
**Focus:** GNOME ecosystem integration (Calendar, Contacts, Tasks, Keyring, Quick Settings)

## Tools

### 1. `send_notification`
Send desktop notifications

**Parameters:**
- `summary` (string, required): Notification title
- `body` (string, required): Notification content

**Voice examples:**
- "Send notification: Meeting in 5 minutes"
- "Notify me: Time to take a break"

---

### 2. `launch_application`
Launch applications

**Parameters:**
- `app_name` (string, required): Application name or executable

**Voice examples:**
- "Launch firefox"
- "Open text editor"

**Status:** ✅ Already integrated in orchestrator

---

### 3. `open_file`
Open files or URLs

**Parameters:**
- `path` (string, required): File path or URL

**Voice examples:**
- "Open /home/user/document.pdf"
- "Open https://github.com"

---

### 4. `set_wallpaper`
Change desktop wallpaper

**Parameters:**
- `image_path` (string, required): Full path to image file
- Supported formats: JPG, JPEG, PNG

**Voice examples:**
- "Set wallpaper to /home/user/Pictures/nature.jpg"
- "Change background image"

---

### 5. `set_volume`
Control audio volume

**Parameters:**
- `volume` (number, optional): Volume level 0-100
- `mute` (boolean, optional): Mute/unmute
- `relative` (boolean, optional): Relative change if true
- `direction` (string, optional): "up" or "down" for default step

**Config:**
```json
"audio": {
  "volume_step": 10    // Default step size
}
```

**Voice examples:**
- "Set volume to 50"
- "Volume up"
- "Mute audio"
- "Increase volume by 10"

---

### 6. `media_control`
Control media playback

**Parameters:**
- `action` (string, required): play, pause, play_pause, stop, next, previous
- `player` (string, optional): Specific player name (default: active player)

**Voice examples:**
- "Play music"
- "Pause"
- "Next track"
- "Previous song"
- "Stop playback"

---

### 7. `quick_settings`
Toggle system quick settings

**Parameters:**
- `setting` (string, required): wifi, bluetooth, night_light, do_not_disturb, dark_style
- `enabled` (boolean, required): Enable/disable state

**Voice examples:**
- "Enable WiFi"
- "Turn off bluetooth"
- "Enable dark mode"
- "Turn on night light"
- "Enable do not disturb"

---

### 8. `take_screenshot`
Take screenshots

**Parameters:**
- `interactive` (boolean, optional): Show selection dialog

**Config:**
```json
"screenshot": {
  "interactive": false    // Default interactive mode
}
```

**Voice examples:**
- "Take screenshot"
- "Screenshot with selection"

**Status:** ✅ Already integrated (via gnome-desktop-mcp) with more features

---

### 9. `window_management`
Comprehensive window management

**Parameters:**
- `action` (string, required): list, focus, close, minimize, maximize, switch_workspace, move_to_workspace, get_geometry, set_geometry, set_position, set_size, snap
- `window_id` (string, optional): Window ID for window-specific actions
- `workspace` (integer, optional): Workspace number (0-indexed)
- `x` (integer, optional): X coordinate
- `y` (integer, optional): Y coordinate
- `width` (integer, optional): Width in pixels
- `height` (integer, optional): Height in pixels
- `position` (string, optional): "left" or "right" for snap action

**Requirements:** GNOME Shell unsafe mode: `Alt+F2` → `lg` → `global.context.unsafe_mode = true`

**Voice examples:**
- "List windows"
- "Focus window 123"
- "Snap window to left"
- "Move window to workspace 2"

**Status:** ⚠️ Partially integrated (via gnome-desktop-mcp) - missing snap, geometry operations

---

### 10. `keyring`
Manage secrets in GNOME Keyring

**Parameters:**
- `action` (string, required): store, retrieve, delete
- `label` (string, optional): Human-readable label (required for store)
- `secret` (string, optional): Secret value (required for store)
- `attributes` (string, optional): JSON object for categorizing/searching

**Examples:**
```json
// Store
{"action": "store", "label": "GitHub Token", "secret": "ghp_xxx", "attributes": "{\"service\": \"github\"}"}

// Retrieve
{"action": "retrieve", "attributes": "{\"service\": \"github\"}"}

// Delete
{"action": "delete", "attributes": "{\"user\": \"myuser\"}"}
```

**Voice examples:**
- "Store GitHub token"
- "Retrieve password for Gmail"
- "Delete saved credentials"

---

## Resources

Resources are read-only context that the MCP server exposes to the client.

### 1. `calendar`
Access calendar events

**Config:**
```json
"calendar": {
  "days_ahead": 30,    // Days to look ahead
  "days_behind": 0     // Days to look behind
}
```

**Use cases:**
- "What's on my calendar today?"
- "Do I have any meetings tomorrow?"

---

### 2. `tasks`
Access task lists

**Config:**
```json
"tasks": {
  "include_completed": true,
  "include_cancelled": false,
  "due_within_days": 0
}
```

**Use cases:**
- "What tasks are due today?"
- "Show my pending tasks"

---

### 3. `contacts`
Access contacts

**Config:**
```json
"contacts": {
  "email_only": false
}
```

**Use cases:**
- "Find John's email"
- "Look up contact information"

---

### 4. `applications`
List of installed applications

**Use cases:**
- "What apps are installed?"
- "Is Firefox installed?"

---

### 5. `audio`
Current audio status

**Use cases:**
- "What's the current volume?"
- "Is audio muted?"

---

### 6. `system_info`
System information

**Use cases:**
- "What's my system info?"
- "Show OS version"

---

## Integration Status

| Feature | Available in gnome-mcp-server | Integrated in Orchestrator | Priority for Integration |
|---------|-------------------------------|---------------------------|--------------------------|
| **Notifications** | ✅ `send_notification` | ❌ | 🔥 HIGH - Very useful for voice |
| **Launch app** | ✅ `launch_application` | ✅ | ✅ Done |
| **Open file/URL** | ✅ `open_file` | ❌ | 🔥 HIGH - Useful for voice |
| **Wallpaper** | ✅ `set_wallpaper` | ❌ | 🟡 MEDIUM - Nice to have |
| **Volume control** | ✅ `set_volume` | ❌ | 🔥 HIGH - Very useful for voice |
| **Media control** | ✅ `media_control` | ❌ | 🔥 HIGH - Very useful for voice |
| **Quick settings** | ✅ `quick_settings` | ❌ | 🔥 HIGH - WiFi, Bluetooth, Dark mode |
| **Screenshots** | ✅ `take_screenshot` | ✅ (better impl) | ✅ Done (via gnome-desktop-mcp) |
| **Window mgmt** | ✅ `window_management` | ⚠️ Partial | 🟡 MEDIUM - Add snap/geometry |
| **Keyring** | ✅ `keyring` | ❌ | 🟢 LOW - Security sensitive |
| **Calendar** | ✅ Resource | ❌ | 🟡 MEDIUM - Context for AI |
| **Tasks** | ✅ Resource | ❌ | 🟡 MEDIUM - Context for AI |
| **Contacts** | ✅ Resource | ❌ | 🟢 LOW - Privacy sensitive |

## Key Differences vs gnome-desktop-mcp

| Feature | gnome-desktop-mcp (GJS) | gnome-mcp-server (Rust) |
|---------|-------------------------|-------------------------|
| **Mouse/Keyboard** | Full input simulation | Not available |
| **Window control** | Detailed control via extension | Basic via GNOME Shell |
| **Screenshots** | Multiple modes, areas | Basic screenshot |
| **GNOME Integration** | Limited | Full (Calendar, Tasks, Contacts, Keyring) |
| **System Control** | Limited | Full (Volume, Media, Quick Settings) |
| **Notifications** | Not available | Full support |
| **File operations** | Not available | Open files/URLs |

## Recommendation

**Use both MCP servers together:**
1. **gnome-desktop-mcp** - Desktop automation (mouse, keyboard, detailed window control)
2. **gnome-mcp-server** - GNOME ecosystem (notifications, volume, media, calendar, quick settings)

The orchestrator can connect to both and expose all features via voice!
