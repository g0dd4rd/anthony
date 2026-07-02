import os
import re
import subprocess

from config.aliases import APP_SHORTCUT_ALIASES
from utils import log_and_print

# ----------------------------------------
# Dependency injection (set via init())
# ----------------------------------------
_mcp_client = None
_get_installed_gui_apps = None


def init(mcp_client, get_installed_gui_apps_fn):
    global _mcp_client, _get_installed_gui_apps
    _mcp_client = mcp_client
    _get_installed_gui_apps = get_installed_gui_apps_fn


def get_datetime() -> str:
    """Return the current date, time, and day of week."""
    import locale
    from datetime import datetime

    locale.setlocale(locale.LC_TIME, "")
    now = datetime.now()
    return now.strftime("It is %c.")


def list_installed_applications() -> str:
    """Lists all installed GUI applications on the system."""
    log_and_print("\n[SYSTEM] Scanning for installed applications...")
    try:
        app_data = _get_installed_gui_apps()
        app_count = app_data["count"]
        samples = app_data["samples"]

        if app_count == 0:
            return "No applications found."

        if samples:
            return f"Found {app_count} installed applications including {', '.join(samples)}, and more."
        else:
            return f"Found {app_count} installed applications."
    except Exception as e:
        return f"Error listing applications: {str(e)}"


def send_notification(summary: str, body: str = "", delay: str = "") -> str:
    """Send a desktop notification."""
    log_and_print(f"\n[SYSTEM] Sending notification: {summary}")
    try:
        return _mcp_client.call_tool(
            "send_notification", {"summary": summary, "body": body, "delay": delay}
        )
    except Exception as e:
        return f"Error sending notification: {str(e)}"


def cleanup_screenshots() -> str:
    """Clean up temporary screenshot files by moving them to trash."""
    log_and_print("\n[SYSTEM] Cleaning up screenshots...")
    try:
        result = _mcp_client.call_tool("cleanup_screenshots", {})
        if result.startswith("Removed"):
            match = re.search(r"Removed (\d+)", result)
            if match:
                return f"Moved {match.group(1)} screenshots from Pictures/Screenshots to trash"
            else:
                return "Moved screenshots from Pictures/Screenshots to trash"
        return result
    except Exception as e:
        return f"Error cleaning up: {str(e)}"


def search_apps(query: str) -> list:
    """Search for apps across flatpak and dnf. Returns list of (name, app_id, source) tuples."""
    results = []
    seen = set()
    fp_queries = [query]
    if " " in query:
        fp_queries.append(query.split()[0])
    for fp_query in fp_queries:
        try:
            fp = subprocess.run(
                ["flatpak", "search", "--columns=name,application,remotes", fp_query],
                capture_output=True,
                text=True,
                timeout=15,
            )
            if fp.returncode == 0 and fp.stdout.strip():
                found_any = False
                for line in fp.stdout.strip().split("\n")[:5]:
                    parts = line.split("\t")
                    if len(parts) >= 3:
                        name = parts[0].strip()
                        app_id = parts[1].strip()
                        remotes = parts[2].strip()
                        remote = "flathub" if "flathub" in remotes else remotes.split(",")[0]
                        if name.lower() not in seen:
                            seen.add(name.lower())
                            results.append((name, app_id, remote))
                            found_any = True
                if found_any:
                    break
        except FileNotFoundError:
            break
        except Exception as e:
            log_and_print(f"[SYSTEM] flatpak search error: {e}", level="warning")
            break
    try:
        dnf = subprocess.run(["dnf", "search", query], capture_output=True, text=True, timeout=15)
        if dnf.returncode == 0 and dnf.stdout.strip():
            for line in dnf.stdout.strip().split("\n"):
                if len(results) >= 5:
                    break
                if not (".x86_64" in line or ".noarch" in line or ".i686" in line):
                    continue
                pkg_name = line.split(".")[0].strip()
                if pkg_name.lower() not in seen:
                    seen.add(pkg_name.lower())
                    results.append((pkg_name, pkg_name, "dnf"))
    except FileNotFoundError:
        pass
    except Exception as e:
        log_and_print(f"[SYSTEM] dnf search error: {e}", level="warning")
    return results


def run_install(app_id: str, source: str = "") -> str:
    """Install an app by its flatpak ID or RPM package name."""
    is_flatpak = source != "dnf"
    try:
        if is_flatpak:
            cmd = ["flatpak", "install", "-y"]
            if source and source != "flatpak":
                cmd.append(source)
            cmd.append(app_id)
        else:
            has_sudo = (
                subprocess.run(["sudo", "-n", "true"], capture_output=True, timeout=5).returncode
                == 0
            )
            if not has_sudo:
                return "Installing RPM packages requires sudo. Please type your sudo password in the terminal, then try again."
            cmd = ["sudo", "dnf", "install", "-y", app_id]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if result.returncode == 0:
            return f"Successfully installed {app_id}."
        else:
            stderr = result.stderr.strip()
            if (
                "already installed" in stderr.lower()
                or "already installed" in result.stdout.lower()
            ):
                return f"{app_id} is already installed."
            return f"Installation failed: {stderr}"
    except subprocess.TimeoutExpired:
        return "Installation timed out after 5 minutes."
    except Exception as e:
        return f"Error installing: {e}"


def run_uninstall(app_id: str, source: str = "") -> str:
    """Uninstall an app by its flatpak ID or RPM package name."""
    is_flatpak = source != "dnf"
    try:
        if is_flatpak:
            cmd = ["flatpak", "uninstall", "-y", app_id]
        else:
            has_sudo = (
                subprocess.run(["sudo", "-n", "true"], capture_output=True, timeout=5).returncode
                == 0
            )
            if not has_sudo:
                return "Uninstalling RPM packages requires sudo. Please type your sudo password in the terminal, then try again."
            cmd = ["sudo", "dnf", "remove", "-y", app_id]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if result.returncode == 0:
            return f"Successfully uninstalled {app_id}."
        else:
            return f"Uninstall failed: {result.stderr.strip()}"
    except Exception as e:
        return f"Error uninstalling: {e}"


def get_app_shortcuts(app_name: str) -> str:
    """Look up keyboard shortcuts for an application."""
    import json as _json

    from shortcuts.gnome_shortcuts import get_shortcuts_for_app

    app_lower = app_name.lower().strip()
    shortcuts = {}

    shortcuts_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "shortcuts"
    )
    json_path = os.path.join(shortcuts_dir, "app_shortcuts.json")
    try:
        with open(json_path) as f:
            curated = _json.load(f)
        lookup_key = APP_SHORTCUT_ALIASES.get(app_lower, app_lower)
        if lookup_key in curated:
            shortcuts.update(curated[lookup_key])
    except Exception:
        pass

    gs_shortcuts = get_shortcuts_for_app(app_name)
    if gs_shortcuts:
        shortcuts.update(gs_shortcuts)

    skills = shortcuts.pop("_skills", None)
    shortcuts = {k: v for k, v in shortcuts.items() if not k.startswith("_")}

    if not shortcuts:
        return f"No shortcuts found for '{app_name}'"

    lines = [f"Shortcuts for {app_name}:"]
    for action, shortcut in shortcuts.items():
        lines.append(f"- {action}: {shortcut}")

    if skills:
        lines.append("")
        lines.append("Skills (execute steps in order, look up shortcuts above):")
        for skill_name, steps in skills.items():
            steps_str = " -> ".join(steps)
            lines.append(f"- {skill_name}: {steps_str}")

    return "\n".join(lines)
