#!/usr/bin/env python3
"""
Debug script to see exactly what gemma4 returns for vision analysis.
"""

import ollama
import base64
import sys
import json
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
import asyncio
import os

async def capture_screenshot():
    """Capture a screenshot using MCP"""
    print("📸 Capturing screenshot...")

    server_params = StdioServerParameters(
        command="gnome-desktop-mcp",
        args=[],
        env=os.environ.copy()
    )

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool("screenshot", arguments={"include_cursor": False, "format": "path"})
            return result.content[0].text.strip()

def main():
    print("🔍 GEMMA4 VISION RESPONSE DEBUGGER")
    print("="*60)

    # Capture screenshot
    try:
        screenshot_path = asyncio.run(capture_screenshot())
        print(f"✅ Screenshot: {screenshot_path}\n")
    except Exception as e:
        print(f"❌ Screenshot failed: {e}")
        sys.exit(1)

    # Load image
    print("📊 Loading screenshot...")
    with open(screenshot_path, 'rb') as img_file:
        img_data = base64.b64encode(img_file.read()).decode('utf-8')

    file_size_kb = len(img_data) / 1024
    print(f"📦 Encoded size: {file_size_kb:.1f} KB\n")

    # Call gemma4 vision
    print("🤖 Sending to gemma4:e4b...")
    print("⏳ Please wait...\n")

    try:
        response = ollama.chat(
            model='gemma4:e4b',
            messages=[{
                'role': 'user',
                'content': 'Describe this screenshot in 2-3 sentences. Focus on: open applications, visible windows, and key UI elements. Be concise.',
                'images': [img_data]
            }],
            options={
                'num_ctx': 2048,
                'num_predict': 100,
                'temperature': 0.3,
                'num_gpu': 99,
            }
        )

        print("="*60)
        print("FULL RESPONSE OBJECT:")
        print("="*60)
        print(json.dumps(response, indent=2, default=str))
        print()

        print("="*60)
        print("RESPONSE BREAKDOWN:")
        print("="*60)
        print(f"Type: {type(response)}")
        print(f"Keys: {list(response.keys())}")
        print()

        if 'message' in response:
            print("MESSAGE object:")
            print(f"  Type: {type(response['message'])}")
            print(f"  Keys: {list(response['message'].keys())}")
            print()

            if 'content' in response['message']:
                content = response['message']['content']
                print("CONTENT:")
                print(f"  Type: {type(content)}")
                print(f"  Length: {len(content) if content else 0}")
                print(f"  Value: '{content}'")
                print()

                if not content or content.strip() == "":
                    print("⚠️  WARNING: Content is EMPTY!")
                    print()
                    print("Possible causes:")
                    print("  1. Model didn't generate any output")
                    print("  2. num_predict too low (currently 100)")
                    print("  3. Image wasn't processed correctly")
                    print("  4. Model error/failure")
                else:
                    print("✅ Content looks good!")
            else:
                print("❌ No 'content' key in message!")
        else:
            print("❌ No 'message' key in response!")

        print()
        print("="*60)

    except Exception as e:
        print(f"❌ Error calling ollama: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
