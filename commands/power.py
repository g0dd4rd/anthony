from commands import step, _mcp_client, _speak, _listen
from utils import log_and_print

_CONFIRM_WORDS = ('yes', 'yeah', 'yep', 'sure', 'do it', 'confirm', 'go ahead')


def _confirm_and_execute(prompt, action):
    _speak(prompt)
    confirmation = _listen()
    if confirmation and any(w in confirmation.lower() for w in _CONFIRM_WORDS):
        result = _mcp_client.call_tool("power_action", {"action": action})
        return result
    return "Canceled."


# --- Lock screen ---

@step('lock screen', 'lock the screen', 'lock my screen',
      category='power', help_text='Lock the screen')
def handle_lock(context):
    return _mcp_client.call_tool("lock_screen", {})


# --- Power actions (with confirmation) ---

@step('suspend', 'sleep', 'hibernate',
      category='power', requires_confirmation=True,
      help_text='Put the computer to sleep')
def handle_suspend(context):
    return _confirm_and_execute(
        "Are you sure you want to put the computer to sleep?", "suspend")


@step('restart', 'reboot',
      category='power', requires_confirmation=True,
      help_text='Restart the computer')
def handle_restart(context):
    return _confirm_and_execute(
        "Are you sure you want to restart the computer?", "restart")


@step('shut down', 'shutdown', 'power off', 'turn off the computer',
      category='power', requires_confirmation=True,
      help_text='Shut down the computer')
def handle_shutdown(context):
    return _confirm_and_execute(
        "Are you sure you want to shut down the computer?", "shutdown")


@step('log out', 'logout', 'sign out', 'sign off',
      category='power', requires_confirmation=True,
      help_text='Log out of the desktop session')
def handle_logout(context):
    return _confirm_and_execute(
        "Are you sure you want to log out of your desktop session?", "logout")
