#!/usr/bin/env python3
"""
Test app resolution in orchestrator without running the full voice loop
"""

import os
import sys

# Build the app index exactly as the orchestrator does
app_name_map = {}
app_friendly_name = {}

def build_app_index():
    """Build index of desktop applications from .desktop files."""
    global app_name_map, app_friendly_name
    app_name_map = {}
    app_friendly_name = {}

    desktop_dir = "/usr/share/applications"

    if not os.path.isdir(desktop_dir):
        print(f"Warning: {desktop_dir} not found")
        return

    # Parse all desktop files and collect data
    apps = []

    for filename in os.listdir(desktop_dir):
        if not filename.endswith('.desktop'):
            continue

        filepath = os.path.join(desktop_dir, filename)
        is_gnome = filename.startswith('org.gnome.')

        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()

            exec_name = None
            name = None
            generic_name = None
            keywords = []

            # Only parse [Desktop Entry] section, stop at next section
            in_desktop_entry = False
            for line in content.split('\n'):
                line = line.strip()

                # Check for section headers
                if line.startswith('['):
                    if line == '[Desktop Entry]':
                        in_desktop_entry = True
                        continue
                    elif in_desktop_entry:
                        # Hit another section, stop parsing
                        break

                if not in_desktop_entry:
                    continue

                if line.startswith('Exec='):
                    exec_line = line[5:].strip()
                    exec_name = exec_line.split()[0] if exec_line else None
                    if exec_name:
                        exec_name = os.path.basename(exec_name)

                elif line.startswith('Name=') and not name:
                    # Only take first Name= encountered
                    name = line.split('=', 1)[1].strip()

                elif line.startswith('GenericName=') and not generic_name:
                    # Only take first GenericName= encountered
                    generic_name = line.split('=', 1)[1].strip()

                elif line.startswith('Keywords='):
                    keywords_str = line.split('=', 1)[1].strip()
                    keywords = [k.strip().rstrip(';') for k in keywords_str.split(';') if k.strip()]

            if exec_name:
                apps.append({
                    'exec': exec_name,
                    'name': name,
                    'generic_name': generic_name,
                    'keywords': keywords,
                    'is_gnome': is_gnome
                })
        except:
            continue

    # First pass: non-gnome apps
    for app in apps:
        if app['is_gnome']:
            continue

        exec_name = app['exec']

        # Store friendly name
        if app['name']:
            app_friendly_name[exec_name] = app['name']
        elif app['generic_name']:
            app_friendly_name[exec_name] = app['generic_name']
        else:
            app_friendly_name[exec_name] = exec_name

        app_name_map[exec_name.lower()] = exec_name

        if app['name']:
            app_name_map[app['name'].lower()] = exec_name

        if app['generic_name']:
            app_name_map[app['generic_name'].lower()] = exec_name

        for keyword in app['keywords']:
            if keyword:
                app_name_map[keyword.lower()] = exec_name

    # Second pass: gnome apps (overwrite with priority)
    gnome_count = 0
    for app in apps:
        if not app['is_gnome']:
            continue

        gnome_count += 1
        exec_name = app['exec']

        # Store friendly name
        if app['name']:
            app_friendly_name[exec_name] = app['name']
        elif app['generic_name']:
            app_friendly_name[exec_name] = app['generic_name']
        else:
            app_friendly_name[exec_name] = exec_name

        app_name_map[exec_name.lower()] = exec_name

        if app['name']:
            app_name_map[app['name'].lower()] = exec_name

        if app['generic_name']:
            app_name_map[app['generic_name'].lower()] = exec_name

        for keyword in app['keywords']:
            if keyword:
                app_name_map[keyword.lower()] = exec_name

    print(f"✓ Indexed {len(app_name_map)} app name mappings ({gnome_count} org.gnome with priority)\n")


def test_resolution(app_name):
    """Test resolving an app name"""
    resolved_exec = app_name_map.get(app_name.lower(), app_name)
    friendly_name = app_friendly_name.get(resolved_exec, resolved_exec)

    if resolved_exec != app_name:
        print(f"✓ '{app_name}' → exec: '{resolved_exec}' → friendly: '{friendly_name}'")
    else:
        print(f"✗ '{app_name}' → (no mapping, will try literal)")
    return resolved_exec, friendly_name


if __name__ == "__main__":
    print("Building app index...\n")
    build_app_index()

    print("=" * 60)
    print("TESTING APP RESOLUTION")
    print("=" * 60)

    test_cases = [
        "audio player",
        "Audio Player",
        "AUDIO PLAYER",
        "music",
        "text editor",
        "browser",
        "firefox",
        "files",
        "terminal",
        "calculator",
        "settings",
        "nonexistent app",
    ]

    for test in test_cases:
        test_resolution(test)

    print("\n" + "=" * 60)
