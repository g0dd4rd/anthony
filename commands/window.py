import json
import time

import app_index
from commands import (
    _dialog_handler,
    _get_friendly_app_name,
    _listen,
    _mcp_client,
    _smart_match_window,
    _speak,
    step,
)
from config.aliases import APP_A11Y_NAMES
from utils import log_and_print

DIALOG_CHECK_SHORTCUTS = {"Alt+F4", "Ctrl+Q", "Ctrl+W", "Ctrl+Shift+W"}


def _resolve_atspi_name(wm_class):
    """Resolve wmClass to AT-SPI app name via app_name_map + APP_A11Y_NAMES."""
    if not wm_class:
        return None
    exec_name = app_index.app_name_map.get(wm_class.lower())
    if not exec_name:
        stripped = wm_class.replace("org.gnome.", "").replace("org.", "")
        exec_name = app_index.app_name_map.get(stripped.lower())
    if exec_name:
        return APP_A11Y_NAMES.get(exec_name)
    return APP_A11Y_NAMES.get(wm_class.lower())


def _send_key_via_mcp(keys):
    if "+" in keys:
        _mcp_client.call_tool("key_combo", {"keys": keys})
    else:
        _mcp_client.call_tool("key_press", {"key": keys})


def _list_windows():
    result = _mcp_client.call_tool("list_windows", {})
    if result.startswith("Error"):
        return result
    return json.loads(result)


def _find_window(app_name):
    windows = _list_windows()
    if isinstance(windows, str):
        return None, windows
    if not windows:
        return None, None
    target = _smart_match_window(app_name, windows)
    return target, windows


def _check_find_result(target, windows_or_error, app_name):
    if isinstance(windows_or_error, str):
        return windows_or_error
    if not target:
        return f"No window found matching '{app_name}'"
    return None


def _verify_window_state(window_id, expected):
    try:
        windows = _list_windows()
        if not windows:
            return None, None
        window = next((w for w in windows if w["id"] == window_id), None)
        if window is None:
            return False, None
        for key, value in expected.items():
            if window.get(key) != value:
                return False, window
        return True, window
    except Exception:
        return None, None


def _handle_save_dialog(window_id=None, atspi_name=None):
    dialog = _dialog_handler.detect_save_dialog(app_name=atspi_name, timeout=3.0)
    if not dialog:
        time.sleep(0.5)
        if window_id:
            windows = _list_windows()
            if windows is not None and not any(w["id"] == window_id for w in windows):
                return None
        dialog = _dialog_handler.detect_save_dialog(app_name=atspi_name, timeout=5.0)
        if not dialog:
            return None

    buttons = dialog["info"]["buttons"]
    button_list = (
        ", ".join([btn["text"] for btn in buttons]) if buttons else "Save, Discard, Cancel"
    )
    _speak(f"The window has unsaved changes. Options: {button_list}. What would you like to do?")
    user_choice = _listen()

    if not user_choice:
        _speak("No response heard. Canceling close operation.")
        _mcp_client.call_tool("key_combo", {"keys": "Escape"})
        return "canceled"

    success = _dialog_handler.activate_button_by_keyboard(
        dialog, user_choice, key_callback=_send_key_via_mcp
    )
    if not success:
        _speak(f"Could not understand choice {user_choice}")
        _mcp_client.call_tool("key_combo", {"keys": "Escape"})
        return "canceled"

    _dialog_handler.verify_dialog_closed(dialog, timeout=2.0)
    return user_choice


# --- Focus / Open ---


def _find_all_matching_windows(app_name, windows):
    """Find all windows matching an app name by wmClass."""
    first_match = _smart_match_window(app_name, windows)
    if not first_match:
        return []
    target_wm = first_match.get("wmClass", "")
    return [w for w in windows if w.get("wmClass", "") == target_wm]


