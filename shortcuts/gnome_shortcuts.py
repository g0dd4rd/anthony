import re
import subprocess

GSETTINGS_SCHEMAS = {
    "gnome-wm": "org.gnome.desktop.wm.keybindings",
    "gnome-shell": "org.gnome.shell.keybindings",
    "gnome-media": "org.gnome.settings-daemon.plugins.media-keys",
    "gnome-mutter": "org.gnome.mutter.keybindings",
    "ptyxis": "org.gnome.Ptyxis.Shortcuts",
}

SCHEMA_ALIASES = {
    "gnome": ["gnome-wm", "gnome-shell"],
    "desktop": ["gnome-wm", "gnome-shell"],
    "terminal": ["ptyxis"],
    "media": ["gnome-media"],
}


def _normalize_shortcut(raw: str) -> str:
    """Convert gsettings format like '<ctrl><shift>w' or '<Alt>F4' to 'Ctrl+Shift+W'."""
    raw = raw.strip().strip("'\"")
    if not raw or raw == "@as []":
        return ""

    if raw.startswith("[") and raw.endswith("]"):
        raw = raw[1:-1].strip().strip("'\"")
    if not raw:
        return ""

    parts = re.findall(r"<([^>]+)>", raw)
    key = re.sub(r"<[^>]+>", "", raw).strip()

    modifiers = []
    for p in parts:
        p_lower = p.lower()
        if p_lower in ("ctrl", "control", "primary"):
            modifiers.append("Ctrl")
        elif p_lower in ("alt", "mod1"):
            modifiers.append("Alt")
        elif p_lower in ("shift",):
            modifiers.append("Shift")
        elif p_lower in ("super", "mod4"):
            modifiers.append("Super")
        else:
            modifiers.append(p.capitalize())

    if key:
        modifiers.append(key.capitalize() if len(key) == 1 else key)

    return "+".join(modifiers)


def _action_label(key_name: str) -> str:
    """Convert gsettings key name like 'close-tab' to 'Close tab'."""
    return key_name.replace("-", " ").replace("_", " ").capitalize()


def get_gsettings_shortcuts(schema_key: str) -> dict:
    """Extract shortcuts from a gsettings schema. Returns {action_label: shortcut_string}."""
    schema = GSETTINGS_SCHEMAS.get(schema_key)
    if not schema:
        return {}

    try:
        result = subprocess.run(
            ["gsettings", "list-recursively", schema], capture_output=True, text=True, timeout=5
        )
        if result.returncode != 0:
            return {}
    except Exception:
        return {}

    shortcuts = {}
    for line in result.stdout.strip().split("\n"):
        if not line:
            continue
        parts = line.split(None, 2)
        if len(parts) < 3:
            continue
        key_name = parts[1]
        raw_value = parts[2]

        shortcut = _normalize_shortcut(raw_value)
        if shortcut:
            shortcuts[_action_label(key_name)] = shortcut

    return shortcuts


def get_shortcuts_for_app(app_name: str) -> dict:
    """Get gsettings shortcuts for an app name. Returns empty dict if no schema found."""
    app_lower = app_name.lower().strip()

    if app_lower in SCHEMA_ALIASES:
        merged = {}
        for key in SCHEMA_ALIASES[app_lower]:
            merged.update(get_gsettings_shortcuts(key))
        return merged

    if app_lower in GSETTINGS_SCHEMAS:
        return get_gsettings_shortcuts(app_lower)

    for key in GSETTINGS_SCHEMAS:
        if app_lower in key:
            return get_gsettings_shortcuts(key)

    return {}
