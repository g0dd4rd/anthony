import time

from parse import parse

from utils import log_and_print

_mcp_client = None
_speak = None
_listen = None
_smart_match_window = None
_get_friendly_app_name = None
_dialog_handler = None
_check_automation_health = None
_get_installed_gui_apps = None


def init(
    mcp_client,
    speak_fn,
    listen_fn,
    smart_match_fn,
    friendly_name_fn,
    dialog_handler,
    check_health_fn,
    get_installed_gui_apps_fn,
):
    global _mcp_client, _speak, _listen, _smart_match_window
    global _get_friendly_app_name, _dialog_handler
    global _check_automation_health, _get_installed_gui_apps
    _mcp_client = mcp_client
    _speak = speak_fn
    _listen = listen_fn
    _smart_match_window = smart_match_fn
    _get_friendly_app_name = friendly_name_fn
    _dialog_handler = dialog_handler
    _check_automation_health = check_health_fn
    _get_installed_gui_apps = get_installed_gui_apps_fn

    from commands import (
        apps,
        audio,
        brightness,
        help,
        input,
        power,
        search,
        settings,
        shortcuts,
        system,
        vision,
        window,
        workspace,
    )


class CommandRegistry:
    def __init__(self):
        self.entries = []

    def step(self, *patterns, category, help_text="", requires_confirmation=False, uses_llm=False):
        def decorator(fn):
            self.entries.append(
                {
                    "patterns": patterns,
                    "handler": fn,
                    "name": fn.__name__,
                    "category": category,
                    "help_text": help_text,
                    "requires_confirmation": requires_confirmation,
                    "uses_llm": uses_llm,
                }
            )
            return fn

        return decorator

    def match(self, text):
        text_clean = text.strip().rstrip(".!?,;")
        for entry in self.entries:
            for pattern in entry["patterns"]:
                result = parse(pattern, text_clean, case_sensitive=False)
                if result:
                    return entry, result.named
        return None, {}

    def get_categories(self):
        categories = {}
        for entry in self.entries:
            cat = entry["category"]
            if cat not in categories:
                categories[cat] = []
            categories[cat].append(entry)
        return categories


registry = CommandRegistry()
step = registry.step
