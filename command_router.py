import json
import re
import time

from utils import log_and_print
import utils

from app_index import (retrieve_relevant_namespaces, smart_match_window,
                       get_friendly_app_name)
from tools.facades import (window_control, audio_control, system_settings,
                           vision_control)
from tools.standalone import (get_datetime, search_apps, run_install,
                              run_uninstall, get_app_shortcuts)

logger = utils.logger

# ----------------------------------------
# Dependency injection (set via init())
# ----------------------------------------
_mcp_client = None
_speak = None
_listen_and_transcribe = None


def init(mcp_client, speak_fn, listen_fn):
    global _mcp_client, _speak, _listen_and_transcribe
    _mcp_client = mcp_client
    _speak = speak_fn
    _listen_and_transcribe = listen_fn


def _log_shortcircuit(label, retrieval_start_time):
    log_and_print(f"[ROUTING] Short-circuit: {label}, skipping LLM")
    log_and_print(f"[TIMING] ⏱️  Response time: {time.time() - retrieval_start_time:.2f}s (no LLM)")


# ----------------------------------------
# Context preparation (RAG + auto-focus)
# ----------------------------------------
def prepare_command_context(user_input, command_messages, retrieval_start_time):
    """
    Run RAG namespace retrieval, auto-focus the detected app,
    and inject shortcut context into command_messages.

    Returns (relevant_namespaces, detected_app, auto_focused).
    """
    relevant_namespaces, detected_app = retrieve_relevant_namespaces(user_input, top_k=2)

    auto_focused = False
    if detected_app:
        try:
            focus_result = window_control("focus", detected_app)
            if "No window found" in focus_result:
                log_and_print(f"[ROUTING] App '{detected_app}' detected but not running, skipping auto-focus")
                command_messages[-1]["content"] += f"\n[{detected_app} is not currently running.]"
            else:
                auto_focused = True
                log_and_print(f"[ROUTING] Auto-focused: {focus_result}")
                command_messages[-1]["content"] += f"\n[{detected_app} is already focused. Do NOT open or search for it.]"
        except Exception as e:
            log_and_print(f"[ROUTING] Auto-focus failed: {e}")

        try:
            shortcut_info = get_app_shortcuts(detected_app)
            if not shortcut_info.startswith("No shortcuts"):
                command_messages[-1]["content"] += f"\n[{shortcut_info}]"
                log_and_print(f"[ROUTING] Injected shortcuts+skills for '{detected_app}'")
        except Exception as e:
            log_and_print(f"[ROUTING] Failed to inject shortcuts: {e}")
    else:
        try:
            result = _mcp_client.call_tool("list_windows", {})
            if not result.startswith("Error"):
                windows = json.loads(result)
                focused = next((w for w in windows if w.get('focused', False)), None)
                if focused:
                    wm_class = focused.get('wmClass', '')
                    shortcut_key = wm_class.lower()
                    for prefix in ('org.gnome.', 'org.mozilla.', 'org.'):
                        if shortcut_key.startswith(prefix):
                            shortcut_key = shortcut_key[len(prefix):]
                            break
                    shortcut_info = get_app_shortcuts(shortcut_key)
                    if not shortcut_info.startswith("No shortcuts"):
                        friendly = get_friendly_app_name(wm_class)
                        command_messages[-1]["content"] += f"\n[{friendly} is focused. {shortcut_info}]"
                        log_and_print(f"[ROUTING] Injected shortcuts for focused app '{shortcut_key}'")
                        if 'input' not in [ns for ns in relevant_namespaces]:
                            relevant_namespaces.append('input')
        except Exception as e:
            log_and_print(f"[ROUTING] Focused-window shortcut lookup failed: {e}")

    return relevant_namespaces, detected_app, auto_focused


