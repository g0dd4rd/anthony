import json
import os

from commands import step, _mcp_client, _get_friendly_app_name
from commands.input import _send_key_via_mcp, _handle_dialog_after_shortcut
from config.aliases import APP_SHORTCUT_ALIASES
from utils import log_and_print

_shortcuts_dir = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "shortcuts"
)
_json_path = os.path.join(_shortcuts_dir, "app_shortcuts.json")

try:
    with open(_json_path) as _f:
        _shortcuts_data = json.load(_f)
except Exception as _e:
    log_and_print(f"[SHORTCUTS] Failed to load app_shortcuts.json: {_e}",
                  level='error')
    _shortcuts_data = {}


def _get_focused_app_key():
    """Return (json_key, friendly_name) for the currently focused window."""
    try:
        result = _mcp_client.call_tool("list_windows", {})
        if result.startswith("Error"):
            return None, None
        windows = json.loads(result)
        focused = next((w for w in windows if w.get('focused', False)), None)
        if not focused:
            return None, None

        wm_class = focused.get('wmClass', '')
        friendly_name = _get_friendly_app_name(wm_class)

        candidates = [wm_class.lower()]
        for prefix in ('org.gnome.', 'org.mozilla.', 'org.'):
            if wm_class.lower().startswith(prefix):
                candidates.append(wm_class.lower()[len(prefix):])
        for c in list(candidates):
            alias = APP_SHORTCUT_ALIASES.get(c)
            if alias:
                candidates.append(alias)
        friendly_alias = APP_SHORTCUT_ALIASES.get(friendly_name.lower())
        if friendly_alias:
            candidates.append(friendly_alias)

        for candidate in candidates:
            if candidate in _shortcuts_data:
                return candidate, friendly_name

        return None, friendly_name
    except Exception as e:
        log_and_print(f"[SHORTCUTS] Error getting focused app: {e}",
                      level='error')
        return None, None


def _execute_app_action(action_name):
    """Look up the action for the focused app and send the shortcut."""
    app_key, friendly_name = _get_focused_app_key()

    if app_key is None:
        if friendly_name:
            return f"No shortcuts available for {friendly_name}"
        return "No focused window found"

    shortcut = _shortcuts_data.get(app_key, {}).get(action_name)
    if not shortcut:
        return f"{friendly_name} does not have a {action_name.lower()} shortcut"

    log_and_print(f"[SHORTCUTS] {action_name} in {app_key}: {shortcut}")
    _send_key_via_mcp(shortcut)

    dialog_result = _handle_dialog_after_shortcut(shortcut)
    if dialog_result:
        return dialog_result

    return f"{action_name} in {friendly_name}"


# --- Tab management ---

@step('next tab', 'switch to next tab', 'go to next tab',
      category='shortcuts', help_text='Switch to the next tab')
def handle_next_tab(context):
    return _execute_app_action("Next tab")


@step('previous tab', 'previews tab', 'last tab',
      'switch to previous tab', 'go to previous tab',
      category='shortcuts', help_text='Switch to the previous tab')
def handle_previous_tab(context):
    return _execute_app_action("Previous tab")


@step('new tab', 'open a new tab', 'open new tab',
      category='shortcuts', help_text='Open a new tab')
def handle_new_tab(context):
    return _execute_app_action("New tab")


@step('close tab', 'close the tab', 'close this tab',
      category='shortcuts', help_text='Close the current tab')
def handle_close_tab(context):
    return _execute_app_action("Close tab")


# --- Clipboard & editing ---

@step('select all',
      category='shortcuts', help_text='Select all content')
def handle_select_all(context):
    return _execute_app_action("Select all")


@step('copy', 'copy that',
      category='shortcuts', help_text='Copy selection')
def handle_copy(context):
    return _execute_app_action("Copy")


@step('paste', 'paste that',
      category='shortcuts', help_text='Paste clipboard')
def handle_paste(context):
    return _execute_app_action("Paste")


@step('cut', 'cut that',
      category='shortcuts', help_text='Cut selection')
def handle_cut(context):
    return _execute_app_action("Cut")


@step('undo',
      category='shortcuts', help_text='Undo the last action')
def handle_undo(context):
    return _execute_app_action("Undo")


@step('redo',
      category='shortcuts', help_text='Redo the last undone action')
def handle_redo(context):
    return _execute_app_action("Redo")


# --- Search ---

@step('find', 'find in page', 'search in page',
      category='shortcuts', help_text='Open find/search')
def handle_find(context):
    return _execute_app_action("Find")


# --- View ---

@step('zoom in',
      category='shortcuts', help_text='Zoom in')
def handle_zoom_in(context):
    return _execute_app_action("Zoom in")


@step('zoom out',
      category='shortcuts', help_text='Zoom out')
def handle_zoom_out(context):
    return _execute_app_action("Zoom out")


@step('full screen', 'toggle full screen', 'go full screen',
      category='shortcuts', help_text='Toggle full screen')
def handle_full_screen(context):
    return _execute_app_action("Full screen")


@step('new window', 'open a new window', 'open new window',
      category='shortcuts', help_text='Open a new window')
def handle_new_window(context):
    return _execute_app_action("New window")
