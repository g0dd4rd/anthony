import json
import os
import time

import requests
import webcolors

from utils import log_and_print
import utils
from voice_io import speak, listen_and_transcribe

# ----------------------------------------
# Dependency injection (set via init())
# ----------------------------------------
_mcp_client = None
_dialog_handler = None
_smart_match_window = None
_get_friendly_app_name = None

LLAMA_VISION_URL = 'http://127.0.0.1:8081/v1/chat/completions'

def init(mcp_client, dialog_handler, smart_match_fn, friendly_name_fn):
    global _mcp_client, _dialog_handler, _smart_match_window, _get_friendly_app_name
    _mcp_client = mcp_client
    _dialog_handler = dialog_handler
    _smart_match_window = smart_match_fn
    _get_friendly_app_name = friendly_name_fn


def _call_vision(system_prompt, user_prompt, img_base64):
    payload = {
        'messages': [
            {'role': 'system', 'content': system_prompt},
            {'role': 'user', 'content': [
                {'type': 'text', 'text': user_prompt},
                {'type': 'image_url', 'image_url': {
                    'url': f'data:image/png;base64,{img_base64}'
                }}
            ]}
        ],
        'temperature': 0.7,
        'max_tokens': 800,
    }
    resp = requests.post(LLAMA_VISION_URL, json=payload, timeout=120)
    resp.raise_for_status()
    return resp.json()['choices'][0]['message']['content']

DIALOG_CHECK_SHORTCUTS = {
    'Alt+F4',
    'Ctrl+Q',
    'Ctrl+W',
    'Ctrl+Shift+W',
}


def _send_key_via_mcp(keys: str):
    """Send keyboard input via MCP client (for dialog handler callback)."""
    if '+' in keys:
        _mcp_client.call_tool("key_combo", {"keys": keys})
    else:
        _mcp_client.call_tool("key_press", {"key": keys})


def parse_position(position: str, screen_width: int = 1920, screen_height: int = 1080) -> tuple:
    """Convert natural language position to screen coordinates."""
    position_lower = position.lower()
    center_x = screen_width // 2
    center_y = screen_height // 2
    left_x = 100
    right_x = screen_width - 100
    top_y = 100
    bottom_y = screen_height - 100

    if "top left" in position_lower:
        return (left_x, top_y)
    elif "top right" in position_lower:
        return (right_x, top_y)
    elif "top" in position_lower:
        return (center_x, top_y)
    elif "bottom left" in position_lower:
        return (left_x, bottom_y)
    elif "bottom right" in position_lower:
        return (right_x, bottom_y)
    elif "bottom" in position_lower:
        return (center_x, bottom_y)
    elif "left" in position_lower:
        return (left_x, center_y)
    elif "right" in position_lower:
        return (right_x, center_y)
    elif "center" in position_lower or "middle" in position_lower:
        return (center_x, center_y)
    else:
        return (center_x, center_y)


# ========================================
# CONSOLIDATED FACADE TOOLS
# ========================================