@step(
    "focus other {app}",
    "focus next {app}",
    "next {app} window",
    "other {app} window",
    "other {app}",
    category="window",
    help_text="Cycle focus between multiple windows of the same app",
)
def handle_focus_next_instance(context, app):
    windows = _list_windows()
    if not windows:
        return "No windows open"

    matches = _find_all_matching_windows(app, windows)
    if not matches:
        return f"No window found matching '{app}'"
    if len(matches) == 1:
        friendly = _get_friendly_app_name(matches[0].get("wmClass", app))
        _mcp_client.call_tool("focus_window", {"window_id": matches[0]["id"]})
        return f"Only one {friendly} window open"

    focused_idx = next(
        (i for i, w in enumerate(matches) if w.get("focused", False)),
        -1,
    )
    next_idx = (focused_idx + 1) % len(matches)
    next_win = matches[next_idx]
    friendly = _get_friendly_app_name(next_win.get("wmClass", app))
    _mcp_client.call_tool("focus_window", {"window_id": next_win["id"]})
    return f"Focused next {friendly} window"


@step(
    "switch to {app}",
    "focus {app}",
    "go to {app}",
    category="window",
    help_text="Switch to or focus an application window",
)
def handle_focus(context, app):
    target, result = _find_window(app)
    error = _check_find_result(target, result, app)
    if error:
        return error
    window_id = target["id"]
    friendly = _get_friendly_app_name(target.get("wmClass", app))
    _mcp_client.call_tool("focus_window", {"window_id": window_id})
    matched, _ = _verify_window_state(window_id, {"focused": True})
    if matched is False:
        return f"Tried to focus {friendly} but it doesn't appear focused"
    return f"Focused {friendly}"


def _get_focused_window():
    windows = _list_windows()
    if not windows:
        return None
    return next((w for w in windows if w.get("focused", False)), None)


# --- Focus (focused) ---


@step(
    "focus",
    "focus window",
    "focus the window",
    category="window",
    help_text="Focus the current window",
)
def handle_focus_focused(context):
    target = _get_focused_window()
    if not target:
        return "No focused window found"
    friendly = _get_friendly_app_name(target.get("wmClass", ""))
    return f"{friendly} is already focused"


# --- Close ---


@step(
    "close",
    "close window",
    "close the window",
    category="window",
    help_text="Close the focused window",
)
def handle_close_focused(context):
    target = _get_focused_window()
    if not target:
        return "No focused window found"
    window_id = target["id"]
    wm_class = target.get("wmClass", "")
    friendly = _get_friendly_app_name(wm_class)
    atspi_name = _resolve_atspi_name(wm_class)
    log_and_print(f"[CLOSE] Focusing and closing {friendly} (id={window_id}, atspi={atspi_name})")
    _mcp_client.call_tool("focus_window", {"window_id": window_id})
    _mcp_client.call_tool("close_window", {"window_id": window_id})
    log_and_print("[CLOSE] close_window returned, checking for dialog")
    dialog_result = _handle_save_dialog(window_id, atspi_name)
    if dialog_result == "canceled":
        return "Close operation canceled"
    if dialog_result:
        return f"Successfully closed {friendly}"
    windows_after = _list_windows()
    if windows_after and not any(w["id"] == window_id for w in windows_after):
        return f"Successfully closed {friendly}"
    return f"Close command sent to {friendly}"


@step(
    "close {app}",
    "quit {app}",
    "exit {app}",
    "kill {app}",
    category="window",
    help_text="Close an application window",
)
def handle_close(context, app):
    target, result = _find_window(app)
    error = _check_find_result(target, result, app)
    if error:
        return error
    window_id = target["id"]
    wm_class = target.get("wmClass", app)
    friendly = _get_friendly_app_name(wm_class)
    atspi_name = _resolve_atspi_name(wm_class)
    log_and_print(f"[CLOSE] Focusing and closing {friendly} (id={window_id}, atspi={atspi_name})")
    _mcp_client.call_tool("focus_window", {"window_id": window_id})
    _mcp_client.call_tool("close_window", {"window_id": window_id})
    log_and_print("[CLOSE] close_window returned, checking for dialog")

    dialog_result = _handle_save_dialog(window_id, atspi_name)
    if dialog_result == "canceled":
        return "Close operation canceled"
    if dialog_result:
        return f"Successfully closed {friendly}"

    windows_after = _list_windows()
    if windows_after and not any(w["id"] == window_id for w in windows_after):
        return f"Successfully closed {friendly}"
    return f"Close command sent to {friendly}"


