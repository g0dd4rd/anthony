import subprocess

from commands import _listen, _speak, step
from utils import log_and_print

_CONFIRM_WORDS = ("yes", "yeah", "yep", "sure", "do it", "confirm", "go ahead")
_CANCEL_WORDS = (
    "cancel",
    "skip",
    "nevermind",
    "never mind",
    "no",
    "nope",
    "stop",
    "forget it",
    "none",
)


def _search_apps(query):
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


def _run_install(app_id, source):
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
                return (
                    "Installing RPM packages requires sudo."
                    " Please type your sudo password in"
                    " the terminal, then try again."
                )
            cmd = ["sudo", "dnf", "install", "-y", app_id]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if result.returncode == 0:
            return f"Successfully installed {app_id}."
        stderr = result.stderr.strip()
        if "already installed" in stderr.lower() or "already installed" in result.stdout.lower():
            return f"{app_id} is already installed."
        return f"Installation failed: {stderr}"
    except subprocess.TimeoutExpired:
        return "Installation timed out after 5 minutes."
    except Exception as e:
        return f"Error installing: {e}"


def _run_uninstall(app_id, source):
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
                return (
                    "Uninstalling RPM packages requires sudo."
                    " Please type your sudo password in"
                    " the terminal, then try again."
                )
            cmd = ["sudo", "dnf", "remove", "-y", app_id]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if result.returncode == 0:
            return f"Successfully uninstalled {app_id}."
        return f"Uninstall failed: {result.stderr.strip()}"
    except Exception as e:
        return f"Error uninstalling: {e}"


def _confirm_and_install(name, app_id, source, is_uninstall):
    action_word = "uninstall" if is_uninstall else "install"
    _speak(f"Found {name}. Should I {action_word} it?")
    confirmation = _listen()
    if confirmation and any(w in confirmation.lower() for w in _CONFIRM_WORDS):
        _speak(
            f"{'Uninstalling' if is_uninstall else 'Installing'} {name}. This may take a moment."
        )
        if is_uninstall:
            return _run_uninstall(app_id, source)
        return _run_install(app_id, source)
    return "Canceled."


@step(
    "install {query}",
    category="apps",
    requires_confirmation=True,
    help_text="Install an application (searches Flatpak and DNF)",
)
def handle_install(context, query):
    _speak(f"Searching for {query}.")
    results = _search_apps(query)

    if not results:
        return f"No apps found matching {query}."

    if len(results) == 1:
        name, app_id, source = results[0]
        return _confirm_and_install(name, app_id, source, False)

    exact = next(((n, a, s) for n, a, s in results if n.lower() == query.lower()), None)
    if exact:
        return _confirm_and_install(*exact, False)

    names = [name for name, _, _ in results[:5]]
    names_str = ", ".join(names[:-1]) + f", and {names[-1]}" if len(names) > 1 else names[0]
    _speak(f"I found {names_str}. Which one?")
    choice = _listen()
    if not choice:
        return "No response heard. Canceled."
    if any(w in choice.lower() for w in _CANCEL_WORDS):
        return "Canceled."

    choice_lower = choice.lower().strip().strip(".,!").strip()
    matched = next(
        (
            (n, a, s)
            for n, a, s in results
            if n.lower() in choice_lower or choice_lower in n.lower()
        ),
        None,
    )
    if matched:
        return _confirm_and_install(*matched, False)
    return f"Could not find {choice} in the results. Canceled."


@step(
    "uninstall {query}",
    "remove app {query}",
    category="apps",
    requires_confirmation=True,
    help_text="Uninstall an application",
)
def handle_uninstall(context, query):
    _speak(f"Searching for {query}.")
    results = _search_apps(query)

    if not results:
        return f"No apps found matching {query}."

    if len(results) == 1:
        name, app_id, source = results[0]
        return _confirm_and_install(name, app_id, source, True)

    exact = next(((n, a, s) for n, a, s in results if n.lower() == query.lower()), None)
    if exact:
        return _confirm_and_install(*exact, True)

    names = [name for name, _, _ in results[:5]]
    names_str = ", ".join(names[:-1]) + f", and {names[-1]}" if len(names) > 1 else names[0]
    _speak(f"I found {names_str}. Which one?")
    choice = _listen()
    if not choice:
        return "No response heard. Canceled."
    if any(w in choice.lower() for w in _CANCEL_WORDS):
        return "Canceled."

    choice_lower = choice.lower().strip().strip(".,!").strip()
    matched = next(
        (
            (n, a, s)
            for n, a, s in results
            if n.lower() in choice_lower or choice_lower in n.lower()
        ),
        None,
    )
    if matched:
        return _confirm_and_install(*matched, True)
    return f"Could not find {choice} in the results. Canceled."


# --- App shortcuts query ---


@step(
    "shortcuts for {app}",
    "what are the shortcuts for {app}",
    "keyboard shortcuts for {app}",
    "shortcut for {app}",
    "how do I save in {app}",
    "what shortcuts does {app} have",
    "{app} shortcuts",
    "show shortcuts for {app}",
    category="apps",
    help_text="Look up keyboard shortcuts for an application",
)
def handle_shortcuts(context, app):
    from tools.standalone import get_app_shortcuts

    shortcut_info = get_app_shortcuts(app)
    if shortcut_info.startswith("No shortcuts"):
        return shortcut_info

    shortcuts_only = shortcut_info.split("\nSkills (")[0]
    lines = shortcuts_only.splitlines()
    shortcuts = [ln.lstrip("- ").strip() for ln in lines if ln.startswith("- ")]
    return f"Shortcuts for {app}: " + ", ".join(shortcuts)