def window_control(action: str, window_name: str = "", x: int = 0, y: int = 0,
                  width: int = 800, height: int = 600, include_frame: bool = True) -> str:
    """Unified window management facade."""
    log_and_print(f"\n[WINDOW_CONTROL] Action: {action}, Window: {window_name or 'current'}")

    try:
        if action == "list":
            result = _mcp_client.call_tool("list_windows", {})
            if result.startswith("Error"):
                return result
            windows = json.loads(result)
            if not windows:
                return "No windows are currently open."
            window_titles = [w.get('title', 'Untitled') for w in windows[:10]]
            return f"Found {len(windows)} open windows: {', '.join(window_titles)}"

        if action == "screenshot_area":
            result = _mcp_client.call_tool("screenshot_area", {
                "x": x, "y": y, "width": width, "height": height,
                "include_cursor": False, "format": "path"
            })
            if result.startswith("Error"):
                return result
            return f"Area screenshot saved to Screenshots."

        result = _mcp_client.call_tool("list_windows", {})
        if result.startswith("Error"):
            return result
        windows = json.loads(result)

        target_window = _smart_match_window(window_name, windows)
        if not target_window:
            return f"No window found matching '{window_name}'"

        window_id = target_window['id']
        wm_class = target_window.get('wmClass', 'Unknown')
        friendly_name = _get_friendly_app_name(wm_class)

        if action == "focus":
            _mcp_client.call_tool("focus_window", {"window_id": window_id})
            return f"Focused {friendly_name}"

        elif action == "close":
            window_title = target_window.get('title', 'Unknown')
            _mcp_client.call_tool("close_window", {"window_id": window_id})

            dialog = _dialog_handler.detect_save_dialog(app_name=None, timeout=3.0)
            if not dialog:
                time.sleep(0.5)
                result = _mcp_client.call_tool("list_windows", {})
                if not result.startswith("Error"):
                    windows_after = json.loads(result)
                    if not any(w['id'] == window_id for w in windows_after):
                        return f"Successfully closed {friendly_name}"

                dialog = _dialog_handler.detect_save_dialog(app_name=None, timeout=5.0)
                if not dialog:
                    return f"Window did not close. No dialog detected."

            buttons = dialog['info']['buttons']
            button_list = ', '.join([btn['text'] for btn in buttons]) if buttons else "Save, Discard, Cancel"
            voice_prompt = f"The window has unsaved changes. Options: {button_list}. What would you like to do?"

            speak(voice_prompt)
            user_choice = listen_and_transcribe()

            if not user_choice:
                speak("No response heard. Canceling close operation.")
                _mcp_client.call_tool("key_combo", {"keys": "Escape"})
                return "Close operation canceled"

            success = _dialog_handler.activate_button_by_keyboard(dialog, user_choice, key_callback=_send_key_via_mcp)
            if not success:
                speak(f"Could not understand choice {user_choice}")
                _mcp_client.call_tool("key_combo", {"keys": "Escape"})
                return f"Unrecognized choice: {user_choice}"

            closed = _dialog_handler.verify_dialog_closed(dialog, timeout=2.0)
            if closed:
                time.sleep(0.5)
                result = _mcp_client.call_tool("list_windows", {})
                if not result.startswith("Error"):
                    windows_final = json.loads(result)
                    window_still_open = any(w['id'] == window_id for w in windows_final)
                    if window_still_open:
                        return f"Dialog closed. {friendly_name} is still open"
                    else:
                        return f"Successfully closed {friendly_name}"
                return "Dialog handled successfully"
            else:
                return "Dialog might still be open"

        elif action == "minimize":
            _mcp_client.call_tool("minimize_window", {"window_id": window_id})
            return f"Minimized {friendly_name}"

        elif action == "maximize":
            state = target_window.get('state', {})
            is_maximized = state.get('maximized', False)
            if is_maximized:
                _mcp_client.call_tool("unmaximize_window", {"window_id": window_id})
                return f"Restored {friendly_name}"
            else:
                _mcp_client.call_tool("maximize_window", {"window_id": window_id})
                return f"Maximized {friendly_name}"

        elif action == "restore":
            state = target_window.get('state', {})
            is_maximized = state.get('maximized', False)
            _mcp_client.call_tool("unminimize_window", {"window_id": window_id})
            _mcp_client.call_tool("focus_window", {"window_id": window_id})
            if is_maximized:
                _mcp_client.call_tool("unmaximize_window", {"window_id": window_id})
            return f"Restored {friendly_name}"

        elif action == "screenshot":
            result = _mcp_client.call_tool("screenshot_window", {
                "window_id": window_id, "include_frame": include_frame,
                "include_cursor": False, "format": "path"
            })
            if result.startswith("Error"):
                return result
            return f"Screenshot of {friendly_name} saved to Screenshots."

        elif action == "move_resize":
            try:
                x_int = int(x) if isinstance(x, (int, str)) else x
                y_int = int(y) if isinstance(y, (int, str)) else y
                width_int = int(width) if isinstance(width, (int, str)) else width
                height_int = int(height) if isinstance(height, (int, str)) else height
            except (ValueError, TypeError):
                return f"Error: move_resize requires integer dimensions, got x={x}, y={y}, width={width}, height={height}"

            window_info = _mcp_client.call_tool("list_windows", {})
            windows = json.loads(window_info)
            current_window = next((w for w in windows if w['id'] == window_id), None)

            old_width = current_window.get('width', 0) if current_window else 0
            old_height = current_window.get('height', 0) if current_window else 0
            old_x = current_window.get('x', 0) if current_window else 0
            old_y = current_window.get('y', 0) if current_window else 0

            _mcp_client.call_tool("move_resize_window", {
                "window_id": window_id, "x": x_int, "y": y_int,
                "width": width_int, "height": height_int
            })

            size_changed = abs(width_int - old_width) > 50 or abs(height_int - old_height) > 50
            position_changed = abs(x_int - old_x) > 50 or abs(y_int - old_y) > 50

            position_description = None
            if x_int == 0 and width_int < 1000:
                position_description = "left side"
            elif x_int > 900 and x_int < 1000 and width_int < 1000:
                position_description = "right side"
            elif y_int == 0 and height_int < 600:
                position_description = "top"
            elif y_int > 400 and height_int < 700:
                position_description = "bottom"
            elif x_int == 0 and y_int == 0:
                position_description = "top-left corner"
            elif x_int > 900 and y_int == 0:
                position_description = "top-right corner"

            if position_description and position_changed:
                return f"Moved {friendly_name} to the {position_description}"
            elif size_changed and not position_changed:
                return f"Resized {friendly_name} to {width_int}x{height_int}"
            elif position_changed and not size_changed:
                return f"Moved {friendly_name}"
            elif position_changed and size_changed:
                return f"Moved and resized {friendly_name} to {width_int}x{height_int}"
            else:
                return f"Window {friendly_name} is already at the requested position and size"

        else:
            return f"Unknown window action: {action}"

    except Exception as e:
        return f"Error in window_control: {str(e)}"


