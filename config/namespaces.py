NAMESPACES = {
    "search": {
        "description": "Opening and launching: applications (firefox, text editor, calculator, terminal), files and documents (image.png, document.pdf, report.txt, presentation.pptx), websites (amazon.com, github.com), system settings (wifi, bluetooth). Use for any 'open', 'launch', 'start', 'find' command. Examples: open firefox, open report.pdf, open image.png, launch calculator, go to amazon.com, find settings.",
        "tools": ["gnome_search"],
    },
    "window": {
        "description": "Managing already running application windows: close, minimize, maximize, restore, focus, move, resize windows. List currently running windows. Capture window images or screen regions. NOT for launching/opening new apps or files.",
        "tools": ["window_control"],
    },
    "input": {
        "description": "Keyboard input, typing text, pressing keys, key combinations, shortcuts, mouse clicks, double clicks, dragging, scrolling pages up and down. Look up app-specific keyboard shortcuts before performing in-app actions.",
        "tools": ["input_control", "get_app_shortcuts"],
    },
    "audio": {
        "description": "Sound volume control, mute, unmute, audio levels. Media playback control - play, pause, stop, next track, previous track, music control, audio player control",
        "tools": ["audio_control"],
    },
    "settings": {
        "description": "System settings - dark mode, light mode, night light, notifications, do not disturb, WiFi, Bluetooth, wallpaper, background image, quick settings toggles",
        "tools": ["system_settings"],
    },
    "vision": {
        "description": "Screen analysis and display tools: capture full desktop image, describe current screen content with AI, describe or analyze an image file by path (e.g., describe screenshot.png, what's in this picture), pick pixel colors at coordinates, get monitor information (resolution, scaling, position)",
        "tools": ["vision_control", "search_files"],
    },
    "workspace": {
        "description": "Virtual desktops, workspace switching (switch to workspace 1, go to workspace 2, activate workspace), multi-desktop management, listing workspaces",
        "tools": ["workspace_control"],
    },
    "system": {
        "description": "System tasks: list installed applications (show apps, what apps are installed), send desktop notifications (notify me, remind me, alert me in X minutes), clean up screenshots (delete screenshots, remove screenshots, cleanup temp files), enable or disable automation, get current date and time (what time is it, what's today's date, what day is it)",
        "tools": [
            "list_installed_applications",
            "send_notification",
            "cleanup_screenshots",
            "set_enabled",
            "get_datetime",
        ],
    },
}
