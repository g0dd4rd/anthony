#!/usr/bin/env python3
"""
Test wallpaper search by color and name
"""

import sys
sys.path.insert(0, '/home/jprajzne/anthony')
sys.path.insert(0, '/home/jprajzne/gnome-desktop-mcp/mcp-server/src')

from gnome_desktop_mcp import wallpaper_index
from mcp_client import MCPClient


def test_indexing():
    """Test wallpaper indexing"""
    print("=" * 60)
    print("WALLPAPER INDEXING TEST")
    print("=" * 60)

    wallpapers = wallpaper_index.index_wallpapers()
    print(f"\n✓ Found {len(wallpapers)} wallpapers\n")

    # Show first 10
    for i, wp in enumerate(wallpapers[:10]):
        print(f"{i+1}. {wp['name']:30} [{wp['color'] or 'unknown':12}] {wp['path']}")

    if len(wallpapers) > 10:
        print(f"... and {len(wallpapers) - 10} more")


def test_color_search():
    """Test searching by color"""
    print("\n" + "=" * 60)
    print("COLOR SEARCH TEST")
    print("=" * 60)

    test_colors = ['red', 'blue', 'green', 'orange', 'purple', 'gray', 'black']

    for color in test_colors:
        result = wallpaper_index.search_wallpaper_by_color(color)
        if result:
            print(f"\n{color:10} → {result}")
        else:
            print(f"\n{color:10} → Not found")


def test_name_search():
    """Test searching by name"""
    print("\n" + "=" * 60)
    print("NAME SEARCH TEST")
    print("=" * 60)

    test_names = ['fedora', 'adwaita', 'default', 'amber']

    for name in test_names:
        result = wallpaper_index.search_wallpaper_by_name(name)
        if result:
            print(f"\n{name:10} → {result}")
        else:
            print(f"\n{name:10} → Not found")


def test_mcp_integration():
    """Test MCP set_wallpaper with color/name"""
    print("\n" + "=" * 60)
    print("MCP INTEGRATION TEST")
    print("=" * 60)

    client = MCPClient("gnome-desktop-mcp")

    # Test 1: Set by color
    print("\n[1] Testing set_wallpaper with color: 'blue'")
    try:
        result = client.call_tool("set_wallpaper", {"image_path": "blue"})
        print(f"    Result: {result}")
    except Exception as e:
        print(f"    Error: {e}")

    # Test 2: Set by name
    print("\n[2] Testing set_wallpaper with name: 'fedora'")
    try:
        result = client.call_tool("set_wallpaper", {"image_path": "fedora"})
        print(f"    Result: {result}")
    except Exception as e:
        print(f"    Error: {e}")

    # Test 3: Set by file path (should still work)
    print("\n[3] Testing set_wallpaper with path: '/usr/share/backgrounds/gnome/adwaita-l.jxl'")
    try:
        result = client.call_tool("set_wallpaper", {"image_path": "/usr/share/backgrounds/gnome/adwaita-l.jxl"})
        print(f"    Result: {result}")
    except Exception as e:
        print(f"    Error: {e}")


if __name__ == "__main__":
    test_indexing()
    test_color_search()
    test_name_search()
    test_mcp_integration()

    print("\n" + "=" * 60)
    print("✅ Wallpaper search tests completed!")
    print("=" * 60)