# --- Minimize ---


@step(
    "minimize",
    "minimize window",
    "minimize the window",
    category="window",
    help_text="Minimize the focused window",
)
def handle_minimize_focused(context):
    target = _get_focused_window()
    if not target:
        return "No focused window found"
    window_id = target["id"]
    friendly = _get_friendly_app_name(target.get("wmClass", ""))
    _mcp_client.call_tool("minimize_window", {"window_id": window_id})
    matched, _ = _verify_window_state(window_id, {"minimized": True})
    if matched is False:
        return f"Tried to minimize {friendly} but it still appears on screen"
    return f"Minimized {friendly}"


@step("minimize {app}", "hide {app}", category="window", help_text="Minimize an application window")
def handle_minimize(context, app):
    target, result = _find_window(app)
    error = _check_find_result(target, result, app)
    if error:
        return error
    window_id = target["id"]
    friendly = _get_friendly_app_name(target.get("wmClass", app))
    _mcp_client.call_tool("minimize_window", {"window_id": window_id})
    matched, _ = _verify_window_state(window_id, {"minimized": True})
    if matched is False:
        return f"Tried to minimize {friendly} but it still appears on screen"
    return f"Minimized {friendly}"


# --- Maximize ---


@step(
    "maximize",
    "maximize window",
    "maximize the window",
    "fullscreen",
    category="window",
    help_text="Maximize the focused window",
)
def handle_maximize_focused(context):
    target = _get_focused_window()
    if not target:
        return "No focused window found"
    window_id = target["id"]
    friendly = _get_friendly_app_name(target.get("wmClass", ""))
    if target.get("maximized", False):
        _mcp_client.call_tool("unmaximize_window", {"window_id": window_id})
        return f"Restored {friendly}"
    _mcp_client.call_tool("maximize_window", {"window_id": window_id})
    matched, _ = _verify_window_state(window_id, {"maximized": True})
    if matched is False:
        return f"Tried to maximize {friendly} but window state didn't change"
    return f"Maximized {friendly}"


@step("maximize {app}", category="window", help_text="Maximize an application window")
def handle_maximize(context, app):
    target, result = _find_window(app)
    error = _check_find_result(target, result, app)
    if error:
        return error
    window_id = target["id"]
    friendly = _get_friendly_app_name(target.get("wmClass", app))

    if target.get("maximized", False):
        _mcp_client.call_tool("unmaximize_window", {"window_id": window_id})
        return f"Restored {friendly}"
    else:
        _mcp_client.call_tool("maximize_window", {"window_id": window_id})
        matched, _ = _verify_window_state(window_id, {"maximized": True})
        if matched is False:
            return f"Tried to maximize {friendly} but window state didn't change"
        return f"Maximized {friendly}"


# --- Restore ---


@step(
    "restore",
    "restore window",
    "restore the window",
    category="window",
    help_text="Restore the focused window",
)
def handle_restore_focused(context):
    target = _get_focused_window()
    if not target:
        return "No focused window found"
    window_id = target["id"]
    friendly = _get_friendly_app_name(target.get("wmClass", ""))
    is_maximized = target.get("maximized", False)
    _mcp_client.call_tool("unminimize_window", {"window_id": window_id})
    _mcp_client.call_tool("focus_window", {"window_id": window_id})
    if is_maximized:
        _mcp_client.call_tool("unmaximize_window", {"window_id": window_id})
    return f"Restored {friendly}"


@step(
    "restore {app}",
    "unminimize {app}",
    category="window",
    help_text="Restore a minimized or maximized window",
)
def handle_restore(context, app):
    target, result = _find_window(app)
    error = _check_find_result(target, result, app)
    if error:
        return error
    window_id = target["id"]
    friendly = _get_friendly_app_name(target.get("wmClass", app))
    is_maximized = target.get("maximized", False)

    _mcp_client.call_tool("unminimize_window", {"window_id": window_id})
    _mcp_client.call_tool("focus_window", {"window_id": window_id})
    if is_maximized:
        _mcp_client.call_tool("unmaximize_window", {"window_id": window_id})
    return f"Restored {friendly}"


