import json

from commands import _get_friendly_app_name, _mcp_client, _smart_match_window, step


def _list_windows():
    result = _mcp_client.call_tool("list_windows", {})
    if result.startswith("Error"):
        return None
    return json.loads(result)


def _get_focused_window():
    windows = _list_windows()
    if not windows:
        return None
    return next((w for w in windows if w.get("focused", False)), None)


def _find_window(app_name):
    windows = _list_windows()
    if not windows:
        return None
    return _smart_match_window(app_name, windows)


@step(
    "list workspaces",
    "show workspaces",
    "how many workspaces",
    category="workspace",
    help_text="List virtual workspaces",
)
def handle_list_workspaces(context):
    result = _mcp_client.call_tool("list_workspaces", {})
    if result.startswith("Error"):
        return result
    try:
        workspaces = json.loads(result)
        if not workspaces:
            return "No workspaces found"
        active = next((ws for ws in workspaces if ws.get("active", False)), None)
        active_idx = active.get("index", 0) if active else 0
        total = len(workspaces)
        return (
            f"You have {total} workspace{'s' if total > 1 else ''}."
            f" You are on workspace {active_idx + 1}."
        )
    except json.JSONDecodeError:
        return result


@step(
    "switch to workspace {index:d}",
    "go to workspace {index:d}",
    "workspace {index:d}",
    category="workspace",
    help_text="Switch to a workspace by number (1-based)",
)
def handle_switch_workspace(context, index):
    zero_based = index - 1
    result = _mcp_client.call_tool("activate_workspace", {"index": zero_based})
    if result.startswith("Error"):
        return result
    try:
        ws_result = _mcp_client.call_tool("list_workspaces", {})
        workspaces = json.loads(ws_result)
        active = next((ws for ws in workspaces if ws.get("active")), None)
        if active and active.get("index") == zero_based:
            return f"Switched to workspace {index}"
        elif active:
            return (
                f"Tried to switch to workspace {index}"
                f" but you're on workspace {active['index'] + 1}"
            )
    except Exception:
        pass
    return f"Switched to workspace {index}, but couldn't confirm"


def _move_window_to_workspace(target, workspace_index):
    """Move a window to a workspace (0-based index). Returns response string."""
    window_id = target["id"]
    friendly = _get_friendly_app_name(target.get("wmClass", ""))
    result = _mcp_client.call_tool(
        "move_window_to_workspace",
        {"window_id": window_id, "workspace_index": workspace_index},
    )
    if result.startswith("Error"):
        return result
    return f"Moved {friendly} to workspace {workspace_index + 1}"


@step(
    "move {app} to workspace {index:d}",
    "send {app} to workspace {index:d}",
    category="workspace",
    help_text="Move an application window to a workspace",
)
def handle_move_to_workspace(context, app, index):
    target = _find_window(app)
    if not target:
        return f"No window found matching '{app}'"
    return _move_window_to_workspace(target, index - 1)


@step(
    "move to workspace {index:d}",
    "move window to workspace {index:d}",
    "send to workspace {index:d}",
    category="workspace",
    help_text="Move the focused window to a workspace",
)
def handle_move_focused_to_workspace(context, index):
    target = _get_focused_window()
    if not target:
        return "No focused window found"
    return _move_window_to_workspace(target, index - 1)


_DIRECTIONS = {"next": 1, "right": 1, "previous": -1, "left": -1}


def _move_relative_workspace(target, direction):
    """Move a window to the next or previous workspace."""
    delta = _DIRECTIONS.get(direction.lower())
    if delta is None:
        return f"Unknown direction '{direction}'"
    current_ws = target.get("workspace", 0)
    if delta > 0:
        try:
            ws_result = _mcp_client.call_tool("list_workspaces", {})
            workspaces = json.loads(ws_result)
            total = len(workspaces)
        except Exception:
            total = current_ws + 2
        if current_ws >= total - 1:
            return "Already on the last workspace"
    else:
        if current_ws <= 0:
            return "Already on the first workspace"
    return _move_window_to_workspace(target, current_ws + delta)


@step(
    "move {app} to {direction} workspace",
    "move {app} to workspace {direction}",
    category="workspace",
    help_text="Move an application to the next or previous workspace",
)
def handle_move_app_to_relative_workspace(context, app, direction):
    target = _find_window(app)
    if not target:
        return f"No window found matching '{app}'"
    return _move_relative_workspace(target, direction)


@step(
    "move to {direction} workspace",
    "move window to {direction} workspace",
    "move to workspace {direction}",
    category="workspace",
    help_text="Move the focused window to the next or previous workspace",
)
def handle_move_to_relative_workspace(context, direction):
    target = _get_focused_window()
    if not target:
        return "No focused window found"
    return _move_relative_workspace(target, direction)
