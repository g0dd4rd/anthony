import json

from commands import _mcp_client, step


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
