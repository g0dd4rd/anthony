#!/usr/bin/env python3
"""
Direct test of gemma4 vision without the orchestrator.
Use this to diagnose vision analysis issues.
"""

import ollama
import base64
import sys
import os
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
import asyncio

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

def test_ollama_text():
    """Test if ollama works with text"""
    print("\n" + "="*60)
    print("TEST 1: Ollama Text Generation")
    print("="*60)

    try:
        print("Sending text request to gemma4...")
        response = ollama.chat(
            model='gemma4:e4b',
            messages=[{'role': 'user', 'content': 'Say "hello" and nothing else.'}],
            options={'num_predict': 10}
        )

        result = response['message']['content']
        print(f"✅ Response: {result}")
        return True

    except Exception as e:
        print(f"❌ Error: {e}")
        return False

def test_ollama_vision(screenshot_path):
    """Test if ollama vision works"""
    print("\n" + "="*60)
    print("TEST 2: Ollama Vision Analysis")
    print("="*60)

    try:
        print(f"Loading screenshot: {screenshot_path}")

        if not os.path.exists(screenshot_path):
            print(f"❌ Screenshot not found: {screenshot_path}")
            return False

        file_size_mb = os.path.getsize(screenshot_path) / (1024 * 1024)
        print(f"📦 File size: {file_size_mb:.2f} MB")

        with open(screenshot_path, 'rb') as img_file:
            img_data = base64.b64encode(img_file.read()).decode('utf-8')

        encoded_size_kb = len(img_data) / 1024
        print(f"📦 Encoded size: {encoded_size_kb:.1f} KB")

        print("🤖 Sending to gemma4 vision model...")
        print("⏳ This may take 2-10 seconds on first run (loading model)...")

        import time
        start_time = time.time()

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

        elapsed = time.time() - start_time

        description = response['message']['content']
        print(f"\n✅ Vision analysis complete! ({elapsed:.1f} seconds)")
        print(f"\n📝 Description:")
        print(f"   {description}")

        return True

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False

def check_ollama_service():
    """Check if ollama service is running"""
    print("\n" + "="*60)
    print("PRE-CHECK: Ollama Service Status")
    print("="*60)

    import subprocess

    try:
        # Check if ollama is running
        result = subprocess.run(['ollama', 'list'], capture_output=True, text=True, timeout=5)

        if result.returncode == 0:
            print("✅ Ollama service is running")
            print("\nInstalled models:")
            print(result.stdout)

            # Check for gemma4
            if 'gemma4:e4b' in result.stdout:
                print("✅ gemma4:e4b model found")
                return True
            else:
                print("⚠️  gemma4:e4b model NOT found")
                print("   Run: ollama pull gemma4:e4b")
                return False
        else:
            print("❌ Ollama service not responding")
            return False

    except FileNotFoundError:
        print("❌ ollama command not found")
        print("   Is ollama installed?")
        return False
    except subprocess.TimeoutExpired:
        print("❌ ollama command timed out")
        print("   Ollama service might be stuck")
        return False
    except Exception as e:
        print(f"❌ Error checking ollama: {e}")
        return False

def main():
    print("🔬 GEMMA4 VISION DIAGNOSTIC TEST")
    print("="*60)

    # Check ollama service
    if not check_ollama_service():
        print("\n⚠️  Please fix ollama service before continuing")
        sys.exit(1)

    # Test text generation
    if not test_ollama_text():
        print("\n⚠️  Ollama text generation failed")
        print("   Vision will also fail")
        sys.exit(1)

    # Capture screenshot
    print("\n" + "="*60)
    print("SETUP: Capturing Screenshot")
    print("="*60)

    try:
        screenshot_path = asyncio.run(capture_screenshot())
        print(f"✅ Screenshot captured: {screenshot_path}")
    except Exception as e:
        print(f"❌ Screenshot capture failed: {e}")
        print("   Using fallback path (if exists)")
        screenshot_path = "/tmp/test_screenshot.png"

    # Test vision
    if not test_ollama_vision(screenshot_path):
        print("\n❌ Vision test failed")
        sys.exit(1)

    print("\n" + "="*60)
    print("✅ ALL TESTS PASSED!")
    print("="*60)
    print("\nVision analysis is working correctly.")
    print("If the orchestrator still has issues, check:")
    print("  1. Tool is being called (add debug output)")
    print("  2. Function result is being returned")
    print("  3. Result is being spoken via TTS")

if __name__ == "__main__":
    main()
