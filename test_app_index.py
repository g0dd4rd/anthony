#!/usr/bin/env python3
"""
Test desktop application indexing for natural language resolution
"""

import os
import shutil


def build_app_index():
    """Build index of desktop applications from .desktop files.

    Maps natural language terms (Name, GenericName, Keywords) to executable names.
    """
    app_name_map = {}

    desktop_dirs = [
        "/usr/share/applications",
        os.path.expanduser("~/.local/share/applications")
    ]

    print("Building application index from .desktop files...\n")

    for desktop_dir in desktop_dirs:
        if not os.path.isdir(desktop_dir):
            continue

        for filename in os.listdir(desktop_dir):
            if not filename.endswith('.desktop'):
                continue

            filepath = os.path.join(desktop_dir, filename)
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    content = f.read()

                # Parse desktop file
                exec_name = None
                name = None
                generic_name = None
                keywords = []

                for line in content.split('\n'):
                    line = line.strip()

                    if line.startswith('Exec='):
                        # Extract executable (first word, remove path and % codes)
                        exec_line = line[5:].strip()
                        exec_name = exec_line.split()[0] if exec_line else None
                        if exec_name:
                            # Remove path prefix if present
                            exec_name = os.path.basename(exec_name)

                    elif line.startswith('Name=') and '=' in line:
                        name = line.split('=', 1)[1].strip()

                    elif line.startswith('GenericName='):
                        generic_name = line.split('=', 1)[1].strip()

                    elif line.startswith('Keywords='):
                        keywords_str = line.split('=', 1)[1].strip()
                        keywords = [k.strip().rstrip(';') for k in keywords_str.split(';') if k.strip()]

                if not exec_name:
                    continue

                # Add all mappings (case-insensitive)
                # 1. Exact executable name
                app_name_map[exec_name.lower()] = exec_name

                # 2. Name field
                if name:
                    app_name_map[name.lower()] = exec_name

                # 3. GenericName field
                if generic_name:
                    app_name_map[generic_name.lower()] = exec_name

                # 4. Keywords
                for keyword in keywords:
                    if keyword:
                        app_name_map[keyword.lower()] = exec_name

            except Exception as e:
                # Skip files that can't be parsed
                continue

    print(f"✓ Indexed {len(app_name_map)} application name mappings\n")
    return app_name_map


def test_app_resolution(app_map):
    """Test resolving common natural language app names"""

    test_names = [
        "audio player",
        "music player",
        "text editor",
        "browser",
        "web browser",
        "firefox",
        "rhythmbox",
        "files",
        "file manager",
        "terminal",
        "calculator",
        "settings",
        "gedit",
    ]

    print("=" * 60)
    print("TESTING APP NAME RESOLUTION")
    print("=" * 60)

    for test_name in test_names:
        resolved = app_map.get(test_name.lower())
        if resolved:
            # Check if executable exists
            exists = shutil.which(resolved) is not None
            status = "✓ EXISTS" if exists else "✗ NOT FOUND"
            print(f"'{test_name}' → {resolved} [{status}]")
        else:
            print(f"'{test_name}' → (no mapping)")

    print("\n" + "=" * 60)


def show_sample_mappings(app_map):
    """Show sample mappings for common apps"""
    print("\nSAMPLE MAPPINGS (showing first 30):")
    print("=" * 60)

    for i, (key, value) in enumerate(list(app_map.items())[:30]):
        print(f"{key:30} → {value}")

    print(f"\n... and {len(app_map) - 30} more mappings")
    print("=" * 60)


if __name__ == "__main__":
    app_map = build_app_index()
    test_app_resolution(app_map)
    show_sample_mappings(app_map)
