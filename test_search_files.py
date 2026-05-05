#!/usr/bin/env python3
"""
Test search_files functionality via MCP server
"""

import sys
import json
sys.path.insert(0, '/home/jprajzne/anthony')

from mcp_client import MCPClient


def test_search_files():
    """Test search_files MCP tool"""
    print("=" * 60)
    print("SEARCH FILES TEST")
    print("=" * 60)

    client = MCPClient("gnome-desktop-mcp")

    # Enable automation first
    print("\n[1] Enabling automation...")
    try:
        result = client.call_tool("set_enabled", {"enabled": True})
        print(f"    Result: {result}")
    except Exception as e:
        print(f"    Error: {e}")

    # Test 1: Search for screenshot files
    print("\n[2] Searching for 'screenshot' files...")
    try:
        result = client.call_tool("search_files", {
            "query": "screenshot",
            "file_type": "files",
            "limit": 5
        })
        data = json.loads(result)
        print(f"    Query: {data['query']}")
        print(f"    Found: {data['count']} results")
        for i, path in enumerate(data['results'], 1):
            print(f"      {i}. {path}")
    except Exception as e:
        print(f"    Error: {e}")

    # Test 2: Search for images
    print("\n[3] Searching for 'screenshot' images...")
    try:
        result = client.call_tool("search_files", {
            "query": "screenshot",
            "file_type": "images",
            "limit": 5
        })
        data = json.loads(result)
        print(f"    Query: {data['query']}")
        print(f"    Found: {data['count']} results")
        for i, path in enumerate(data['results'], 1):
            print(f"      {i}. {path}")
    except Exception as e:
        print(f"    Error: {e}")

    # Test 3: Search for documents
    print("\n[4] Searching for 'test' documents...")
    try:
        result = client.call_tool("search_files", {
            "query": "test",
            "file_type": "documents",
            "limit": 5
        })
        data = json.loads(result)
        print(f"    Query: {data['query']}")
        print(f"    Found: {data['count']} results")
        for i, path in enumerate(data['results'], 1):
            print(f"      {i}. {path}")
    except Exception as e:
        print(f"    Error: {e}")

    # Test 4: Search for folders
    print("\n[5] Searching for 'Pictures' folders...")
    try:
        result = client.call_tool("search_files", {
            "query": "Pictures",
            "file_type": "folders",
            "limit": 5
        })
        data = json.loads(result)
        print(f"    Query: {data['query']}")
        print(f"    Found: {data['count']} results")
        for i, path in enumerate(data['results'], 1):
            print(f"      {i}. {path}")
    except Exception as e:
        print(f"    Error: {e}")

    # Test 5: Search with limit
    print("\n[6] Searching for 'screenshot' with limit=2...")
    try:
        result = client.call_tool("search_files", {
            "query": "screenshot",
            "file_type": "files",
            "limit": 2
        })
        data = json.loads(result)
        print(f"    Query: {data['query']}")
        print(f"    Found: {data['count']} results (limited to 2)")
        for i, path in enumerate(data['results'], 1):
            print(f"      {i}. {path}")
    except Exception as e:
        print(f"    Error: {e}")

    print("\n" + "=" * 60)
    print("✅ Search files tests completed!")
    print("=" * 60)


if __name__ == "__main__":
    print("\n⚠️  This will search your indexed files using localsearch.")
    print("    Results depend on what's in your GNOME file index.\n")

    if sys.stdin.isatty():
        input("Press Enter to start testing...")
    else:
        print("Running non-interactively...\n")

    test_search_files()
