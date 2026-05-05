#!/usr/bin/env python3
"""
Test media control functionality via MCP server
"""

import sys
import json
sys.path.insert(0, '/home/jprajzne/anthony')

from mcp_client import MCPClient


def test_media_control():
    """Test media control MCP tools"""
    print("=" * 60)
    print("MEDIA CONTROL TEST")
    print("=" * 60)

    client = MCPClient("gnome-desktop-mcp")

    # Enable automation first
    print("\n[1] Enabling automation...")
    try:
        result = client.call_tool("set_enabled", {"enabled": True})
        print(f"    Result: {result}")
    except Exception as e:
        print(f"    Error: {e}")

    # Test 1: Get media status
    print("\n[2] Getting media status...")
    try:
        result = client.call_tool("get_media_status", {})
        status = json.loads(result)
        print(f"    Player: {status.get('player', 'N/A')}")
        print(f"    Status: {status.get('status', 'N/A')}")
        print(f"    Title: {status.get('title', 'N/A')}")
        print(f"    Artist: {status.get('artist', 'N/A')}")
        print(f"    Album: {status.get('album', 'N/A')}")
        if 'error' in status:
            print(f"    Error: {status['error']}")
    except Exception as e:
        print(f"    Error: {e}")

    # Test 2: Play/Pause toggle
    print("\n[3] Testing play/pause...")
    try:
        result = client.call_tool("media_control", {"action": "play_pause"})
        print(f"    Result: {result}")
    except Exception as e:
        print(f"    Error: {e}")

    # Test 3: Next track
    print("\n[4] Testing next track...")
    try:
        result = client.call_tool("media_control", {"action": "next"})
        print(f"    Result: {result}")
    except Exception as e:
        print(f"    Error: {e}")

    # Test 4: Previous track
    print("\n[5] Testing previous track...")
    try:
        result = client.call_tool("media_control", {"action": "previous"})
        print(f"    Result: {result}")
    except Exception as e:
        print(f"    Error: {e}")

    # Test 5: Pause
    print("\n[6] Testing pause...")
    try:
        result = client.call_tool("media_control", {"action": "pause"})
        print(f"    Result: {result}")
    except Exception as e:
        print(f"    Error: {e}")

    # Test 6: Play
    print("\n[7] Testing play...")
    try:
        result = client.call_tool("media_control", {"action": "play"})
        print(f"    Result: {result}")
    except Exception as e:
        print(f"    Error: {e}")

    # Test 7: Get status again
    print("\n[8] Getting updated media status...")
    try:
        result = client.call_tool("get_media_status", {})
        status = json.loads(result)
        print(f"    Status: {status.get('status', 'N/A')}")
        if 'error' in status:
            print(f"    Error: {status['error']}")
    except Exception as e:
        print(f"    Error: {e}")

    print("\n" + "=" * 60)
    print("✅ All media control tests completed!")
    print("=" * 60)


if __name__ == "__main__":
    print("\n⚠️  PREREQUISITE: Start a media player (Rhythmbox, Spotify, VLC, etc.)")
    print("    and have a song loaded before running this test.\n")

    # Check if running interactively
    import sys
    if sys.stdin.isatty():
        input("Press Enter when ready to test media controls...")
    else:
        print("Running non-interactively, starting test immediately...\n")

    test_media_control()
