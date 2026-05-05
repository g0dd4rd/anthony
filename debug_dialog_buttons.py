#!/usr/bin/env python3
"""
Debug why buttons aren't found in text editor dialog.
"""

from dogtail.tree import root
import time

print("="*60)
print("BUTTON DETECTION DEBUG")
print("="*60)
print("\nInstructions:")
print("1. Open gnome-text-editor")
print("2. Type some text")
print("3. Press Ctrl+Q")
print("4. Press Enter here when dialog is showing\n")

input("Press Enter when ready...")

print("\n[DEBUG] Finding text editor app...")
app = None
for a in root.applications():
    if 'text' in a.name.lower() or 'editor' in a.name.lower():
        print(f"[DEBUG] Found: {a.name}")
        app = a
        break

if not app:
    print("❌ Text editor app not found!")
    exit(1)

print(f"\n[DEBUG] Looking for dialogs in {app.name}...")

# Find all alerts/dialogs
dialogs = app.findChildren(
    lambda x: x.roleName in ['alert', 'dialog'] and x.showing,
    recursive=True
)

print(f"[DEBUG] Found {len(dialogs)} dialog(s)")

if not dialogs:
    print("❌ No dialogs found!")
    exit(1)

for i, dialog in enumerate(dialogs):
    print(f"\n{'='*60}")
    print(f"DIALOG {i+1}: {dialog.name}")
    print(f"{'='*60}")

    # Print entire element tree
    def print_tree(elem, indent=0):
        try:
            role = elem.roleName
            name = elem.name or "(no name)"
            showing = "✓" if elem.showing else "✗"

            print(f"{'  '*indent}[{showing}] {role}: {name}")

            # If it looks like a button, print more details
            if 'button' in role.lower():
                print(f"{'  '*indent}    → This is a BUTTON!")
                print(f"{'  '*indent}       showing={elem.showing}")
                print(f"{'  '*indent}       sensitive={elem.sensitive if hasattr(elem, 'sensitive') else 'N/A'}")

            for child in elem.children:
                print_tree(child, indent + 1)
        except:
            pass

    print("\nFull element tree:")
    print_tree(dialog)

    print("\n" + "="*60)
    print("BUTTON SEARCH ATTEMPTS:")
    print("="*60)

    # Try 1: Standard search
    buttons1 = dialog.findChildren(
        lambda x: x.roleName == 'push button' and x.showing,
        recursive=True
    )
    print(f"\n1. roleName == 'push button' and showing: {len(buttons1)} found")

    # Try 2: Any button type
    buttons2 = dialog.findChildren(
        lambda x: 'button' in x.roleName.lower() and x.showing,
        recursive=True
    )
    print(f"2. 'button' in roleName and showing: {len(buttons2)} found")

    # Try 3: Button without showing check
    buttons3 = dialog.findChildren(
        lambda x: 'button' in x.roleName.lower(),
        recursive=True
    )
    print(f"3. 'button' in roleName (no showing check): {len(buttons3)} found")
    if buttons3:
        for btn in buttons3:
            print(f"   - {btn.name} (showing={btn.showing})")

    # Try 4: Look for specific names
    buttons4 = dialog.findChildren(
        lambda x: x.name and x.name.lower() in ['save', 'discard', 'cancel'],
        recursive=True
    )
    print(f"4. By name (save/discard/cancel): {len(buttons4)} found")
    if buttons4:
        for btn in buttons4:
            print(f"   - {btn.name} (role={btn.roleName}, showing={btn.showing})")

    # Try 5: All children with names
    all_named = dialog.findChildren(
        lambda x: x.name and len(x.name) > 0,
        recursive=True
    )
    print(f"\n5. All elements with names: {len(all_named)} found")
    for elem in all_named[:20]:  # First 20
        print(f"   - {elem.roleName}: {elem.name}")

print("\n" + "="*60)
print("RECOMMENDATION:")
print("="*60)
print("Look for elements marked '→ This is a BUTTON!' in the tree above.")
print("Check their roleName and update button detection accordingly.")
