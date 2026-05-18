import os
import re
import subprocess

from utils import log_and_print
from config.aliases import APP_SHORTCUT_ALIASES

# ----------------------------------------
# Dependency injection (set via init())
# ----------------------------------------
_mcp_client = None
_get_installed_gui_apps = None


def init(mcp_client, get_installed_gui_apps_fn):
    global _mcp_client, _get_installed_gui_apps
    _mcp_client = mcp_client
    _get_installed_gui_apps = get_installed_gui_apps_fn


def get_battery_status() -> str:
    """Return battery percentage, state, and time remaining."""
    try:
        result = subprocess.run(
            ["upower", "-i", "/org/freedesktop/UPower/devices/battery_BAT0"],
            capture_output=True, text=True, check=True
        )
        info = {}
        for line in result.stdout.splitlines():
            line = line.strip()
            if line.startswith("percentage:"):
                info["percentage"] = line.split(":")[-1].strip()
            elif line.startswith("state:"):
                info["state"] = line.split(":")[-1].strip()
            elif line.startswith("time to empty:"):
                info["remaining"] = line.split(":")[-1].strip()
            elif line.startswith("time to full:"):
                info["remaining"] = line.split(":")[-1].strip()

        pct = info.get("percentage", "unknown")
        state = info.get("state", "unknown")
        remaining = info.get("remaining")

        msg = f"Battery is at {pct}, {state}"
        if remaining:
            msg += f", {remaining} remaining"
        return msg + "."
    except Exception:
        return "Could not read battery status."


def set_brightness(target: str, level: str) -> str:
    """Set screen or keyboard backlight brightness."""
    try:
        if target == "keyboard":
            device_flag = ["--device", "tpacpi::kbd_backlight"]
        else:
            device_flag = []

        if level in ("up", "increase"):
            cmd = ["brightnessctl", *device_flag, "set", "+10%"]
        elif level in ("down", "decrease"):
            cmd = ["brightnessctl", *device_flag, "set", "10%-"]
        elif level.endswith("%"):
            cmd = ["brightnessctl", *device_flag, "set", level]
        elif level == "max":
            cmd = ["brightnessctl", *device_flag, "set", "100%"]
        elif level in ("min", "off") and target == "keyboard":
            cmd = ["brightnessctl", *device_flag, "set", "0"]
        elif level == "min":
            cmd = ["brightnessctl", *device_flag, "set", "5%"]
        else:
            cmd = ["brightnessctl", *device_flag, "set", level]

        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        for line in result.stdout.splitlines():
            if "Current brightness" in line:
                pct_match = re.search(r'\((\d+%)\)', line)
                if pct_match:
                    label = "Keyboard backlight" if target == "keyboard" else "Brightness"
                    return f"{label} set to {pct_match.group(1)}."
                return line.strip()
        return f"{'Keyboard backlight' if target == 'keyboard' else 'Brightness'} set to {level}."
    except FileNotFoundError:
        return "brightnessctl is not installed."
    except Exception as e:
        return f"Error setting brightness: {e}"


def get_power_profile() -> str:
    """Get the current power profile."""
    try:
        result = subprocess.run(
            ["gdbus", "call", "--system",
             "--dest", "net.hadess.PowerProfiles",
             "--object-path", "/net/hadess/PowerProfiles",
             "--method", "org.freedesktop.DBus.Properties.Get",
             "net.hadess.PowerProfiles", "ActiveProfile"],
            capture_output=True, text=True, check=True
        )
        profile = result.stdout.strip().strip("(<'>),")
        return f"Power mode is {profile}."
    except Exception as e:
        return f"Error reading power profile: {e}"


def set_power_profile(profile: str) -> str:
    """Set power profile: performance, balanced, or power-saver."""
    profile_map = {
        "performance": "performance",
        "balanced": "balanced",
        "power saver": "power-saver",
        "power-saver": "power-saver",
        "powersaver": "power-saver",
    }
    profile_name = profile_map.get(profile.lower())
    if not profile_name:
        return f"Unknown profile: {profile}. Options: performance, balanced, power-saver."
    try:
        subprocess.run(
            ["gdbus", "call", "--system",
             "--dest", "net.hadess.PowerProfiles",
             "--object-path", "/net/hadess/PowerProfiles",
             "--method", "org.freedesktop.DBus.Properties.Set",
             "net.hadess.PowerProfiles", "ActiveProfile",
             f"<'{profile_name}'>"],
            capture_output=True, text=True, check=True
        )
        return f"Power mode set to {profile_name}."
    except Exception as e:
        return f"Error setting power profile: {e}"


def lock_screen() -> str:
    """Lock the screen."""
    try:
        subprocess.run(["loginctl", "lock-session"], check=True)
        return "Screen locked."
    except Exception as e:
        return f"Error locking screen: {e}"


def power_action(action: str) -> str:
    """Execute a power action: suspend, restart, shutdown, or logout."""
    if action == "suspend":
        subprocess.run(["systemctl", "suspend"], check=False)
        return "Suspending."
    elif action == "restart":
        subprocess.run(["systemctl", "reboot"], check=False)
        return "Restarting."
    elif action == "shutdown":
        subprocess.run(["systemctl", "poweroff"], check=False)
        return "Shutting down."
    elif action == "logout":
        subprocess.run(["gnome-session-quit", "--logout", "--no-prompt"], check=False)
        return "Logging out."
    else:
        return f"Unknown power action: {action}"


def get_datetime() -> str:
    """Return the current date, time, and day of week."""
    from datetime import datetime
    import locale
    locale.setlocale(locale.LC_TIME, '')
    now = datetime.now()
    return now.strftime("It is %c.")


def list_installed_applications() -> str:
    """Lists all installed GUI applications on the system."""
    log_and_print(f"\n[SYSTEM] Scanning for installed applications...")
    try:
        app_data = _get_installed_gui_apps()
        app_count = app_data['count']
        samples = app_data['samples']

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
        return _mcp_client.call_tool("send_notification", {
            "summary": summary, "body": body, "delay": delay
        })
    except Exception as e:
        return f"Error sending notification: {str(e)}"


def cleanup_screenshots() -> str:
    """Clean up temporary screenshot files by moving them to trash."""
    log_and_print(f"\n[SYSTEM] Cleaning up screenshots...")
    try:
        result = _mcp_client.call_tool("cleanup_screenshots", {})
        if result.startswith("Removed"):
            match = re.search(r'Removed (\d+)', result)
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
                capture_output=True, text=True, timeout=15
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
            log_and_print(f"[SYSTEM] flatpak search error: {e}", level='warning')
            break
    try:
        dnf = subprocess.run(
            ["dnf", "search", query],
            capture_output=True, text=True, timeout=15
        )
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
        log_and_print(f"[SYSTEM] dnf search error: {e}", level='warning')
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
            has_sudo = subprocess.run(
                ["sudo", "-n", "true"], capture_output=True, timeout=5
            ).returncode == 0
            if not has_sudo:
                return "Installing RPM packages requires sudo. Please type your sudo password in the terminal, then try again."
            cmd = ["sudo", "dnf", "install", "-y", app_id]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if result.returncode == 0:
            return f"Successfully installed {app_id}."
        else:
            stderr = result.stderr.strip()
            if "already installed" in stderr.lower() or "already installed" in result.stdout.lower():
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
            has_sudo = subprocess.run(
                ["sudo", "-n", "true"], capture_output=True, timeout=5
            ).returncode == 0
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
    from shortcuts.gnome_shortcuts import get_shortcuts_for_app
    import json as _json

    app_lower = app_name.lower().strip()
    shortcuts = {}

    shortcuts_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "shortcuts")
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