def input_control(action: str, text: str = "", keys: str = "",
                 x: int = 0, y: int = 0, to_x: int = 0, to_y: int = 0,
                 direction: str = "down", amount: int = 1, button: int = 1,
                 from_position: str = "center", to_position: str = "center") -> str:
    """Unified input control facade."""
    log_and_print(f"\n[INPUT_CONTROL] Action: {action}")

    try:
        if action == "type":
            _mcp_client.call_tool("type_text", {"text": text})
            return f"Typed: {text}"

        elif action == "key_combo":
            normalized = keys
            if " " in normalized and "+" not in normalized:
                normalized = normalized.replace(" ", "+")

            _mcp_client.call_tool("key_combo", {"keys": normalized})

            if normalized in DIALOG_CHECK_SHORTCUTS:
                time.sleep(0.5)
                dialog = _dialog_handler.detect_save_dialog(app_name=None, timeout=3.0)

                if dialog:
                    buttons = dialog['info']['buttons']
                    button_list = ', '.join([btn['text'] for btn in buttons]) if buttons else "Save, Discard, Cancel"
                    voice_prompt = f"The window has unsaved changes. Options: {button_list}. What would you like to do?"

                    speak(voice_prompt)
                    user_choice = listen_and_transcribe()

                    if not user_choice:
                        speak("No response heard. Canceling close operation.")
                        _mcp_client.call_tool("key_combo", {"keys": "Escape"})
                        return f"Pressed {normalized} but close operation was canceled (no response to dialog)"

                    success = _dialog_handler.activate_button_by_keyboard(dialog, user_choice, key_callback=_send_key_via_mcp)
                    if not success:
                        speak(f"Could not understand choice {user_choice}")
                        _mcp_client.call_tool("key_combo", {"keys": "Escape"})
                        return f"Pressed {normalized} but unrecognized dialog choice: {user_choice}"

                    closed = _dialog_handler.verify_dialog_closed(dialog, timeout=2.0)
                    if closed:
                        return f"Pressed {normalized} and handled save dialog: {user_choice}"
                    else:
                        return f"Pressed {normalized} - dialog might still be open"

            return f"Pressed {normalized}"

        elif action == "key_press":
            _mcp_client.call_tool("key_press", {"key": keys})
            return f"Pressed {keys}"

        elif action == "click":
            _mcp_client.call_tool("mouse_click", {"x": x, "y": y, "button": button})
            return f"Clicked at ({x}, {y})"

        elif action == "double_click":
            _mcp_client.call_tool("mouse_double_click", {"x": x, "y": y, "button": button})
            return f"Double-clicked at ({x}, {y})"

        elif action == "drag":
            if to_x == 0 and to_y == 0:
                from_coords = parse_position(from_position)
                to_coords = parse_position(to_position)
                x, y = from_coords
                to_x, to_y = to_coords

            _mcp_client.call_tool("mouse_drag", {
                "x1": x, "y1": y, "x2": to_x, "y2": to_y, "button": button
            })
            return f"Dragged from ({x}, {y}) to ({to_x}, {to_y})"

        elif action == "scroll":
            is_down = "down" in direction.lower()
            dy = 100 * amount if is_down else -100 * amount
            result = _mcp_client.call_tool("mouse_scroll", {
                "x": 960, "y": 540, "dx": 0, "dy": dy
            })

            if not result.startswith("Error"):
                return f"Scrolled {direction}"

            key = "Page_Down" if is_down else "Page_Up"
            for i in range(amount):
                _mcp_client.call_tool("key_combo", {"keys": key})
                if i < amount - 1:
                    time.sleep(0.1)
            return f"Scrolled {direction}"

        else:
            return f"Unknown input action: {action}"

    except Exception as e:
        return f"Error in input_control: {str(e)}"


