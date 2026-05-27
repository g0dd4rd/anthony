import json
import re

from commands import step, _mcp_client, _speak
from utils import log_and_print


def _audio_call(tool, args):
    return _mcp_client.call_tool(tool, args)


def _get_volume_status():
    try:
        return json.loads(_audio_call("get_volume", {}))
    except Exception:
        return None


def _get_media_status():
    try:
        return json.loads(_audio_call("get_media_status", {}))
    except Exception:
        return None


# --- Mute / Unmute ---

@step('mute', 'mute audio', 'mute the sound', 'mute sound',
      category='audio', help_text='Mute system audio')
def handle_mute(context):
    _audio_call("mute_volume", {"mute": True})
    status = _get_volume_status()
    if status and status.get('muted'):
        return "Muted"
    return "Muted, but couldn't confirm"


@step('unmute', 'unmute audio', 'unmute the sound', 'unmute sound',
      category='audio', help_text='Unmute system audio')
def handle_unmute(context):
    _audio_call("mute_volume", {"mute": False})
    status = _get_volume_status()
    if status and not status.get('muted'):
        return "Unmuted"
    return "Unmuted, but couldn't confirm"


# --- Volume ---

@step('volume up', 'turn up', 'louder', 'raise the volume', 'raise volume',
      'increase volume', 'increase the volume',
      category='audio', help_text='Increase volume by 10%')
def handle_volume_up(context):
    _audio_call("set_volume", {"volume": 10, "relative": True})
    status = _get_volume_status()
    if status:
        return f"Volume set to {status['volume']}%"
    return "Volume increased"


@step('volume down', 'turn down', 'quieter', 'lower the volume', 'lower volume',
      'decrease volume', 'decrease the volume',
      category='audio', help_text='Decrease volume by 10%')
def handle_volume_down(context):
    _audio_call("set_volume", {"volume": -10, "relative": True})
    status = _get_volume_status()
    if status:
        return f"Volume set to {status['volume']}%"
    return "Volume decreased"


@step('set volume to {level:d}', 'volume {level:d}',
      'set volume to {level:d} percent', 'volume {level:d} percent',
      category='audio', help_text='Set volume to a specific level (0-100)')
def handle_set_volume(context, level):
    _audio_call("set_volume", {"volume": level, "relative": False})
    status = _get_volume_status()
    if status:
        return f"Volume set to {status['volume']}%"
    return f"Volume set to {level}%"


# --- Media playback ---

@step('play', 'play music', 'resume', 'resume playback',
      category='audio', help_text='Play or resume media')
def handle_play(context):
    _audio_call("media_control", {"action": "play"})
    status = _get_media_status()
    if status and not status.get('error'):
        title = status.get('title', '')
        if title and status.get('status') == 'Playing':
            return f"Playing {title}"
    return "Playing"


@step('pause', 'pause music', 'pause playback',
      category='audio', help_text='Pause media')
def handle_pause(context):
    _audio_call("media_control", {"action": "pause"})
    status = _get_media_status()
    if status and not status.get('error'):
        title = status.get('title', '')
        if title:
            return f"Paused {title}"
    return "Paused"


@step('play pause', 'toggle playback',
      category='audio', help_text='Toggle play/pause')
def handle_play_pause(context):
    _audio_call("media_control", {"action": "play-pause"})
    status = _get_media_status()
    if status and not status.get('error'):
        return status.get('status', 'Toggled playback')
    return "Toggled playback"


@step('stop', 'stop music', 'stop playback', 'stop playing',
      category='audio', help_text='Stop media playback')
def handle_stop(context):
    _audio_call("media_control", {"action": "stop"})
    return "Stopped playback"


@step('next', 'next song', 'next track', 'skip',
      category='audio', help_text='Skip to next track')
def handle_next(context):
    _audio_call("media_control", {"action": "next"})
    status = _get_media_status()
    if status and not status.get('error'):
        title = status.get('title', '')
        if title:
            return f"Skipped to {title}"
    return "Next track"


@step('previous', 'previous song', 'previous track', 'go back',
      category='audio', help_text='Go to previous track')
def handle_previous(context):
    _audio_call("media_control", {"action": "previous"})
    status = _get_media_status()
    if status and not status.get('error'):
        title = status.get('title', '')
        if title:
            return f"Back to {title}"
    return "Previous track"


# --- Mute/unmute browser tab ---

@step('mute tab', 'mute the tab', 'mute this tab',
      'silence tab', 'silence the tab', 'silence this tab',
      category='audio', help_text='Mute the current browser tab')
def handle_mute_tab(context):
    _mcp_client.call_tool("key_combo", {"keys": "ctrl+m"})
    return "Muted tab"


@step('unmute tab', 'unmute the tab', 'unmute this tab',
      category='audio', help_text='Unmute the current browser tab')
def handle_unmute_tab(context):
    _mcp_client.call_tool("key_combo", {"keys": "ctrl+m"})
    return "Unmuted tab"
