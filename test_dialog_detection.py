#!/usr/bin/env python3
"""
Test if dialog detection actually works with text editor.
"""

from dialog_handler import DialogHandler
import time

print("="*60)
print("DIALOG DETECTION TEST")
print("="*60)
print("\nInstructions:")
print("1. Open gnome-text-editor")
print("2. Type some text")
print("3. Press Ctrl+Q (or close button)")
print("4. DO NOT click any buttons in the dialog")
print("5. Press Enter here when dialog is visible\n")

input("Press Enter when dialog is showing...")

handler = DialogHandler()

print("\n[TEST] Searching for dialogs...")
dialogs = handler.find_dialogs()

print(f"\n[TEST] Found {len(dialogs)} dialogs")

if dialogs:
    for i, dialog in enumerate(dialogs, 1):
        print(f"\nDialog {i}:")
        print(f"  Name: {dialog['name']}")
        print(f"  Role: {dialog['role']}")
        print(f"  App: {dialog['app']}")

        info = handler.get_dialog_info(dialog['element'])
        print(f"  Message: {info['message'][:100]}...")
        print(f"  Buttons: {[btn['text'] for btn in info['buttons']]}")

    print("\n[TEST] Testing detect_save_dialog()...")
    result = handler.detect_save_dialog(timeout=2.0)

    if result:
        print("✅ detect_save_dialog() WORKS!")
        desc = handler.describe_dialog(result)
        print(f"\nDescription: {desc}")
    else:
        print("❌ detect_save_dialog() returned None")
        print("   But find_dialogs() found dialogs above!")
        print("   There's a bug in the detection logic.")
else:
    print("\n❌ No dialogs found at all!")
    print("Possible causes:")
    print("  1. Dialog already closed")
    print("  2. Accessibility not working")
    print("  3. Text editor doesn't use accessible dialogs")

    print("\n[DEBUG] Checking accessibility...")
    import subprocess
    result = subprocess.run(
        ['gsettings', 'get', 'org.gnome.desktop.interface', 'toolkit-accessibility'],
        capture_output=True, text=True
    )
    print(f"  Accessibility enabled: {result.stdout.strip()}")

    print("\n[DEBUG] Listing all accessible apps...")
    from dogtail.tree import root
    apps = [app.name for app in root.applications()]
    print(f"  Accessible apps: {apps}")

    if 'org.gnome.TextEditor' in apps or 'TextEditor' in apps:
        print("  ✅ Text Editor is accessible")
    else:
        print("  ⚠️ Text Editor not in accessible apps list")
