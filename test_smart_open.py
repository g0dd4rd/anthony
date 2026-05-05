#!/usr/bin/env python3
"""
Test smart open_file and open_url functionality
"""

import sys
sys.path.insert(0, '/home/jprajzne/anthony')

from mcp_client import MCPClient


def test_smart_open():
    """Test smart open functions"""
    print("=" * 60)
    print("SMART OPEN TEST")
    print("=" * 60)

    client = MCPClient("gnome-desktop-mcp")

    # Test 1: Open URL (no https://)
    print("\n[1] Testing open_url with 'google.com'...")
    try:
        result = client.call_tool("open_url", {"url": "google.com"})
        print(f"    Result: {result}")
    except Exception as e:
        print(f"    Error: {e}")

    if sys.stdin.isatty():
        input("\n    Press Enter to continue...")

    # Test 2: Open file by search (just filename)
    print("\n[2] Testing open_file with just 'screenshot.png'...")
    try:
        result = client.call_tool("open_file", {"path": "screenshot.png"})
        print(f"    Result: {result}")
    except Exception as e:
        print(f"    Error: {e}")

    if sys.stdin.isatty():
        input("\n    Press Enter to continue...")

    # Test 3: Open file with search_location
    print("\n[3] Testing open_file with 'screenshot.png' in 'Pictures'...")
    try:
        result = client.call_tool("open_file", {
            "path": "screenshot.png",
            "search_location": "Pictures"
        })
        print(f"    Result: {result}")
    except Exception as e:
        print(f"    Error: {e}")

    if sys.stdin.isatty():
        input("\n    Press Enter to continue...")

    # Test 4: Open with full path (direct open)
    print("\n[4] Testing open_file with full path '~/Pictures/Screenshot.png'...")
    try:
        result = client.call_tool("open_file", {
            "path": "~/Pictures/Screenshot.png"
        })
        print(f"    Result: {result}")
    except Exception as e:
        print(f"    Error: {e}")

    print("\n" + "=" * 60)
    print("✅ Smart open tests completed!")
    print("=" * 60)


if __name__ == "__main__":
    print("\n⚠️  This will open URLs and files.")
    print("    Browser and applications will launch.\n")

    if sys.stdin.isatty():
        input("Press Enter to start testing...")
    else:
        print("Running non-interactively...\n")

    test_smart_open()
