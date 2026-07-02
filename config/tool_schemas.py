TOOL_SCHEMAS = [
    # 1. SEARCH (direct MCP)
    {
        "type": "function",
        "function": {
            "name": "gnome_search",
            "description": "Find and open apps, files, settings, or websites. For WEBSITES (domains/URLs): append ' website' to query (e.g., 'amazon.com website', 'github.com website'). For FILES (documents, images, etc.): append ' file' to query (e.g., 'Screenshot-1.png file', 'document.pdf file'). For APPS and SETTINGS: use query as-is (e.g., 'firefox', 'text editor', 'wifi settings'). The markers (' website' or ' file') tell the system how to handle the query.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "App name, file name+' file', setting, or domain+' website'. Examples: 'firefox', 'text editor', 'Screenshot-1.png file', 'document.pdf file', 'amazon.com website', 'github.com website', 'wifi'",
                    }
                },
                "required": ["query"],
            },
        },
    },
    # 2. SEARCH_FILES (direct MCP)
    {
        "type": "function",
        "function": {
            "name": "search_files",
            "description": "Search for files by name using GNOME file indexing. Returns a JSON list of full absolute file paths matching the query. Use this to find a file's exact path before acting on it (e.g., before describing an image). Does NOT open files.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Filename or keywords to search for. Example: 'screenshot.png', 'report'",
                    }
                },
                "required": ["query"],
            },
        },
    },
    # 3. WINDOW_CONTROL (facade)
    {
        "type": "function",
        "function": {
            "name": "window_control",
            "description": "Unified window management: list windows, focus/close/minimize/maximize/restore windows, take window screenshots or area screenshots, move and resize windows. Matches windows by application name (e.g., 'text editor', 'firefox', 'nautilus'). Empty window_name = current window. For move_resize: left half of 1920x1080 screen = x:0, y:0, width:960, height:1080. Right half = x:960, y:0, width:960, height:1080.",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "description": "Action to perform: list | focus | close | minimize | maximize | restore | screenshot | screenshot_area | move_resize",
                    },
                    "window_name": {
                        "type": "string",
                        "description": "Application name (e.g., 'text editor'). Leave empty for current window.",
                        "default": "",
                    },
                    "x": {
                        "type": "integer",
                        "description": "X position in pixels for move_resize or screenshot_area. Must be integer, NOT percentage.",
                        "default": 0,
                    },
                    "y": {
                        "type": "integer",
                        "description": "Y position in pixels for move_resize or screenshot_area. Must be integer, NOT percentage.",
                        "default": 0,
                    },
                    "width": {
                        "type": "integer",
                        "description": "Width in pixels for move_resize or screenshot_area. Must be integer, NOT percentage. For left/right half: use 960 pixels on 1920 wide screen.",
                        "default": 800,
                    },
                    "height": {
                        "type": "integer",
                        "description": "Height in pixels for move_resize or screenshot_area. Must be integer, NOT percentage. For full height: use 1080 pixels on 1080 tall screen.",
                        "default": 600,
                    },
                    "include_frame": {
                        "type": "boolean",
                        "description": "Include window borders in screenshot",
                        "default": True,
                    },
                },
                "required": ["action"],
            },
        },
    },
    # 4. INPUT_CONTROL (facade)
    {
        "type": "function",
        "function": {
            "name": "input_control",
            "description": "Unified input control: type text, press key combos, press single keys, mouse click/double-click, drag and drop, scroll. Use get_app_shortcuts to look up the correct shortcut before pressing keys.",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "description": "Action: type | key_combo | key_press | click | double_click | drag | scroll",
                    },
                    "text": {
                        "type": "string",
                        "description": "Text to type (for 'type' action)",
                        "default": "",
                    },
                    "keys": {
                        "type": "string",
                        "description": "Key combo like 'Ctrl+c' or single key like 'Enter'",
                        "default": "",
                    },
                    "x": {
                        "type": "integer",
                        "description": "X coordinate for click or drag start",
                        "default": 0,
                    },
                    "y": {
                        "type": "integer",
                        "description": "Y coordinate for click or drag start",
                        "default": 0,
                    },
                    "to_x": {
                        "type": "integer",
                        "description": "Drag end X coordinate",
                        "default": 0,
                    },
                    "to_y": {
                        "type": "integer",
                        "description": "Drag end Y coordinate",
                        "default": 0,
                    },
                    "from_position": {
                        "type": "string",
                        "description": "Natural language start position for drag: 'left', 'right', 'center', 'top left', etc.",
                        "default": "center",
                    },
                    "to_position": {
                        "type": "string",
                        "description": "Natural language end position for drag: 'left', 'right', 'center', 'bottom right', etc.",
                        "default": "center",
                    },
                    "direction": {
                        "type": "string",
                        "description": "Scroll direction: 'up' or 'down'",
                        "default": "down",
                    },
                    "amount": {
                        "type": "integer",
                        "description": "Scroll amount (number of times)",
                        "default": 1,
                    },
                    "button": {
                        "type": "integer",
                        "description": "Mouse button: 1=left, 2=middle, 3=right",
                        "default": 1,
                    },
                },
                "required": ["action"],
            },
        },
    },
    # 5. GET_APP_SHORTCUTS (standalone)
    {
        "type": "function",
        "function": {
            "name": "get_app_shortcuts",
            "description": "Look up keyboard shortcuts for a specific application. Call this before using input_control key_combo/key_press to find the correct shortcut for an action. Returns a list of available shortcuts.",
            "parameters": {
                "type": "object",
                "properties": {
                    "app_name": {
                        "type": "string",
                        "description": "Application name (e.g., 'firefox', 'text editor', 'nautilus', 'terminal', 'gnome' for desktop-wide shortcuts)",
                    }
                },
                "required": ["app_name"],
            },
        },
    },
    # 6. AUDIO_CONTROL (facade)
    {
        "type": "function",
        "function": {
            "name": "audio_control",
            "description": "Unified audio control: volume (set/increase/decrease), mute, unmute, media playback (play, pause, play_pause toggle, next, previous, stop). Handles all sound and media controls.",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "description": "Action: volume | mute | unmute | play | pause | play_pause | next | previous | stop",
                    },
                    "level": {
                        "type": "integer",
                        "description": "Volume level: 0-100 absolute, or +/- for relative change",
                        "default": 0,
                    },
                    "relative": {
                        "type": "boolean",
                        "description": "True for relative volume change (+/-), false for absolute",
                        "default": False,
                    },
                },
                "required": ["action"],
            },
        },
    },
    # 7. SYSTEM_SETTINGS (facade)
    {
        "type": "function",
        "function": {
            "name": "system_settings",
            "description": "Unified system settings: toggle dark mode, night light, do not disturb, WiFi, Bluetooth, set wallpaper. Handles all quick settings and appearance controls. For wallpaper: can use color names (red, blue, green), wallpaper names (fedora, adwaita), or file paths.",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "description": "Setting: dark_mode | night_light | do_not_disturb | wifi | bluetooth | wallpaper",
                    },
                    "state": {
                        "type": "string",
                        "description": "For toggles: 'on' or 'off'. For wallpaper: color name (red, blue), wallpaper name (fedora), or path",
                        "default": "toggle",
                    },
                    "path": {
                        "type": "string",
                        "description": "Image path for wallpaper action (alternative to state parameter)",
                        "default": "",
                    },
                },
                "required": ["action"],
            },
        },
    },
    # 8. VISION_CONTROL (facade)
    {
        "type": "function",
        "function": {
            "name": "vision_control",
            "description": "Unified vision operations: take full desktop screenshot, describe what's on screen using AI vision, describe the focused application window content, describe/analyze an image file by path, pick RGB color at screen coordinates, get monitor information (position, resolution, scaling). Handles all screen analysis and display queries. For 'describe this image/file/picture' when an image viewer is focused, use describe_window. For pick_color: user says 'at 100, 100' or 'at 100-100' or 'at coordinates 100 and 100' means x=100, y=100. For describe_file: use search_files FIRST to get the exact path, then call describe_file with the full path from the search result.",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "description": "Action: screenshot (full desktop) | describe (AI vision of current screen) | describe_window (AI vision of focused app window, use for 'describe this image/file') | describe_file (analyze image at path) | pick_color | get_monitors",
                    },
                    "x": {
                        "type": "integer",
                        "description": "X coordinate in pixels for pick_color action. User says '100, 100' or '100-100' means x=100. Must be positive integer >= 1.",
                        "default": 0,
                    },
                    "y": {
                        "type": "integer",
                        "description": "Y coordinate in pixels for pick_color action. User says '100, 100' or '100-100' or 'at 100 and 100' means y=100. Must be positive integer >= 1.",
                        "default": 0,
                    },
                    "path": {
                        "type": "string",
                        "description": "File path for describe_file action. Supports ~ for home directory. Example: '~/Pictures/screenshot.png'",
                        "default": "",
                    },
                },
                "required": ["action"],
            },
        },
    },
    # 9. WORKSPACE_CONTROL (facade)
    {
        "type": "function",
        "function": {
            "name": "workspace_control",
            "description": "Unified workspace management: list all virtual desktops, switch to specific workspace by index (0-based). Users say workspace numbers starting from 1, but the index parameter is 0-based, so subtract 1: 'workspace 1' = index 0, 'workspace 2' = index 1, 'workspace 3' = index 2.",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {"type": "string", "description": "Action: list | activate"},
                    "index": {
                        "type": "integer",
                        "description": "Workspace index (0-based). Subtract 1 from the user's number: 'workspace 1' = index 0, 'workspace 2' = index 1.",
                        "default": 0,
                    },
                },
                "required": ["action"],
            },
        },
    },
    # 10. LIST_INSTALLED_APPLICATIONS (standalone)
    {
        "type": "function",
        "function": {
            "name": "list_installed_applications",
            "description": "Lists all installed GUI applications available on the Linux system. Use for 'what apps are installed', 'list all applications', 'show me installed programs'.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    # 11. SEND_NOTIFICATION (standalone)
    {
        "type": "function",
        "function": {
            "name": "send_notification",
            "description": "Send a desktop notification immediately or after a delay. Use for reminders, timers, alerts. Examples: 'remind me in 5 minutes', 'notify in 1 hour', 'send notification' (immediate).",
            "parameters": {
                "type": "object",
                "properties": {
                    "summary": {
                        "type": "string",
                        "description": "Notification title/headline (required)",
                    },
                    "body": {
                        "type": "string",
                        "description": "Notification message body (optional)",
                        "default": "",
                    },
                    "delay": {
                        "type": "string",
                        "description": "Time delay: '5 minutes', '1 hour', '30 seconds'. Empty = immediate.",
                        "default": "",
                    },
                },
                "required": ["summary"],
            },
        },
    },
    # 12. CLEANUP_SCREENSHOTS (standalone)
    {
        "type": "function",
        "function": {
            "name": "cleanup_screenshots",
            "description": "Remove all temporary screenshot files to free disk space. Use for maintenance, cleanup tasks.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    # 13. GET_DATETIME (standalone)
    {
        "type": "function",
        "function": {
            "name": "get_datetime",
            "description": "Get the current date, time, and day of week. Use for 'what time is it', 'what's the date', 'what day is it'.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
]
