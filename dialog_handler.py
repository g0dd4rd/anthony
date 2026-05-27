#!/usr/bin/env python3
"""
Dialog Handler using dogtail for safe user interaction.

Detects dialogs, reads options, gets user input, and executes safely.

REQUIRES: Accessibility (a11y) must be enabled in GNOME
"""

import subprocess
import sys
from typing import Optional, List, Dict
import time

class DialogHandler:
    """Handles GNOME dialogs safely with user confirmation"""

    def __init__(self):
        self.last_dialog = None
        self._ensure_accessibility_enabled()

    def _ensure_accessibility_enabled(self):
        """
        Check if GNOME accessibility is enabled. Enable it if not.

        Dogtail requires toolkit-accessibility to be enabled.
        """
        try:
            # Check current state
            result = subprocess.run(
                ['gsettings', 'get', 'org.gnome.desktop.interface', 'toolkit-accessibility'],
                capture_output=True,
                text=True,
                check=True
            )

            is_enabled = result.stdout.strip() == 'true'

            if not is_enabled:
                print("[A11Y] ⚠️  Accessibility not enabled. Enabling now...")
                subprocess.run(
                    ['gsettings', 'set', 'org.gnome.desktop.interface', 'toolkit-accessibility', 'true'],
                    check=True
                )
                print("[A11Y] ✅ Accessibility enabled.")
                print("[A11Y] ⚠️  NOTE: You may need to restart applications for full a11y support.")
                print("[A11Y]      For best results, log out and log back in.")
            else:
                print("[A11Y] ✅ Accessibility already enabled")

        except Exception as e:
            print(f"[A11Y] ⚠️  Could not check/enable accessibility: {e}")
            print("[A11Y]      Run manually: gsettings set org.gnome.desktop.interface toolkit-accessibility true")

    def _import_dogtail(self):
        """Lazy import dogtail after ensuring a11y is enabled"""
        try:
            from dogtail.tree import root, SearchError
            from dogtail.utils import doDelay
            return root, SearchError, doDelay
        except ImportError as e:
            print(f"[A11Y] ❌ Error importing dogtail: {e}")
            print("[A11Y]      Install with: pip install dogtail")
            sys.exit(1)

    def find_dialogs(self, app_name=None) -> List[Dict]:
        """
        Find open dialogs/alerts, optionally filtered to a specific app.

        Args:
            app_name: AT-SPI application name to filter by. If provided,
                      only that app's tree is searched (much faster).

        Returns list of dialog info dicts with:
        - element: dogtail element
        - name: dialog title/name
        - role: roleName
        - app: parent application name
        """
        from dogtail.tree import root, SearchError

        dialogs = []

        try:
            for app in root.applications():
                if app_name and app_name.lower() != app.name.lower():
                    continue

                try:
                    alert_elements = app.findChildren(
                        lambda x: x.roleName in ['alert', 'dialog'] and x.showing,
                        recursive=True,
                        showingOnly=True
                    )

                    for elem in alert_elements:
                        dialogs.append({
                            'element': elem,
                            'name': elem.name or 'Unnamed Dialog',
                            'role': elem.roleName,
                            'app': app.name
                        })
                except SearchError:
                    continue

        except Exception as e:
            print(f"[Dialog] Error finding dialogs: {e}")

        return dialogs

    def get_dialog_info(self, dialog_element) -> Dict:
        """
        Extract detailed information from a dialog.

        Returns:
        - title: Dialog title
        - message: Main text/message
        - buttons: List of button dicts with 'text' and 'element'
        """
        info = {
            'title': dialog_element.name or 'Dialog',
            'message': '',
            'buttons': []
        }

        try:
            # Find all labels in the dialog (contains message text)
            labels = dialog_element.findChildren(
                lambda x: x.roleName == 'label' and x.showing and x.text,
                recursive=True
            )

            # Concatenate label texts to form message
            message_parts = []
            for label in labels:
                text = label.text.strip()
                if text and len(text) > 1:  # Skip single-char labels
                    message_parts.append(text)

            info['message'] = ' '.join(message_parts)

            # Find all buttons (roleName is 'button', not 'push button')
            buttons = dialog_element.findChildren(
                lambda x: x.roleName == 'button',  # Changed from 'push button'
                recursive=True
            )

            for btn in buttons:
                if btn.name:
                    info['buttons'].append({
                        'text': btn.name,
                        'element': btn
                    })

        except Exception as e:
            print(f"[Dialog] Error extracting dialog info: {e}")

        return info

    def detect_save_dialog(self, app_name: str = None, timeout: float = 2.0) -> Optional[Dict]:
        """
        Detect if a save/discard dialog appeared.

        Args:
            app_name: Optional application name to filter dialogs
            timeout: How long to wait for dialog to appear

        Returns:
            Dialog info dict if found, None otherwise
        """
        start_time = time.time()
        checks = 0

        print(f"[Dialog] Searching for dialogs (timeout: {timeout}s, app filter: {app_name or 'none'})...")

        while time.time() - start_time < timeout:
            dialogs = self.find_dialogs(app_name=app_name)
            checks += 1

            if checks == 1 or checks % 10 == 0:
                print(f"[Dialog] Check #{checks}: Found {len(dialogs)} dialog(s)")

            for dialog in dialogs:
                print(f"[Dialog]   - Dialog in '{dialog['app']}': '{dialog['name']}'")

                # Check if this looks like a save dialog
                info = self.get_dialog_info(dialog['element'])

                print(f"[Dialog]     Title: {info['title']}")
                print(f"[Dialog]     Message: {info['message'][:80]}...")
                print(f"[Dialog]     Buttons: {[btn['text'] for btn in info['buttons']]}")

                # Common keywords in save dialogs
                save_keywords = ['save', 'discard', 'changes', 'close without saving',
                                'don\'t save', 'cancel']

                dialog_text = (info['title'] + ' ' + info['message']).lower()
                button_texts = [btn['text'].lower() for btn in info['buttons']]

                # If dialog mentions save/discard or has those buttons
                if any(kw in dialog_text for kw in save_keywords) or \
                   any(kw in ' '.join(button_texts) for kw in save_keywords):

                    print(f"[Dialog]     ✅ MATCH! This looks like a save dialog")
                    self.last_dialog = {
                        'dialog': dialog,
                        'info': info
                    }
                    return self.last_dialog
                else:
                    print(f"[Dialog]     Not a save dialog (no matching keywords)")

            time.sleep(0.1)

        print(f"[Dialog] No save dialog found after {checks} checks over {timeout}s")
        return None

    def describe_dialog(self, dialog_data: Dict) -> str:
        """
        Create a human-readable description of dialog options.

        Args:
            dialog_data: Dict from detect_save_dialog()

        Returns:
            Description string for TTS
        """
        info = dialog_data['info']

        description_parts = []

        # Add title
        if info['title']:
            description_parts.append(f"Dialog: {info['title']}")

        # Add message (truncate if too long)
        if info['message']:
            message = info['message']
            if len(message) > 100:
                message = message[:97] + "..."
            description_parts.append(f"Message: {message}")

        # Add button options
        if info['buttons']:
            button_names = [btn['text'] for btn in info['buttons']]
            options_str = ', '.join(button_names)
            description_parts.append(f"Options: {options_str}")

        return '. '.join(description_parts)

    def activate_button_by_keyboard(self, dialog_data: Dict, button_choice: str, use_fallback: bool = True, key_callback=None) -> bool:
        """
        Activate dialog button using keyboard shortcuts with Tab/arrow fallback.

        Strategy:
        1. Try Alt+key shortcuts first (Alt+s/d/c)
        2. If that fails (Wayland issue), use Tab/arrow navigation:
           - Tab once lands on Discard (middle button)
           - Left arrow → Cancel, Right arrow → Save
           - Enter activates selected button

        Args:
            dialog_data: Dict from detect_save_dialog()
            button_choice: User's choice (e.g., "save", "discard", "cancel")
            use_fallback: If True, try Tab/arrow navigation if shortcuts fail
            key_callback: Optional callback function(keys_str) for sending keyboard input.
                         If None, uses dogtail. If provided, uses callback instead.

        Returns:
            True if shortcut was sent, False otherwise
        """
        choice_lower = button_choice.lower()

        # Map user choice to keyboard shortcuts and navigation
        shortcuts = {
            'save': 'Alt+s',
            'discard': 'Alt+d',
            'cancel': 'Alt+c',
            'don\'t save': 'Alt+d',
            'no': 'Alt+d',
            'yes': 'Alt+s',
        }

        # Determine which button to activate
        target_button = None
        if any(k in choice_lower or choice_lower in k for k in ['save', 'yes']):
            target_button = 'save'
        elif any(k in choice_lower or choice_lower in k for k in ['discard', 'don\'t save', 'no']):
            target_button = 'discard'
        elif 'cancel' in choice_lower or choice_lower in 'cancel':
            target_button = 'cancel'

        if not target_button:
            print(f"[Dialog] No keyboard shortcut found for: {button_choice}")
            return False

        shortcut = shortcuts[target_button]

        # STRATEGY 1: Try keyboard shortcut (Alt+s/d/c)
        if key_callback:
            # Use provided keyboard callback (e.g., MCP client)
            print(f"[Dialog] Trying keyboard shortcut via callback: {shortcut}")
            key_callback(shortcut)
            time.sleep(0.5)
        else:
            # Use dogtail keyboard input (fallback for standalone usage)
            from dogtail.rawinput import keyCombo, pressKey
            from dogtail.utils import doDelay

            try:
                dialog_element = dialog_data['dialog']['element']
                print(f"[Dialog] Grabbing focus on dialog...")
                dialog_element.grabFocus()
                doDelay(0.2)
            except Exception as e:
                print(f"[Dialog] Warning: Could not grab focus: {e}")

            print(f"[Dialog] Trying keyboard shortcut: <{shortcut.replace('+', '>')}")
            keyCombo(f"<{shortcut.replace('+', '>')}")
            doDelay(0.5)

        # Check if dialog closed (shortcut worked)
        if not self.verify_dialog_closed(dialog_data, timeout=0.5):
            if use_fallback:
                # STRATEGY 2: Fallback to Tab/arrow navigation
                print(f"[Dialog] Shortcut didn't work, using Tab/arrow fallback...")

                if key_callback:
                    # Use callback for Tab/arrow navigation
                    print(f"[Dialog] Pressing Tab to focus Discard button")
                    key_callback('Tab')
                    time.sleep(0.2)

                    # Navigate to target button
                    if target_button == 'save':
                        print(f"[Dialog] Pressing Right arrow to move to Save button")
                        key_callback('Right')
                        time.sleep(0.2)
                    elif target_button == 'cancel':
                        print(f"[Dialog] Pressing Left arrow to move to Cancel button")
                        key_callback('Left')
                        time.sleep(0.2)
                    # For 'discard', we're already there after Tab

                    # Press Enter to activate
                    print(f"[Dialog] Pressing Return to activate {target_button.title()} button")
                    key_callback('Return')
                    time.sleep(0.3)
                else:
                    # Use dogtail for Tab/arrow navigation
                    from dogtail.rawinput import pressKey
                    from dogtail.utils import doDelay

                    # Tab once to select Discard button (middle)
                    print(f"[Dialog] Pressing Tab to focus Discard button")
                    pressKey('Tab')
                    doDelay(0.2)

                    # Navigate to target button
                    if target_button == 'save':
                        print(f"[Dialog] Pressing Right arrow to move to Save button")
                        pressKey('Right')
                        doDelay(0.2)
                    elif target_button == 'cancel':
                        print(f"[Dialog] Pressing Left arrow to move to Cancel button")
                        pressKey('Left')
                        doDelay(0.2)
                    # For 'discard', we're already there after Tab

                    # Press Enter to activate
                    print(f"[Dialog] Pressing Enter to activate {target_button.title()} button")
                    pressKey('Enter')
                    doDelay(0.3)
            else:
                print(f"[Dialog] Shortcut may not have worked, fallback disabled")

        return True

    def click_button_by_text(self, dialog_data: Dict, button_text: str) -> bool:
        """
        Click a button in the dialog by matching text.

        Args:
            dialog_data: Dict from detect_save_dialog()
            button_text: Text to match (case-insensitive, partial match OK)

        Returns:
            True if button clicked successfully, False otherwise
        """
        from dogtail.utils import doDelay

        try:
            info = dialog_data['info']
            button_text_lower = button_text.lower()

            # Find matching button
            for btn in info['buttons']:
                if button_text_lower in btn['text'].lower():
                    print(f"[Dialog] Clicking button: {btn['text']}")
                    btn['element'].click()
                    doDelay(0.3)
                    return True

            # Try fuzzy matching common alternatives
            alternatives = {
                'save': ['save', 'yes'],
                'discard': ['discard', 'don\'t save', 'no'],
                'cancel': ['cancel', 'close']
            }

            for key, variants in alternatives.items():
                if button_text_lower in key or any(v in button_text_lower for v in variants):
                    for btn in info['buttons']:
                        if any(v in btn['text'].lower() for v in variants):
                            print(f"[Dialog] Clicking button: {btn['text']}")
                            btn['element'].click()
                            doDelay(0.3)
                            return True

            print(f"[Dialog] No button found matching: {button_text}")
            return False

        except Exception as e:
            print(f"[Dialog] Error clicking button: {e}")
            return False

    def verify_dialog_closed(self, dialog_data: Dict, timeout: float = 2.0) -> bool:
        """
        Verify that the dialog was closed successfully.

        Args:
            dialog_data: Original dialog data
            timeout: How long to wait for closure

        Returns:
            True if dialog closed, False if still visible
        """
        start_time = time.time()

        while time.time() - start_time < timeout:
            try:
                # Try to check if dialog element still exists and is showing
                elem = dialog_data['dialog']['element']
                if not elem.showing:
                    return True
            except:
                # Element no longer exists (good - dialog closed)
                return True

            time.sleep(0.1)

        # Timeout - dialog might still be there
        try:
            return not dialog_data['dialog']['element'].showing
        except:
            return True  # Can't check, assume closed


