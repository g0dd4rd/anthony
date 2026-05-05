#!/usr/bin/env python3
"""
Test open_file functionality via MCP server
"""

import sys
import os
sys.path.insert(0, '/home/jprajzne/anthony')

from mcp_client import MCPClient


def test_open_file():
    """Test open_file MCP tool"""
    print("=" * 60)
    print("OPEN FILE TEST")
    print("=" * 60)

    client = MCPClient("gnome-desktop-mcp")

    # Enable automation first
    print("\n[1] Enabling automation...")
    try:
        result = client.call_tool("set_enabled", {"enabled": True})
        print(f"    Result: {result}")
    except Exception as e:
        print(f"    Error: {e}")

    # Test 1: Open a URL
    print("\n[2] Testing URL open (https://example.com)...")
    try:
        result = client.call_tool("open_file", {
            "path": "https://example.com"
        })
        print(f"    Result: {result}")
        print("    (Check if browser opened)")
    except Exception as e:
        print(f"    Error: {e}")

    if sys.stdin.isatty():
        input("\n    Press Enter to continue...")

    # Test 2: Create and open a test text file
    test_file = os.path.expanduser("~/test_document.txt")
    print(f"\n[3] Creating test file: {test_file}")
    with open(test_file, 'w') as f:
        f.write("This is a test document.\nOpened via MCP open_file tool.\n")
    print("    File created")

    print(f"\n[4] Testing file open ({test_file})...")
    try:
        result = client.call_tool("open_file", {
            "path": test_file
        })
        print(f"    Result: {result}")
        print("    (Check if text editor opened)")
    except Exception as e:
        print(f"    Error: {e}")

    if sys.stdin.isatty():
        input("\n    Press Enter to continue...")

    # Test 3: Test with ~ expansion
    print(f"\n[5] Testing path with ~ expansion (~/test_document.txt)...")
    try:
        result = client.call_tool("open_file", {
            "path": "~/test_document.txt"
        })
        print(f"    Result: {result}")
        print("    (Check if text editor opened)")
    except Exception as e:
        print(f"    Error: {e}")

    if sys.stdin.isatty():
        input("\n    Press Enter to continue...")

    # Test 4: Test with non-existent file
    print("\n[6] Testing non-existent file (should fail)...")
    try:
        result = client.call_tool("open_file", {
            "path": "/tmp/nonexistent_file_12345.txt"
        })
        print(f"    Result: {result}")
    except Exception as e:
        print(f"    Error (expected): {e}")

    # Cleanup
    print("\n[7] Cleaning up test file...")
    try:
        os.remove(test_file)
        print("    Test file removed")
    except:
        pass

    print("\n" + "=" * 60)
    print("✅ Open file tests completed!")
    print("=" * 60)


if __name__ == "__main__":
    print("\n⚠️  This will open files and URLs in their default applications.")
    print("    A browser window and text editor will open.\n")

    if sys.stdin.isatty():
        input("Press Enter to start testing...")
    else:
        print("Running non-interactively...\n")

    test_open_file()