def audio_control(action: str, level: int = 0, relative: bool = False) -> str:
    """Unified audio control facade."""
    log_and_print(f"\n[AUDIO_CONTROL] Action: {action}")

    try:
        if action == "volume":
            return _mcp_client.call_tool("set_volume", {"volume": level, "relative": relative})
        elif action == "mute":
            return _mcp_client.call_tool("mute_volume", {"mute": True})
        elif action == "unmute":
            return _mcp_client.call_tool("mute_volume", {"mute": False})
        elif action in ["play", "pause", "play_pause", "next", "previous", "stop"]:
            mcp_action = action.replace("_", "-")
            return _mcp_client.call_tool("media_control", {"action": mcp_action})
        else:
            return f"Unknown audio action: {action}"
    except Exception as e:
        return f"Error in audio_control: {str(e)}"


def system_settings(action: str, state: str = "toggle", path: str = "") -> str:
    """Unified system settings facade."""
    log_and_print(f"\n[SYSTEM_SETTINGS] Action: {action}, State: {state}")

    try:
        if action == "wallpaper":
            return _mcp_client.call_tool("set_wallpaper", {"image_path": path or state})

        setting_map = {
            "dark_mode": "dark_style",
            "night_light": "night_light",
            "do_not_disturb": "do_not_disturb",
            "wifi": "wifi",
            "bluetooth": "bluetooth"
        }

        setting_name = setting_map.get(action)
        if not setting_name:
            return f"Unknown setting: {action}"

        if state.lower() in ["on", "true", "enable", "enabled"]:
            enabled = True
        elif state.lower() in ["off", "false", "disable", "disabled"]:
            enabled = False
        else:
            return "Please specify 'on' or 'off' for this setting"

        return _mcp_client.call_tool("quick_settings", {"setting": setting_name, "enabled": enabled})
    except Exception as e:
        return f"Error in system_settings: {str(e)}"


