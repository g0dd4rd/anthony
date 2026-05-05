#!/usr/bin/env python3
"""
Test key_combo functionality with gnome-desktop-mcp
"""

import asyncio
import os
import time
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

async def test_key_combo():
    server_params = StdioServerParameters(
        command="gnome-desktop-mcp",
        args=[],
        env=os.environ.copy()
    )

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            print("="*60)
            print("Testing key_combo with Text Editor")
            print("="*60)
            print()

            # Step 1: Open text editor
            print("Step 1: Opening text editor...")
            print("Please open gnome-text-editor manually and focus it.")
            print()
            input("Press Enter when text editor is open and focused...")

            # Step 2: Type some text
            print("\nStep 2: Typing test text...")
            result = await session.call_tool("type_text", arguments={"text": "Hello World - Testing Ctrl+s"})
            print(f"Result: {result.content[0].text}")
            time.sleep(0.5)

            # Step 3: Try different Ctrl+s variations
            test_combos = [
                "Ctrl+s",      # Standard format
                "Ctrl+S",      # Uppercase S
                "Control+s",   # Full "Control"
                "Control+S",   # Full "Control" + uppercase
            ]

            for combo in test_combos:
                print(f"\n{'='*60}")
                print(f"Testing: {combo}")
                print(f"{'='*60}")

                # Small delay before
                time.sleep(0.2)

                print(f"Sending key combo: {combo}")
                result = await session.call_tool("key_combo", arguments={"keys": combo})
                print(f"MCP Result: {result.content[0].text}")

                # Wait to see if save dialog appears
                print("Waiting 2 seconds... Check if save dialog appeared!")
                time.sleep(2)

                response = input("Did save dialog appear? (y/n): ").strip().lower()

                if response == 'y':
                    print(f"✅ SUCCESS! Working format: {combo}")
                    print("\nDismissing dialog with Escape...")
                    await session.call_tool("key_press", arguments={"key": "Escape"})
                    time.sleep(0.5)
                    break
                else:
                    print(f"❌ FAILED: {combo}")
                    continue
            else:
                print("\n" + "="*60)
                print("❌ None of the formats worked!")
                print("="*60)

            print("\nTest complete.")

if __name__ == "__main__":
    asyncio.run(test_key_combo())
