import re

from commands import step, _mcp_client
from utils import log_and_print


# --- Screen brightness ---

@step('increase brightness', 'brightness up', 'brighter',
      category='brightness', help_text='Increase screen brightness')
def handle_brightness_up(context):
    return _mcp_client.call_tool("set_brightness", {"target": "screen", "level": "up"})


@step('decrease brightness', 'brightness down', 'dimmer', 'dim',
      category='brightness', help_text='Decrease screen brightness')
def handle_brightness_down(context):
    return _mcp_client.call_tool("set_brightness", {"target": "screen", "level": "down"})


@step('max brightness', 'full brightness',
      category='brightness', help_text='Set brightness to maximum')
def handle_brightness_max(context):
    return _mcp_client.call_tool("set_brightness", {"target": "screen", "level": "max"})


@step('min brightness',
      category='brightness', help_text='Set brightness to minimum')
def handle_brightness_min(context):
    return _mcp_client.call_tool("set_brightness", {"target": "screen", "level": "min"})


@step('set brightness to {level}', 'brightness {level}',
      category='brightness', help_text='Set brightness to a percentage (e.g., 50%)')
def handle_brightness_set(context, level):
    level_str = str(level).strip()
    if not level_str.endswith('%'):
        level_str = f"{level_str}%"
    return _mcp_client.call_tool("set_brightness", {"target": "screen", "level": level_str})


# --- Keyboard backlight ---

@step('keyboard brightness up', 'keyboard backlight up',
      category='brightness', help_text='Increase keyboard backlight')
def handle_kbd_brightness_up(context):
    return _mcp_client.call_tool("set_brightness", {"target": "keyboard", "level": "up"})


@step('keyboard brightness down', 'keyboard backlight down',
      category='brightness', help_text='Decrease keyboard backlight')
def handle_kbd_brightness_down(context):
    return _mcp_client.call_tool("set_brightness", {"target": "keyboard", "level": "down"})


@step('keyboard backlight off', 'keyboard brightness off',
      category='brightness', help_text='Turn off keyboard backlight')
def handle_kbd_brightness_off(context):
    return _mcp_client.call_tool("set_brightness", {"target": "keyboard", "level": "min"})


# --- Power profile ---

@step('what power mode', 'current power mode', 'check power mode',
      'what power profile', 'get power profile',
      category='brightness', help_text='Check current power profile')
def handle_get_power_profile(context):
    return _mcp_client.call_tool("get_power_profile", {})


@step('set power mode to {profile}', 'power mode {profile}',
      'set power profile to {profile}',
      category='brightness', help_text='Set power profile (performance, balanced, power-saver)')
def handle_set_power_profile(context, profile):
    profile_lower = profile.lower().strip()
    profile_map = {
        'performance': 'performance',
        'balanced': 'balanced',
        'power saver': 'power-saver',
        'power-saver': 'power-saver',
        'saving': 'power-saver',
    }
    mapped = profile_map.get(profile_lower, profile_lower)
    return _mcp_client.call_tool("set_power_profile", {"profile": mapped})