# ----------------------------------------
# Short-circuit pattern matching
# ----------------------------------------
def try_short_circuit(user_input, user_input_lower, detected_app, auto_focused,
                      retrieval_start_time):
    """
    Try to handle the command via keyword pattern matching without the LLM.

    Returns True if handled (caller should continue), False to fall through to LLM.
    """
    # --- Focus / open app ---
    _focus_verbs = ('switch to', 'focus', 'go to', 'open')
    for fv in _focus_verbs:
        if user_input_lower.startswith(fv):
            remainder = user_input_lower[len(fv):].strip().strip('.,!').strip()
            remainder = remainder.removeprefix('the ').strip()
            if detected_app and remainder == detected_app and auto_focused:
                friendly = get_friendly_app_name(detected_app)
                _speak(f"Switched to {friendly}.")
                _log_shortcircuit("focus-only command", retrieval_start_time)
                return True
            elif not detected_app and remainder:
                result = window_control("focus", remainder)
                if "No window found" not in result:
                    _speak(result)
                    _log_shortcircuit(f"focused '{remainder}' by window match", retrieval_start_time)
                    return True
            break

    # --- Date/time ---
    _time_phrases = ('what time', 'what\'s the time', 'what is the time',
                     'what date', 'what\'s the date', 'what is the date',
                     'what day', 'what\'s the day', 'what is the day',
                     'current time', 'current date', 'tell me the time',
                     'tell me the date')
    if any(p in user_input_lower for p in _time_phrases):
        result = get_datetime()
        _speak(result)
        _log_shortcircuit("datetime query", retrieval_start_time)
        return True

    # --- Battery ---
    _battery_phrases = ('battery', 'charge level', 'power level',
                        'how much charge', 'how much power')
    if any(p in user_input_lower for p in _battery_phrases):
        result = _mcp_client.call_tool("get_battery_status", {})
        _speak(result)
        _log_shortcircuit("battery query", retrieval_start_time)
        return True

    # --- System setting toggles ---
    _toggle_map = {
        'dark mode':       'dark_mode',
        'dark style':      'dark_mode',
        'dark theme':      'dark_mode',
        'night light':     'night_light',
        'night mode':      'night_light',
        'do not disturb':  'do_not_disturb',
        'dnd':             'do_not_disturb',
        'wifi':            'wifi',
        'wi-fi':           'wifi',
        'bluetooth':       'bluetooth',
    }
    _on_verbs = ('turn on', 'enable', 'activate', 'switch on')
    _off_verbs = ('turn off', 'disable', 'deactivate', 'switch off')
    for setting_phrase, action_name in _toggle_map.items():
        if setting_phrase in user_input_lower:
            state = None
            if any(v in user_input_lower for v in _on_verbs):
                state = 'on'
            elif any(v in user_input_lower for v in _off_verbs):
                state = 'off'
            if state:
                result = system_settings(action_name, state)
                _speak(result)
                _log_shortcircuit(f"{setting_phrase} {state}", retrieval_start_time)
                return True
            break

    # --- App shortcuts query ---
    if 'shortcut' in user_input_lower:
        shortcut_app = detected_app
        if not shortcut_app:
            from app_index import app_name_map
            words = user_input_lower.split()
            for n in range(len(words), 0, -1):
                for i in range(len(words) - n + 1):
                    phrase = ' '.join(words[i:i+n])
                    if phrase in app_name_map:
                        shortcut_app = phrase
                        break
                if shortcut_app:
                    break
        if shortcut_app:
            shortcut_info = get_app_shortcuts(shortcut_app)
            if not shortcut_info.startswith("No shortcuts"):
                shortcuts_only = shortcut_info.split("\nSkills (")[0]
                lines = shortcuts_only.splitlines()
                shortcuts = [l.lstrip('- ').strip() for l in lines
                             if l.startswith('- ')]
                tts_text = f"Shortcuts for {shortcut_app}: " + ", ".join(shortcuts)
                _speak(tts_text)
                _log_shortcircuit(f"shortcuts for {shortcut_app}", retrieval_start_time)
                return True

    # --- Window management (close/minimize/maximize/restore + app name) ---
    if detected_app:
        _window_actions = {
            'close': 'close', 'quit': 'close', 'exit': 'close', 'kill': 'close',
            'minimize': 'minimize', 'hide': 'minimize',
            'maximize': 'maximize',
            'restore': 'restore', 'unminimize': 'restore',
        }
        for verb, action in _window_actions.items():
            if user_input_lower.startswith(verb):
                remainder = user_input_lower[len(verb):].strip().strip('.,!').strip()
                remainder = remainder.removeprefix('the ').strip()
                if remainder == detected_app:
                    result = window_control(action, detected_app)
                    _speak(result)
                    _log_shortcircuit(f"{action} {detected_app}", retrieval_start_time)
                    return True
                break

    # --- Window tiling ---
    _tile_positions = {
        'left half':      lambda w, h: (0, 0, w // 2, h),
        'right half':     lambda w, h: (w // 2, 0, w // 2, h),
        'top half':       lambda w, h: (0, 0, w, h // 2),
        'bottom half':    lambda w, h: (0, h // 2, w, h // 2),
        'top left':       lambda w, h: (0, 0, w // 2, h // 2),
        'top right':      lambda w, h: (w // 2, 0, w // 2, h // 2),
        'bottom left':    lambda w, h: (0, h // 2, w // 2, h // 2),
        'bottom right':   lambda w, h: (w // 2, h // 2, w // 2, h // 2),
        'left side':      lambda w, h: (0, 0, w // 2, h),
        'right side':     lambda w, h: (w // 2, 0, w // 2, h),
        'the left':       lambda w, h: (0, 0, w // 2, h),
        'the right':      lambda w, h: (w // 2, 0, w // 2, h),
        'center':         lambda w, h: (w // 4, h // 4, w // 2, h // 2),
    }
    if any(p in user_input_lower for p in ('move', 'tile', 'snap', 'put')):
        for position, calc_fn in _tile_positions.items():
            if position in user_input_lower:
                app_to_tile = detected_app
                if not app_to_tile:
                    try:
                        win_list = json.loads(_mcp_client.call_tool("list_windows", {}))
                        focused = next((w for w in win_list if w.get('focused', False)), None)
                        if focused:
                            app_to_tile = focused.get('wmClass', '')
                    except Exception:
                        pass
                if app_to_tile:
                    try:
                        mon_result = _mcp_client.call_tool("get_monitors", {})
                        monitors = json.loads(mon_result)
                        primary = next((m for m in monitors if m.get('primary')), monitors[0])
                        scr_w = primary['width']
                        scr_h = primary['height']
                        tx, ty, tw, th = calc_fn(scr_w, scr_h)
                        result = window_control("move_resize", app_to_tile, x=tx, y=ty, width=tw, height=th)
                        _speak(result)
                        _log_shortcircuit(f"tile {app_to_tile} to {position}", retrieval_start_time)
                        return True
                    except Exception as e:
                        log_and_print(f"[ROUTING] Tiling failed: {e}", level='warning')
                break

    # --- Mute/unmute tab (before audio controls to avoid conflict) ---
    _mute_tab_phrases = ('mute tab', 'mute the tab', 'mute this tab',
                         'silence tab', 'silence the tab', 'silence this tab')
    _unmute_tab_phrases = ('unmute tab', 'unmute the tab', 'unmute this tab')
    if any(p in user_input_lower for p in _mute_tab_phrases + _unmute_tab_phrases):
        from tools.facades import input_control
        input_control("key_combo", keys="ctrl+m", app_name=detected_app or "")
        action_word = "Unmuted" if any(p in user_input_lower for p in _unmute_tab_phrases) else "Muted"
        _speak(f"{action_word} tab.")
        _log_shortcircuit("mute/unmute tab", retrieval_start_time)
        return True

    # --- Audio controls ---
    audio_handled = False
    if user_input_lower in ('mute', 'mute the sound', 'mute sound', 'mute audio'):
        result = audio_control("mute")
        _speak(result)
        audio_handled = True
    elif any(user_input_lower == p for p in ('unmute', 'unmute the sound', 'unmute sound', 'unmute audio')):
        result = audio_control("unmute")
        _speak(result)
        audio_handled = True
    elif any(p in user_input_lower for p in ('volume up', 'turn up', 'louder', 'raise the volume', 'raise volume', 'increase volume', 'increase the volume')):
        result = audio_control("volume", level=10, relative=True)
        _speak(result)
        audio_handled = True
    elif any(p in user_input_lower for p in ('volume down', 'turn down', 'quieter', 'lower the volume', 'lower volume', 'decrease volume', 'decrease the volume')):
        result = audio_control("volume", level=-10, relative=True)
        _speak(result)
        audio_handled = True
    elif 'volume' in user_input_lower:
        vol_match = re.search(r'(\d+)\s*%?', user_input_lower)
        if vol_match:
            level = int(vol_match.group(1))
            result = audio_control("volume", level=level, relative=False)
            _speak(result)
            audio_handled = True
    elif user_input_lower in ('play', 'play music', 'resume', 'resume playback'):
        result = audio_control("play")
        _speak(result)
        audio_handled = True
    elif user_input_lower in ('pause', 'pause music', 'pause playback'):
        result = audio_control("pause")
        _speak(result)
        audio_handled = True
    elif user_input_lower in ('play pause', 'play/pause', 'toggle playback'):
        result = audio_control("play_pause")
        _speak(result)
        audio_handled = True
    elif user_input_lower in ('stop', 'stop music', 'stop playback', 'stop playing'):
        result = audio_control("stop")
        _speak(result)
        audio_handled = True
    elif user_input_lower in ('next', 'next song', 'next track', 'skip'):
        result = audio_control("next")
        _speak(result)
        audio_handled = True
    elif user_input_lower in ('previous', 'previous song', 'previous track', 'go back'):
        result = audio_control("previous")
        _speak(result)
        audio_handled = True
    if audio_handled:
        _log_shortcircuit("audio control", retrieval_start_time)
        return True

    # --- Screenshot ---
    _screenshot_phrases = ('take a screenshot', 'take screenshot', 'capture screen',
                           'screenshot', 'screen capture', 'grab the screen',
                           'capture the screen')
    if any(user_input_lower == p for p in _screenshot_phrases):
        result = vision_control("screenshot")
        _speak(result)
        _log_shortcircuit("screenshot", retrieval_start_time)
        return True
    if detected_app and 'screenshot' in user_input_lower:
        _app_screenshot_prefixes = ('take a screenshot of', 'take screenshot of',
                                    'screenshot of', 'capture')
        for prefix in _app_screenshot_prefixes:
            if user_input_lower.startswith(prefix):
                remainder = user_input_lower[len(prefix):].strip()
                remainder = remainder.removeprefix('the ').strip()
                if remainder == detected_app:
                    result = window_control("screenshot", detected_app)
                    _speak(result)
                    _log_shortcircuit(f"screenshot of {detected_app}", retrieval_start_time)
                    return True
                break

    # --- Brightness ---
    if 'brightness' in user_input_lower or 'backlight' in user_input_lower:
        target = "keyboard" if any(w in user_input_lower for w in ('keyboard', 'kbd', 'keys')) else "screen"
        level = None
        if any(w in user_input_lower for w in ('up', 'increase', 'brighter', 'raise')):
            level = "up"
        elif any(w in user_input_lower for w in ('down', 'decrease', 'dimmer', 'lower', 'dim')):
            level = "down"
        elif 'max' in user_input_lower or 'full' in user_input_lower:
            level = "max"
        elif 'min' in user_input_lower or ('off' in user_input_lower and target == "keyboard"):
            level = "min"
        else:
            pct_match = re.search(r'(\d+)\s*%', user_input_lower)
            if pct_match:
                level = f"{pct_match.group(1)}%"
        if level:
            result = _mcp_client.call_tool("set_brightness", {"target": target, "level": level})
            _speak(result)
            _log_shortcircuit(f"{target} brightness {level}", retrieval_start_time)
            return True

    # --- Power profile ---
    if 'power mode' in user_input_lower or 'power profile' in user_input_lower or 'power saver' in user_input_lower:
        if any(w in user_input_lower for w in ('what', 'current', 'which', 'get', 'check')):
            result = _mcp_client.call_tool("get_power_profile", {})
        elif 'performance' in user_input_lower:
            result = _mcp_client.call_tool("set_power_profile", {"profile": "performance"})
        elif 'balanced' in user_input_lower:
            result = _mcp_client.call_tool("set_power_profile", {"profile": "balanced"})
        elif any(w in user_input_lower for w in ('power saver', 'power-saver', 'saving')):
            result = _mcp_client.call_tool("set_power_profile", {"profile": "power-saver"})
        else:
            result = _mcp_client.call_tool("get_power_profile", {})
        _speak(result)
        _log_shortcircuit("power profile", retrieval_start_time)
        return True

    # --- Lock screen ---
    if any(p in user_input_lower for p in ('lock screen', 'lock the screen', 'lock my screen')):
        result = _mcp_client.call_tool("lock_screen", {})
        _speak(result)
        _log_shortcircuit("lock screen", retrieval_start_time)
        return True

    # --- Power actions (with confirmation) ---
    _power_actions = {
        'suspend': ('suspend', 'sleep', 'hibernate'),
        'restart': ('restart', 'reboot'),
        'shutdown': ('shut down', 'shutdown', 'power off', 'poweroff', 'turn off the computer'),
        'logout': ('log out', 'logout', 'sign out', 'sign off'),
    }
    power_matched = None
    for action_name, phrases in _power_actions.items():
        if any(p in user_input_lower for p in phrases):
            power_matched = action_name
            break
    if power_matched:
        _power_confirmations = {
            'suspend': "Are you sure you want to put the computer to sleep?",
            'restart': "Are you sure you want to restart the computer?",
            'shutdown': "Are you sure you want to shut down the computer?",
            'logout': "Are you sure you want to log out of your desktop session?",
        }
        _speak(_power_confirmations[power_matched])
        confirmation = _listen_and_transcribe()
        if confirmation and any(w in confirmation.lower() for w in ('yes', 'yeah', 'yep', 'sure', 'do it', 'confirm', 'go ahead')):
            result = _mcp_client.call_tool("power_action", {"action": power_matched})
            _speak(result)
        else:
            _speak("Canceled.")
        _log_shortcircuit(f"power action {power_matched}", retrieval_start_time)
        return True

    # --- Install/uninstall apps ---
    _install_verbs = ('install ', 'uninstall ', 'remove app ')
    install_matched = None
    install_query = None
    for iv in _install_verbs:
        if user_input_lower.startswith(iv):
            install_matched = iv.strip()
            install_query = user_input_lower[len(iv):].strip().strip('.,!').strip()
            break
    if install_matched and install_query:
        is_uninstall = install_matched in ('uninstall', 'remove app')
        action_word = "uninstall" if is_uninstall else "install"
        log_and_print(f"[ROUTING] Short-circuit: {action_word} '{install_query}'")

        _speak(f"Searching for {install_query}.")
        results = search_apps(install_query)

        _confirm_words = ('yes', 'yeah', 'yep', 'sure', 'do it', 'confirm', 'go ahead')
        _cancel_words = ('cancel', 'skip', 'nevermind', 'never mind', 'no', 'nope', 'stop', 'forget it', 'none')

        def _do_install(name, app_id, source):
            _speak(f"{'Uninstalling' if is_uninstall else 'Installing'} {name}. This may take a moment.")
            r = run_uninstall(app_id, source) if is_uninstall else run_install(app_id, source)
            _speak(r)

        def _confirm_and_install(name, app_id, source):
            _speak(f"Found {name}. Should I {action_word} it?")
            confirmation = _listen_and_transcribe()
            if confirmation and any(w in confirmation.lower() for w in _confirm_words):
                _do_install(name, app_id, source)
            else:
                _speak("Canceled.")

        if not results:
            _speak(f"No apps found matching {install_query}.")
        elif len(results) == 1:
            name, app_id, source = results[0]
            _confirm_and_install(name, app_id, source)
        else:
            exact = None
            for name, app_id, source in results:
                if name.lower() == install_query:
                    exact = (name, app_id, source)
                    break
            if exact:
                _confirm_and_install(*exact)
            else:
                names = [name for name, _, _ in results[:5]]
                names_str = ", ".join(names[:-1]) + f", and {names[-1]}" if len(names) > 1 else names[0]
                _speak(f"I found {names_str}. Which one?")
                choice = _listen_and_transcribe()
                if not choice:
                    _speak("No response heard. Canceled.")
                elif any(w in choice.lower() for w in _cancel_words):
                    _speak("Canceled.")
                else:
                    choice_lower = choice.lower().strip().strip('.,!').strip()
                    matched = None
                    for name, app_id, source in results:
                        if name.lower() in choice_lower or choice_lower in name.lower():
                            matched = (name, app_id, source)
                            break
                    if matched:
                        name, app_id, source = matched
                        _confirm_and_install(name, app_id, source)
                    else:
                        _speak(f"Could not find {choice} in the results. Canceled.")

        _log_shortcircuit(f"{action_word} app", retrieval_start_time)
        return True

    return False
