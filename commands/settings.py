from commands import _mcp_client, step

_SETTING_MAP = {
    "dark mode": "dark_style",
    "dark style": "dark_style",
    "dark theme": "dark_style",
    "night light": "night_light",
    "night mode": "night_light",
    "do not disturb": "do_not_disturb",
    "dnd": "do_not_disturb",
    "wifi": "wifi",
    "wi-fi": "wifi",
    "bluetooth": "bluetooth",
}


@step(
    "turn on {setting}",
    "enable {setting}",
    "activate {setting}",
    "switch on {setting}",
    category="settings",
    help_text="Enable a system setting (dark mode, wifi, bluetooth, etc.)",
)
def handle_setting_on(context, setting):
    setting_lower = setting.lower().strip()
    mcp_setting = _SETTING_MAP.get(setting_lower)
    if not mcp_setting:
        return f"Unknown setting: {setting}"
    return _mcp_client.call_tool("quick_settings", {"setting": mcp_setting, "enabled": True})


@step(
    "turn off {setting}",
    "disable {setting}",
    "deactivate {setting}",
    "switch off {setting}",
    category="settings",
    help_text="Disable a system setting",
)
def handle_setting_off(context, setting):
    setting_lower = setting.lower().strip()
    mcp_setting = _SETTING_MAP.get(setting_lower)
    if not mcp_setting:
        return f"Unknown setting: {setting}"
    return _mcp_client.call_tool("quick_settings", {"setting": mcp_setting, "enabled": False})


@step(
    "set wallpaper to {value}",
    "set wallpaper {value}",
    "change wallpaper to {value}",
    "change wallpaper {value}",
    category="settings",
    help_text="Set the desktop wallpaper",
)
def handle_wallpaper(context, value):
    return _mcp_client.call_tool("set_wallpaper", {"image_path": value})
