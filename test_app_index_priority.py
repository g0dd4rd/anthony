#!/usr/bin/env python3
"""
Test both indexing approaches: flat vs multi-candidate
"""

import os


def build_flat_index():
    """Flat map: org.gnome apps overwrite conflicts"""
    app_map = {}
    desktop_dir = "/usr/share/applications"

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

            for line in content.split('\n'):
                line = line.strip()
                if line.startswith('Exec='):
                    exec_line = line[5:].strip()
                    exec_name = exec_line.split()[0] if exec_line else None
                    if exec_name:
                        exec_name = os.path.basename(exec_name)
                elif line.startswith('Name='):
                    name = line.split('=', 1)[1].strip()
                elif line.startswith('GenericName='):
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

    # First: non-gnome apps
    for app in apps:
        if app['is_gnome']:
            continue
        exec_name = app['exec']
        app_map[exec_name.lower()] = exec_name
        if app['name']:
            app_map[app['name'].lower()] = exec_name
        if app['generic_name']:
            app_map[app['generic_name'].lower()] = exec_name
        for kw in app['keywords']:
            if kw:
                app_map[kw.lower()] = exec_name

    # Second: gnome apps (overwrite)
    for app in apps:
        if not app['is_gnome']:
            continue
        exec_name = app['exec']
        app_map[exec_name.lower()] = exec_name
        if app['name']:
            app_map[app['name'].lower()] = exec_name
        if app['generic_name']:
            app_map[app['generic_name'].lower()] = exec_name
        for kw in app['keywords']:
            if kw:
                app_map[kw.lower()] = exec_name

    return app_map


def build_multi_candidate_index():
    """Multi-candidate map: org.gnome apps listed first"""
    app_map = {}
    desktop_dir = "/usr/share/applications"

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

            for line in content.split('\n'):
                line = line.strip()
                if line.startswith('Exec='):
                    exec_line = line[5:].strip()
                    exec_name = exec_line.split()[0] if exec_line else None
                    if exec_name:
                        exec_name = os.path.basename(exec_name)
                elif line.startswith('Name='):
                    name = line.split('=', 1)[1].strip()
                elif line.startswith('GenericName='):
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

    # Add all apps, collecting candidates
    for app in apps:
        exec_name = app['exec']
        terms = [exec_name.lower()]
        if app['name']:
            terms.append(app['name'].lower())
        if app['generic_name']:
            terms.append(app['generic_name'].lower())
        terms.extend([kw.lower() for kw in app['keywords'] if kw])

        for term in terms:
            if term not in app_map:
                app_map[term] = []
            # Insert org.gnome at front, others at back
            if app['is_gnome']:
                app_map[term].insert(0, exec_name)
            else:
                app_map[term].append(exec_name)

    # Deduplicate
    for term in app_map:
        seen = set()
        unique = []
        for exec_name in app_map[term]:
            if exec_name not in seen:
                seen.add(exec_name)
                unique.append(exec_name)
        app_map[term] = unique

    return app_map


print("=" * 70)
print("OPTION 1: FLAT INDEX (org.gnome overwrites conflicts)")
print("=" * 70)
flat = build_flat_index()
print(f"Total mappings: {len(flat)}\n")

test_terms = ["text editor", "audio player", "browser", "files", "terminal"]
for term in test_terms:
    result = flat.get(term, "(no mapping)")
    print(f"  '{term}' → {result}")

print("\n" + "=" * 70)
print("OPTION 2: MULTI-CANDIDATE (org.gnome listed first)")
print("=" * 70)
multi = build_multi_candidate_index()
print(f"Total mappings: {len(multi)}\n")

for term in test_terms:
    result = multi.get(term, "(no mapping)")
    if isinstance(result, list):
        print(f"  '{term}' → {result}")
    else:
        print(f"  '{term}' → {result}")

print("\n" + "=" * 70)
print("WHICH IS BETTER FOR LLM?")
print("=" * 70)
print("""
Option 1 (Flat):
  + Simple: one term → one answer
  + LLM just needs to resolve term to executable
  + Tool schema: "Launch app_name"
  - Hides non-gnome apps when there's conflict

Option 2 (Multi-candidate):
  + Shows all options, LLM can choose
  + Non-gnome apps visible
  + Tool schema: "Launch app_name, prefer first in list"
  - More complex, LLM might get confused
  - Needs array handling in tool function

Recommendation: Try Option 1 first (simpler, more deterministic)
""")
