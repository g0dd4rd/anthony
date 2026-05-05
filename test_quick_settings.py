#!/usr/bin/env python3
"""
Test quick settings functionality via MCP server
"""

import sys
sys.path.insert(0, '/home/jprajzne/anthony')

from mcp_client import MCPClient


def test_quick_settings():
    """Test quick settings MCP tool"""
    print("=" * 60)
    print("QUICK SETTINGS TEST")
    print("=" * 60)

    client = MCPClient("gnome-desktop-mcp")

    # Enable automation first
    print("\n[1] Enabling automation...")
    try:
        result = client.call_tool("set_enabled", {"enabled": True})
        print(f"    Result: {result}")
    except Exception as e:
        print(f"    Error: {e}")

    # Test 1: Toggle Dark Style on
    print("\n[2] Testing dark style ON...")
    try:
        result = client.call_tool("quick_settings", {
            "setting": "dark_style",
            "enabled": True
        })
        print(f"    Result: {result}")
    except Exception as e:
        print(f"    Error: {e}")

    input("\n    Press Enter to continue (check if dark mode is on)...")

    # Test 2: Toggle Dark Style off
    print("\n[3] Testing dark style OFF...")
    try:
        result = client.call_tool("quick_settings", {
            "setting": "dark_style",
            "enabled": False
        })
        print(f"    Result: {result}")
    except Exception as e:
        print(f"    Error: {e}")

    input("\n    Press Enter to continue (check if dark mode is off)...")

    # Test 3: Toggle Night Light on
    print("\n[4] Testing night light ON...")
    try:
        result = client.call_tool("quick_settings", {
            "setting": "night_light",
            "enabled": True
        })
        print(f"    Result: {result}")
    except Exception as e:
        print(f"    Error: {e}")

    input("\n    Press Enter to continue (check if screen is warmer)...")

    # Test 4: Toggle Night Light off
    print("\n[5] Testing night light OFF...")
    try:
        result = client.call_tool("quick_settings", {
            "setting": "night_light",
            "enabled": False
        })
        print(f"    Result: {result}")
    except Exception as e:
        print(f"    Error: {e}")

    # Test 5: Toggle Do Not Disturb on
    print("\n[6] Testing Do Not Disturb ON...")
    try:
        result = client.call_tool("quick_settings", {
            "setting": "do_not_disturb",
            "enabled": True
        })
        print(f"    Result: {result}")
    except Exception as e:
        print(f"    Error: {e}")

    input("\n    Press Enter to continue (notifications should be blocked)...")

    # Test 6: Toggle Do Not Disturb off
    print("\n[7] Testing Do Not Disturb OFF...")
    try:
        result = client.call_tool("quick_settings", {
            "setting": "do_not_disturb",
            "enabled": False
        })
        print(f"    Result: {result}")
    except Exception as e:
        print(f"    Error: {e}")

    # Test 7: Test WiFi (optional - be careful!)
    print("\n[8] Testing WiFi toggle...")
    print("    ⚠️  WARNING: This will disconnect your WiFi!")

    if sys.stdin.isatty():
        response = input("    Continue with WiFi test? (y/N): ")
        if response.lower() == 'y':
            print("\n    Disabling WiFi...")
            try:
                result = client.call_tool("quick_settings", {
                    "setting": "wifi",
                    "enabled": False
                })
                print(f"    Result: {result}")
            except Exception as e:
                print(f"    Error: {e}")

            input("\n    Press Enter to re-enable WiFi...")

            print("\n    Enabling WiFi...")
            try:
                result = client.call_tool("quick_settings", {
                    "setting": "wifi",
                    "enabled": True
                })
                print(f"    Result: {result}")
            except Exception as e:
                print(f"    Error: {e}")
        else:
            print("    SKIPPED")
    else:
        print("    SKIPPED (non-interactive mode)")

    # Test 8: Test Bluetooth (optional)
    print("\n[9] Testing Bluetooth toggle...")
    print("    ⚠️  WARNING: This will disconnect Bluetooth devices!")

    if sys.stdin.isatty():
        response = input("    Continue with Bluetooth test? (y/N): ")
        if response.lower() == 'y':
            print("\n    Disabling Bluetooth...")
            try:
                result = client.call_tool("quick_settings", {
                    "setting": "bluetooth",
                    "enabled": False
                })
                print(f"    Result: {result}")
            except Exception as e:
                print(f"    Error: {e}")

            input("\n    Press Enter to re-enable Bluetooth...")

            print("\n    Enabling Bluetooth...")
            try:
                result = client.call_tool("quick_settings", {
                    "setting": "bluetooth",
                    "enabled": True
                })
                print(f"    Result: {result}")
            except Exception as e:
                print(f"    Error: {e}")
        else:
            print("    SKIPPED")
    else:
        print("    SKIPPED (non-interactive mode)")

    print("\n" + "=" * 60)
    print("✅ Quick settings tests completed!")
    print("=" * 60)


if __name__ == "__main__":
    print("\n⚠️  This will toggle system settings.")
    print("    Dark mode, Night Light, and Do Not Disturb will be toggled.\n")

    if sys.stdin.isatty():
        input("Press Enter to start testing...")
    else:
        print("Running non-interactively...\n")

    test_quick_settings()