def vision_control(action: str, x: int = 0, y: int = 0, path: str = "") -> str:
    """Unified vision operations facade."""
    log_and_print(f"\n[VISION_CONTROL] Action: {action}")
    DEBUG = utils.DEBUG

    try:
        if action == "screenshot":
            result = _mcp_client.call_tool("screenshot", {"include_cursor": False, "format": "path"})
            if result.startswith("Error"):
                return result
            return f"Screenshot saved to Screenshots."

        elif action == "describe":
            result = _mcp_client.call_tool("screenshot", {"include_cursor": False, "format": "path"})
            if result.startswith("Error"):
                return result

            screenshot_path = result.strip()
            with open(screenshot_path, 'rb') as img_file:
                import base64
                img_data = base64.b64encode(img_file.read()).decode('utf-8')

            description = _call_vision(
                'You are a screen reader for visually impaired users. Describe what you see in plain text without any formatting. Do not use markdown, asterisks, or special characters. Answer directly without explaining your reasoning process.',
                'What applications and windows are visible on this desktop screenshot?',
                img_data
            )

            try:
                os.remove(screenshot_path)
            except:
                pass
            return description

        elif action == "describe_file":
            file_path = os.path.expanduser(path)
            if not os.path.isfile(file_path):
                log_and_print(f"[VISION_CONTROL] Exact path not found, searching via localsearch...")
                try:
                    search_result = _mcp_client.call_tool("search_files", {"query": os.path.basename(path), "file_type": "files", "limit": 5})
                    results = json.loads(search_result)
                    if results.get("count", 0) > 0:
                        file_path = results["results"][0]
                        log_and_print(f"[VISION_CONTROL] Resolved to: {file_path}")
                    else:
                        return f"File not found: {path}"
                except Exception:
                    return f"File not found: {path}"

            with open(file_path, 'rb') as img_file:
                import base64
                img_data = base64.b64encode(img_file.read()).decode('utf-8')

            description = _call_vision(
                'Describe the image in plain text without any formatting. Do not use markdown, asterisks, or special characters. Answer directly without explaining your reasoning process.',
                f'Describe this image: {os.path.basename(file_path)}',
                img_data
            )
            return description

        elif action == "describe_window":
            result = _mcp_client.call_tool("list_windows", {})
            if result.startswith("Error"):
                return result
            windows = json.loads(result)
            focused = next((w for w in windows if w.get('focused', False)), None)
            if not focused:
                return "No focused window found."
            window_id = focused['id']
            friendly_name = _get_friendly_app_name(focused.get('wmClass', ''))

            result = _mcp_client.call_tool("screenshot_window", {
                "window_id": window_id, "include_frame": False,
                "include_cursor": False, "format": "path"
            })
            if result.startswith("Error"):
                return result

            screenshot_path = result.strip()
            with open(screenshot_path, 'rb') as img_file:
                import base64
                img_data = base64.b64encode(img_file.read()).decode('utf-8')

            description = _call_vision(
                'Describe what you see in this application window in plain text without any formatting. Do not use markdown, asterisks, or special characters. Answer directly.',
                f'Describe the content shown in this {friendly_name} window.',
                img_data
            )

            try:
                os.remove(screenshot_path)
            except:
                pass
            return description

        elif action == "pick_color":
            log_and_print(f"[DEBUG] vision_control received coordinates: x={x}, y={y}, types: x={type(x)}, y={type(y)}", level='debug', console=DEBUG)
            result = _mcp_client.call_tool("pick_color", {"x": x, "y": y})
            log_and_print(f"[DEBUG] pick_color result: {result}", level='debug', console=DEBUG)

            try:
                rgb_data = json.loads(result)
                r, g, b = int(rgb_data['r']), int(rgb_data['g']), int(rgb_data['b'])
                try:
                    color_name = webcolors.rgb_to_name((r, g, b), spec='css3')
                except ValueError:
                    min_distance = float('inf')
                    closest_name = None
                    for name in webcolors.names('css3'):
                        named_rgb = webcolors.name_to_rgb(name)
                        distance = sum((a - b_val) ** 2 for a, b_val in zip((r, g, b), named_rgb)) ** 0.5
                        if distance < min_distance:
                            min_distance = distance
                            closest_name = name
                    color_name = closest_name
                return f"{color_name} (RGB: {r}, {g}, {b})"
            except Exception as e:
                log_and_print(f"[DEBUG] Color name conversion failed: {e}", level='debug', console=DEBUG)
                return result

        elif action == "get_monitors":
            result = _mcp_client.call_tool("get_monitors", {})
            try:
                monitors = json.loads(result)
                if len(monitors) == 0:
                    return "No monitors detected"
                elif len(monitors) == 1:
                    m = monitors[0]
                    primary_tag = " (primary)" if m.get('primary') else ""
                    return f"1 {primary_tag} monitor, resolution {m['width']}x{m['height']} at scale {m.get('scale', 1)}"
                else:
                    lines = [f"{len(monitors)} monitors connected:"]
                    for i, m in enumerate(monitors):
                        primary_tag = " (primary)" if m.get('primary') else ""
                        lines.append(f"Monitor {i+1}{primary_tag}, resolution {m['width']}x{m['height']} at position ({m['x']}, {m['y']})")
                    return " ".join(lines)
            except Exception as e:
                log_and_print(f"[DEBUG] Monitor formatting failed: {e}", level='debug', console=DEBUG)
                return result

        else:
            return f"Unknown vision action: {action}"

    except Exception as e:
        return f"Error in vision_control: {str(e)}"


def workspace_control(action: str, index: int = 0) -> str:
    """Unified workspace management facade."""
    log_and_print(f"\n[WORKSPACE_CONTROL] Action: {action}")

    try:
        if action == "list":
            result = _mcp_client.call_tool("list_workspaces", {})
            if result.startswith("Error"):
                return result
            try:
                workspaces = json.loads(result)
                if not workspaces:
                    return "No workspaces found"
                active_workspace = None
                for ws in workspaces:
                    if ws.get('active', False):
                        active_workspace = ws.get('index', 0)
                        break
                total = len(workspaces)
                return f"You have {total} workspace{'s' if total > 1 else ''}. You are on workspace {active_workspace + 1}."
            except json.JSONDecodeError:
                return result

        elif action == "activate":
            result = _mcp_client.call_tool("activate_workspace", {"index": index})
            if result.startswith("Error"):
                return result
            return f"Switched to workspace {index + 1}"

        else:
            return f"Unknown workspace action: {action}"

    except Exception as e:
        return f"Error in workspace_control: {str(e)}"