# --- List windows ---


@step(
    "list windows",
    "what windows are open",
    "what applications are running",
    "what apps are running",
    "what's running",
    "show windows",
    category="window",
    help_text="List all open windows",
)
def handle_list_windows(context):
    windows = _list_windows()
    if isinstance(windows, str):
        return windows
    if not windows:
        return "No windows are currently open."
    titles = [w.get("title", "Untitled") for w in windows[:10]]
    return f"Found {len(windows)} open windows: {', '.join(titles)}"


# --- Window tiling ---

_TILE_POSITIONS = {
    "left half": lambda w, h: (0, 0, w // 2, h),
    "right half": lambda w, h: (w // 2, 0, w // 2, h),
    "top half": lambda w, h: (0, 0, w, h // 2),
    "bottom half": lambda w, h: (0, h // 2, w, h // 2),
    "top left": lambda w, h: (0, 0, w // 2, h // 2),
    "top right": lambda w, h: (w // 2, 0, w // 2, h // 2),
    "bottom left": lambda w, h: (0, h // 2, w // 2, h // 2),
    "bottom right": lambda w, h: (w // 2, h // 2, w // 2, h // 2),
    "left side": lambda w, h: (0, 0, w // 2, h),
    "right side": lambda w, h: (w // 2, 0, w // 2, h),
    "the left": lambda w, h: (0, 0, w // 2, h),
    "the right": lambda w, h: (w // 2, 0, w // 2, h),
    "left": lambda w, h: (0, 0, w // 2, h),
    "right": lambda w, h: (w // 2, 0, w // 2, h),
    "to left": lambda w, h: (0, 0, w // 2, h),
    "to right": lambda w, h: (w // 2, 0, w // 2, h),
    "to the left": lambda w, h: (0, 0, w // 2, h),
    "to the right": lambda w, h: (w // 2, 0, w // 2, h),
    "top": lambda w, h: (0, 0, w, h // 2),
    "bottom": lambda w, h: (0, h // 2, w, h // 2),
    "center": lambda w, h: (w // 4, h // 4, w // 2, h // 2),
}


def _tile_window(app_name, position):
    for suffix in (" of the screen", " of screen", " corner", " side"):
        if position.endswith(suffix):
            position = position[: -len(suffix)]
            break
    position = position.strip()
    calc_fn = _TILE_POSITIONS.get(position)
    if not calc_fn:
        return f"Unknown position: {position}"

    if app_name:
        target, result = _find_window(app_name)
        error = _check_find_result(target, result, app_name)
        if error:
            return error
    else:
        windows = _list_windows()
        if isinstance(windows, str):
            return windows
        target = next((w for w in (windows or []) if w.get("focused", False)), None)

    if not target:
        return "No window to tile"

    window_id = target["id"]
    friendly = _get_friendly_app_name(target.get("wmClass", ""))

    try:
        mon_result = _mcp_client.call_tool("get_monitors", {})
        monitors = json.loads(mon_result)
        primary = next((m for m in monitors if m.get("primary")), monitors[0])
        scr_w = primary["width"]
        scr_h = primary["height"]
    except Exception:
        scr_w, scr_h = 1920, 1080

    tx, ty, tw, th = calc_fn(scr_w, scr_h)
    _mcp_client.call_tool(
        "move_resize_window", {"window_id": window_id, "x": tx, "y": ty, "width": tw, "height": th}
    )
    return f"Moved {friendly} to the {position}"


@step(
    "tile {app} to the {position}",
    "snap {app} to the {position}",
    "put {app} on the {position}",
    "snap {app} {position}",
    "tile {app} {position}",
    category="window",
    help_text="Tile a window to a screen position",
)
def handle_tile_app(context, app, position):
    return _tile_window(app, position)


@step(
    "tile {position}",
    "snap {position}",
    category="window",
    help_text="Tile the focused window to a position",
)
def handle_tile_focused(context, position):
    return _tile_window(None, position)


# --- Window screenshot ---


@step(
    "take a screenshot of {app}",
    "take screenshot of {app}",
    "screenshot of {app}",
    "capture {app}",
    "screenshot {app}",
    category="window",
    help_text="Take a screenshot of a specific window",
)
def handle_window_screenshot(context, app):
    target, result = _find_window(app)
    error = _check_find_result(target, result, app)
    if error:
        return error
    window_id = target["id"]
    friendly = _get_friendly_app_name(target.get("wmClass", app))
    result = _mcp_client.call_tool(
        "screenshot_window",
        {"window_id": window_id, "include_frame": True, "include_cursor": False, "format": "path"},
    )
    if result.startswith("Error"):
        return result
    return f"Screenshot of {friendly} saved to Screenshots."


# --- Move to monitor ---


def _move_to_monitor(app_name, monitor_target):
    """Move a window to another monitor.

    monitor_target: "other" or a 1-based monitor number.
    """
    if app_name:
        target, result = _find_window(app_name)
        error = _check_find_result(target, result, app_name)
        if error:
            return error
    else:
        target = _get_focused_window()
    if not target:
        return "No window to move"

    window_id = target["id"]
    friendly = _get_friendly_app_name(target.get("wmClass", ""))
    current_monitor = target.get("monitor", 0)

    try:
        mon_result = _mcp_client.call_tool("get_monitors", {})
        monitors = json.loads(mon_result)
    except Exception:
        return "Could not get monitor information"

    if len(monitors) < 2:
        return "Only one monitor detected"

    if monitor_target == "other":
        dest = next((m for m in monitors if m["index"] != current_monitor), None)
    else:
        dest_index = int(monitor_target) - 1
        dest = next((m for m in monitors if m["index"] == dest_index), None)

    if not dest:
        return f"Monitor {monitor_target} not found"

    dest_x = dest["x"] + (dest["width"] - target["width"]) // 2
    dest_y = dest["y"] + (dest["height"] - target["height"]) // 2
    _mcp_client.call_tool(
        "move_resize_window",
        {
            "window_id": window_id,
            "x": dest_x,
            "y": dest_y,
            "width": target["width"],
            "height": target["height"],
        },
    )
    return f"Moved {friendly} to monitor {dest['index'] + 1}"


@step(
    "move {app} to other monitor",
    "move {app} to the other monitor",
    "send {app} to other monitor",
    category="window",
    help_text="Move an application to the other monitor",
)
def handle_move_to_other_monitor(context, app):
    return _move_to_monitor(app, "other")


@step(
    "move to other monitor",
    "move window to other monitor",
    "move to the other monitor",
    "send to other monitor",
    category="window",
    help_text="Move the focused window to the other monitor",
)
def handle_move_focused_to_other_monitor(context):
    return _move_to_monitor(None, "other")


@step(
    "move {app} to monitor {n:d}",
    "send {app} to monitor {n:d}",
    category="window",
    help_text="Move an application to a specific monitor",
)
def handle_move_to_monitor_n(context, app, n):
    return _move_to_monitor(app, str(n))


@step(
    "move to monitor {n:d}",
    "move window to monitor {n:d}",
    "send to monitor {n:d}",
    category="window",
    help_text="Move the focused window to a specific monitor",
)
def handle_move_focused_to_monitor_n(context, n):
    return _move_to_monitor(None, str(n))


_ORDINALS = {"first": 1, "second": 2, "third": 3, "fourth": 4}


@step(
    "move {app} to the {ordinal} monitor",
    "send {app} to the {ordinal} monitor",
    category="window",
    help_text="Move an application to a monitor by ordinal name",
)
def handle_move_to_monitor_ordinal(context, app, ordinal):
    n = _ORDINALS.get(ordinal.lower())
    if n is None:
        return f"Unknown monitor position '{ordinal}'"
    return _move_to_monitor(app, str(n))


@step(
    "move to the {ordinal} monitor",
    "move window to the {ordinal} monitor",
    "send to the {ordinal} monitor",
    category="window",
    help_text="Move the focused window to a monitor by ordinal name",
)
def handle_move_focused_to_monitor_ordinal(context, ordinal):
    n = _ORDINALS.get(ordinal.lower())
    if n is None:
        return f"Unknown monitor position '{ordinal}'"
    return _move_to_monitor(None, str(n))