# Example usage and testing
if __name__ == "__main__":
    print("Dialog Handler Test")
    print("="*60)
    print("1. Open gnome-text-editor")
    print("2. Type some text")
    print("3. Try to close the window (Ctrl+Q or close button)")
    print("4. This script will detect and describe the save dialog\n")

    input("Press Enter when ready to test...")

    handler = DialogHandler()

    print("\n[Test] Waiting for save dialog to appear...")
    dialog = handler.detect_save_dialog(timeout=10.0)

    if dialog:
        print("\n✅ Dialog detected!")
        description = handler.describe_dialog(dialog)
        print(f"\n{description}\n")

        # List buttons
        print("Available buttons:")
        for i, btn in enumerate(dialog['info']['buttons'], 1):
            print(f"  {i}. {btn['text']}")

        # Test clicking
        choice = input("\nEnter button text to click (or 'cancel' to skip): ").strip()

        if choice and choice.lower() != 'cancel':
            success = handler.click_button_by_text(dialog, choice)

            if success:
                print("\n[Test] Button clicked, verifying closure...")
                closed = handler.verify_dialog_closed(dialog)

                if closed:
                    print("✅ Dialog closed successfully")
                else:
                    print("⚠️  Dialog might still be open")
            else:
                print("❌ Failed to click button")
    else:
        print("\n❌ No save dialog detected in 10 seconds")
        print("Make sure to close an app with unsaved changes!")
