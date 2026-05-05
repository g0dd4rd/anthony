#!/usr/bin/env python3
"""
Test keyboard shortcut activation for dialog buttons.
"""

from dialog_handler import DialogHandler
import time

print("="*60)
print("KEYBOARD SHORTCUT TEST")
print("="*60)
print("\nThis will test pressing <Alt>s, <Alt>d, <Alt>c for dialog buttons")
print("\nInstructions:")
print("1. Open gnome-text-editor")
print("2. Type some text")
print("3. Press Ctrl+Q to show save dialog")
print("4. DO NOT click anything")
print("5. Press Enter here when dialog is visible\n")

input("Press Enter when ready...")

handler = DialogHandler()

print("\n[TEST] Testing button detection with 'button' roleName...")
dialog = handler.detect_save_dialog(timeout=2.0)

if not dialog:
    print("❌ No dialog detected!")
    exit(1)

print(f"✅ Dialog detected: {dialog['info']['title']}")
print(f"   Message: {dialog['info']['message'][:80]}...")

buttons = dialog['info']['buttons']
if buttons:
    print(f"✅ Found {len(buttons)} buttons: {[btn['text'] for btn in buttons]}")
else:
    print(f"⚠️  No buttons detected (but that's OK, we'll use keyboard shortcuts)")

print("\n" + "="*60)
print("TESTING KEYBOARD SHORTCUTS")
print("="*60)

test_choices = ['save', 'discard', 'cancel', "don't save", 'yes', 'no']

for choice in test_choices:
    print(f"\nTest input: '{choice}'")

    # Map to shortcut
    shortcuts = {
        'save': '<Alt>s',
        'discard': '<Alt>d',
        'cancel': '<Alt>c',
        'don\'t save': '<Alt>d',
        'no': '<Alt>d',
        'yes': '<Alt>s',
    }

    expected = None
    for key, combo in shortcuts.items():
        if key in choice.lower() or choice.lower() in key:
            expected = combo
            break

    print(f"  Expected shortcut: {expected}")

print("\n" + "="*60)
print("MANUAL TEST")
print("="*60)
print("\nNow let's test actually pressing a shortcut.")
print("The dialog should still be open.")
print("\nWhich button do you want to test?")
print("  1. Save (<Alt>s)")
print("  2. Discard (<Alt>d)")
print("  3. Cancel (<Alt>c)")

choice = input("\nEnter 1, 2, or 3 (or 'skip'): ").strip()

if choice == '1':
    user_choice = 'save'
elif choice == '2':
    user_choice = 'discard'
elif choice == '3':
    user_choice = 'cancel'
else:
    print("Skipping manual test")
    exit(0)

print(f"\n[TEST] Activating '{user_choice}' button via keyboard...")
success = handler.activate_button_by_keyboard(dialog, user_choice)

if success:
    print("✅ Keyboard shortcut sent!")
    print("   Check if the dialog responded correctly.")

    time.sleep(1)

    # Check if dialog closed
    print("\n[TEST] Checking if dialog closed...")
    dialog_after = handler.detect_save_dialog(timeout=1.0)

    if dialog_after:
        print("⚠️  Dialog still open (might be expected for 'Cancel')")
    else:
        print("✅ Dialog closed!")
else:
    print("❌ Failed to send keyboard shortcut")
