import re
import subprocess
from datetime import datetime

from commands import _get_installed_gui_apps, _mcp_client, step


def _is_dnd_enabled():
    try:
        result = subprocess.run(
            ["gsettings", "get", "org.gnome.desktop.notifications", "show-banners"],
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip() == "false"
    except Exception:
        return False


def _dnd_warning():
    return "Warning: Do Not Disturb is enabled. The notification may not be shown. "


# --- Date/time ---


@step(
    "what time is it",
    "what's the time",
    "what is the time",
    "current time",
    "tell me the time",
    category="system",
    help_text="Get the current time",
)
def handle_time(context):
    return datetime.now().strftime("It's %I:%M %p.")


@step(
    "what date is it",
    "what's the date",
    "what is the date",
    "current date",
    "tell me the date",
    category="system",
    help_text="Get the current date",
)
def handle_date(context):
    return datetime.now().strftime("It's %A, %B %-d.")


@step(
    "what day is it",
    "what's the day",
    "what is the day",
    category="system",
    help_text="Get the current day of the week",
)
def handle_day(context):
    return datetime.now().strftime("It's %A.")


# --- Battery ---


@step(
    "battery status",
    "what's my battery level",
    "battery level",
    "how much battery",
    "battery",
    "charge level",
    "power level",
    "how much charge",
    "how much power",
    category="system",
    help_text="Check battery status",
)
def handle_battery(context):
    return _mcp_client.call_tool("get_battery_status", {})


# --- Notifications ---


@step(
    "remind me in {delay} to {summary}",
    "remind me in {delay} about {summary}",
    "alert me in {delay} to {summary}",
    "remind me to {summary} in {delay}",
    category="system",
    help_text="Set a reminder notification",
)
def handle_reminder(context, delay, summary):
    prefix = _dnd_warning() if _is_dnd_enabled() else ""
    result = _mcp_client.call_tool(
        "send_notification", {"summary": summary, "body": "", "delay": delay}
    )
    return prefix + result


@step(
    "remind me in {delay}",
    "alert me in {delay}",
    category="system",
    help_text="Set a reminder with default message",
)
def handle_reminder_simple(context, delay):
    prefix = _dnd_warning() if _is_dnd_enabled() else ""
    result = _mcp_client.call_tool(
        "send_notification", {"summary": "Reminder", "body": "", "delay": delay}
    )
    return prefix + result


@step(
    "send notification {summary}",
    "notify {summary}",
    "send me a notification saying {summary}",
    "notify me {summary}",
    category="system",
    help_text="Send a desktop notification",
)
def handle_notification(context, summary):
    prefix = _dnd_warning() if _is_dnd_enabled() else ""
    result = _mcp_client.call_tool(
        "send_notification", {"summary": summary, "body": "", "delay": ""}
    )
    return prefix + result


@step(
    "send notification",
    "send a notification",
    category="system",
    help_text="Send a default notification",
)
def handle_notification_simple(context):
    prefix = _dnd_warning() if _is_dnd_enabled() else ""
    result = _mcp_client.call_tool(
        "send_notification", {"summary": "Notification from Anthony", "body": "", "delay": ""}
    )
    return prefix + result


# --- Cleanup ---


@step(
    "clean up screenshots",
    "cleanup screenshots",
    "delete screenshots",
    "remove screenshots",
    category="system",
    help_text="Move temporary screenshots to trash",
)
def handle_cleanup(context):
    result = _mcp_client.call_tool("cleanup_screenshots", {})
    match = re.search(r"Removed (\d+)", result)
    if match:
        return f"Moved {match.group(1)} screenshots from Pictures/Screenshots to trash"
    return result


# --- List apps ---


@step(
    "list installed applications",
    "what apps are installed",
    "list installed apps",
    "show installed applications",
    category="system",
    help_text="List all installed GUI applications",
)
def handle_list_apps(context):
    try:
        app_data = _get_installed_gui_apps()
        count = app_data["count"]
        samples = app_data["samples"]
        if count == 0:
            return "No applications found."
        if samples:
            return f"Found {count} installed applications including {', '.join(samples)}, and more."
        return f"Found {count} installed applications."
    except Exception as e:
        return f"Error listing applications: {e}"
