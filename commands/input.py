import re
import time

from commands import _dialog_handler, _listen, _mcp_client, _speak, step

DIALOG_CHECK_SHORTCUTS = {"Alt+F4", "Ctrl+Q", "Ctrl+W", "Ctrl+Shift+W"}

_MULTI_WORD_KEY_MAP = {
    "page down": "Page_Down",
    "page-down": "Page_Down",
    "pagedown": "Page_Down",
    "page up": "Page_Up",
    "page-up": "Page_Up",
    "pageup": "Page_Up",
    "caps lock": "Caps_Lock",
    "caps-lock": "Caps_Lock",
    "capslock": "Caps_Lock",
    "num lock": "Num_Lock",
    "num-lock": "Num_Lock",
    "numlock": "Num_Lock",
    "scroll lock": "Scroll_Lock",
    "scroll-lock": "Scroll_Lock",
    "print screen": "Print",
    "print-screen": "Print",
    "left arrow": "Left",
    "right arrow": "Right",
    "up arrow": "Up",
    "down arrow": "Down",
}

_KEY_NAME_MAP = {
    "control": "ctrl",
    "command": "super",
    "escape": "Escape",
    "enter": "Return",
    "return": "Return",
    "delete": "Delete",
    "backspace": "BackSpace",
    "tab": "Tab",
    "space": "space",
    "home": "Home",
    "end": "End",
    "insert": "Insert",
    "up": "Up",
    "down": "Down",
    "left": "Left",
    "right": "Right",
    "print": "Print",
    "plus": "plus",
    "minus": "minus",
}


def _send_key_via_mcp(keys):
    if "+" in keys:
        _mcp_client.call_tool("key_combo", {"keys": keys})
    else:
        _mcp_client.call_tool("key_press", {"key": keys})


def _handle_dialog_after_shortcut(normalized):
    if normalized not in DIALOG_CHECK_SHORTCUTS:
        return None
    time.sleep(0.5)
    dialog = _dialog_handler.detect_save_dialog(app_name=None, timeout=3.0)
    if not dialog:
        return None

    buttons = dialog["info"]["buttons"]
    button_list = (
        ", ".join([btn["text"] for btn in buttons]) if buttons else "Save, Discard, Cancel"
    )
    _speak(f"The window has unsaved changes. Options: {button_list}. What would you like to do?")
    user_choice = _listen()

    if not user_choice:
        _speak("No response heard. Canceling.")
        _mcp_client.call_tool("key_combo", {"keys": "Escape"})
        return f"Pressed {normalized} but canceled (no response to dialog)"

    success = _dialog_handler.activate_button_by_keyboard(
        dialog, user_choice, key_callback=_send_key_via_mcp
    )
    if not success:
        _speak(f"Could not understand choice {user_choice}")
        _mcp_client.call_tool("key_combo", {"keys": "Escape"})
        return f"Pressed {normalized} but unrecognized dialog choice"

    _dialog_handler.verify_dialog_closed(dialog, timeout=2.0)
    return f"Pressed {normalized} and handled save dialog"


# --- Type text ---

_MATH_OPERATORS = {
    "plus": "+",
    "minus": "-",
    "times": "*",
    "divided by": "/",
    "equals": "=",
}


def _restore_math_operators(text):
    for word, symbol in _MATH_OPERATORS.items():
        text = re.sub(rf"(?<=\d)\s+{word}\s+(?=\d)", f" {symbol} ", text)
    return text


@step("type {text}", category="input", help_text="Type text character by character")
def handle_type(context, text):
    text = _restore_math_operators(text)
    _mcp_client.call_tool("type_text", {"text": text})
    return f"Typed: {text}"


# --- Key press ---


@step(
    "press {keys}",
    "hit {keys}",
    "push {keys}",
    category="input",
    help_text="Press a key or key combination (e.g., ctrl+c, enter, escape)",
)
def handle_key_press(context, keys):
    normalized = keys.strip()

    for phrase, gdk_name in _MULTI_WORD_KEY_MAP.items():
        pattern = re.compile(re.escape(phrase), re.IGNORECASE)
        normalized = pattern.sub(gdk_name, normalized)

    normalized = re.sub(r"(?<=[a-zA-Z])-(?=[a-zA-Z0-9])", "+", normalized)

    normalized = normalized.replace(" ", "+")
    parts = normalized.split("+")
    parts = [_KEY_NAME_MAP.get(p.lower(), p) for p in parts]
    normalized = "+".join(parts)

    _send_key_via_mcp(normalized)

    dialog_result = _handle_dialog_after_shortcut(normalized)
    if dialog_result:
        return dialog_result
    return f"Pressed {normalized}"


# --- Mouse click ---


@step("click at {x:d} {y:d}", category="input", help_text="Click at screen coordinates")
def handle_click(context, x, y):
    _mcp_client.call_tool("mouse_click", {"x": x, "y": y, "button": 1})
    return f"Clicked at ({x}, {y})"


@step(
    "double click at {x:d} {y:d}", category="input", help_text="Double-click at screen coordinates"
)
def handle_double_click(context, x, y):
    _mcp_client.call_tool("mouse_double_click", {"x": x, "y": y, "button": 1})
    return f"Double-clicked at ({x}, {y})"


@step("right click at {x:d} {y:d}", category="input", help_text="Right-click at screen coordinates")
def handle_right_click(context, x, y):
    _mcp_client.call_tool("mouse_click", {"x": x, "y": y, "button": 3})
    return f"Right-clicked at ({x}, {y})"


# --- Scroll ---


@step(
    "scroll down",
    "scroll down {amount:d} times",
    category="input",
    help_text="Scroll down on the current window",
)
def handle_scroll_down(context, amount=1):
    dy = 100 * amount
    result = _mcp_client.call_tool("mouse_scroll", {"x": 960, "y": 540, "dx": 0, "dy": dy})
    if result.startswith("Error"):
        for i in range(amount):
            _mcp_client.call_tool("key_press", {"key": "Page_Down"})
            if i < amount - 1:
                time.sleep(0.1)
    return "Scrolled down"


@step(
    "scroll up",
    "scroll up {amount:d} times",
    category="input",
    help_text="Scroll up on the current window",
)
def handle_scroll_up(context, amount=1):
    dy = -100 * amount
    result = _mcp_client.call_tool("mouse_scroll", {"x": 960, "y": 540, "dx": 0, "dy": dy})
    if result.startswith("Error"):
        for i in range(amount):
            _mcp_client.call_tool("key_press", {"key": "Page_Up"})
            if i < amount - 1:
                time.sleep(0.1)
    return "Scrolled up"


# --- Drag ---


@step(
    "drag from {x1:d} {y1:d} to {x2:d} {y2:d}",
    category="input",
    help_text="Drag from one position to another",
)
def handle_drag(context, x1, y1, x2, y2):
    _mcp_client.call_tool("mouse_drag", {"x1": x1, "y1": y1, "x2": x2, "y2": y2, "button": 1})
    return f"Dragged from ({x1}, {y1}) to ({x2}, {y2})"
