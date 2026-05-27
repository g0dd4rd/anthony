#!/usr/bin/env python3
"""
Discover AT-SPI accessibility names for installed GUI applications.

Launches each app, checks dogtail's root.applications() for the AT-SPI name,
records the mapping, and closes the app. Results are written to config/aliases.py
as APP_A11Y_NAMES dict.

Usage: python tools/discover_a11y.py
"""

import os
import signal
import subprocess
import sys
import time

import gi
gi.require_version('Gio', '2.0')
from gi.repository import Gio

from dogtail.tree import root


def get_running_atspi_names():
    return {app.name for app in root.applications()}


def kill_pid(pid, timeout=5):
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return
        time.sleep(0.3)
    try:
        os.kill(pid, signal.SIGKILL)
    except ProcessLookupError:
        pass


def discover():
    apps = []
    for gio_app in Gio.AppInfo.get_all():
        if not gio_app.should_show():
            continue
        exec_path = gio_app.get_executable()
        if not exec_path:
            continue
        exec_name = os.path.basename(exec_path)
        display_name = gio_app.get_display_name() or exec_name
        apps.append({
            'exec': exec_name,
            'exec_path': exec_path,
            'name': display_name,
        })

    seen_execs = set()
    unique_apps = []
    for app in apps:
        if app['exec'] not in seen_execs:
            seen_execs.add(app['exec'])
            unique_apps.append(app)

    print(f"Found {len(unique_apps)} unique GUI apps to discover")

    mapping = {}
    before_all = get_running_atspi_names()
    print(f"Currently running AT-SPI apps: {before_all}")

    for i, app in enumerate(unique_apps):
        exec_name = app['exec']
        exec_path = app['exec_path']
        display_name = app['name']

        if exec_name in mapping:
            continue

        print(f"\n[{i+1}/{len(unique_apps)}] {display_name} ({exec_name})")

        before = get_running_atspi_names()

        try:
            proc = subprocess.Popen(
                [exec_path],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except Exception as e:
            print(f"  SKIP: Could not launch: {e}")
            continue

        time.sleep(2)
        after = get_running_atspi_names()
        new_apps = after - before

        if not new_apps:
            print(f"  SKIP: No new AT-SPI entry appeared")
            kill_pid(proc.pid)
            time.sleep(1)
            continue

        if len(new_apps) == 1:
            atspi_name = new_apps.pop()
        else:
            exec_lower = exec_name.lower().replace('-', '').replace('_', '')
            best = None
            for name in new_apps:
                name_lower = name.lower().replace('-', '').replace('_', '').replace('.', '')
                if exec_lower in name_lower or name_lower in exec_lower:
                    best = name
                    break
            atspi_name = best or sorted(new_apps)[0]
            print(f"  Multiple new entries: {new_apps}, picked: {atspi_name}")

        mapping[exec_name] = atspi_name
        print(f"  FOUND: {exec_name} -> {atspi_name}")

        kill_pid(proc.pid)
        time.sleep(1)

    return mapping


def write_to_aliases(mapping):
    aliases_path = os.path.join(os.path.dirname(__file__), '..', 'config', 'aliases.py')
    aliases_path = os.path.abspath(aliases_path)

    with open(aliases_path, 'r') as f:
        content = f.read()

    marker = '# exec_name -> AT-SPI accessibility name'
    if marker in content:
        start = content.index(marker)
        # Find the closing brace of the existing dict
        brace_depth = 0
        idx = content.index('{', start)
        for j in range(idx, len(content)):
            if content[j] == '{':
                brace_depth += 1
            elif content[j] == '}':
                brace_depth -= 1
                if brace_depth == 0:
                    end = j + 1
                    break
        # Remove old block including the marker line
        line_start = content.rfind('\n', 0, start)
        if line_start == -1:
            line_start = 0
        content = content[:line_start].rstrip('\n') + '\n' + content[end:].lstrip('\n')

    lines = [f'\n\n{marker}']
    lines.append('# (discovered by tools/discover_a11y.py)')
    lines.append('APP_A11Y_NAMES = {')
    for exec_name in sorted(mapping):
        atspi_name = mapping[exec_name]
        lines.append(f'    "{exec_name}": "{atspi_name}",')
    lines.append('}')

    content = content.rstrip('\n') + '\n' + '\n'.join(lines) + '\n'

    with open(aliases_path, 'w') as f:
        f.write(content)

    print(f"\nWrote {len(mapping)} entries to {aliases_path}")


if __name__ == '__main__':
    print("AT-SPI Name Discovery")
    print("=" * 60)
    print("This will launch and close each GUI app to discover its")
    print("AT-SPI accessibility name. This may take several minutes.")
    print()

    if '--yes' not in sys.argv:
        answer = input("Continue? [y/N] ").strip().lower()
        if answer != 'y':
            print("Aborted.")
            sys.exit(0)

    mapping = discover()

    print(f"\n{'=' * 60}")
    print(f"Discovered {len(mapping)} AT-SPI names:")
    for k, v in sorted(mapping.items()):
        print(f"  {k} -> {v}")

    write_to_aliases(mapping)
