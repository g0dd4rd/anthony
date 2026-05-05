#!/usr/bin/env python3
"""
Benchmark different vision models for screenshot analysis speed
"""
import time
import base64
import ollama
import os
import sys
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
import asyncio

async def capture_screenshot():
    """Capture a screenshot using MCP"""
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

def test_model(model_name: str, screenshot_path: str, prompt: str):
    """Test a single model and return timing + output"""
    print(f"\n{'='*60}")
    print(f"Testing: {model_name}")
    print(f"{'='*60}")

    try:
        # Load image
        with open(screenshot_path, 'rb') as img_file:
            img_data = base64.b64encode(img_file.read()).decode('utf-8')

        # Time the analysis
        start_time = time.time()

        response = ollama.chat(
            model=model_name,
            messages=[{
                'role': 'user',
                'content': prompt,
                'images': [img_data]
            }],
            options={
                'num_ctx': 2048,
                'temperature': 0.3
            }
        )

        end_time = time.time()
        elapsed = end_time - start_time

        description = response['message']['content']
        word_count = len(description.split())

        print(f"\n⏱️  Time: {elapsed:.2f} seconds")
        print(f"📝 Words: {word_count}")
        print(f"📄 Description:\n{description[:200]}...")

        return {
            'model': model_name,
            'time': elapsed,
            'words': word_count,
            'description': description
        }

    except Exception as e:
        print(f"❌ Error: {e}")
        return None

def main():
    print("🔬 Vision Model Speed Benchmark")
    print("=" * 60)

    # Capture screenshot
    print("\n📸 Capturing screenshot...")
    screenshot_path = asyncio.run(capture_screenshot())
    print(f"✅ Screenshot saved: {screenshot_path}")

    # Test prompts
    verbose_prompt = "Describe what you see in this screenshot in detail."
    concise_prompt = "Describe this screenshot in 2-3 sentences. Focus on: open applications, visible windows, and key UI elements. Be concise."

    # Models to test
    models_to_test = [
        ('gemma4:e4b', verbose_prompt, "Original (Gemma4 + verbose)"),
        ('gemma4:e4b', concise_prompt, "Gemma4 + concise prompt"),
        ('minicpm-v:8b-2.6-q4_K_M', concise_prompt, "Improved (MiniCPM-V + concise)"),
    ]

    # Optional faster models if available
    try:
        ollama.show('moondream:1.8b-v2-q4_K_M')
        models_to_test.append(('moondream:1.8b-v2-q4_K_M', concise_prompt, "Fastest (Moondream)"))
    except:
        print("\n💡 Tip: Install moondream for even faster results:")
        print("   ollama pull moondream:1.8b-v2-q4_K_M")

    try:
        ollama.show('llava:7b-v1.6-mistral-q4_K_M')
        models_to_test.append(('llava:7b-v1.6-mistral-q4_K_M', concise_prompt, "Alternative (LLaVA)"))
    except:
        print("💡 Tip: Install llava for balanced speed/quality:")
        print("   ollama pull llava:7b-v1.6-mistral-q4_K_M")

    # Run tests
    results = []
    for model, prompt, description in models_to_test:
        try:
            result = test_model(model, screenshot_path, prompt)
            if result:
                result['description_label'] = description
                results.append(result)
        except KeyboardInterrupt:
            print("\n\n⚠️  Benchmark interrupted by user")
            break
        except Exception as e:
            print(f"\n❌ Failed to test {model}: {e}")

    # Summary
    if results:
        print("\n" + "=" * 60)
        print("📊 BENCHMARK RESULTS SUMMARY")
        print("=" * 60)

        # Sort by speed
        results.sort(key=lambda x: x['time'])

        print(f"\n{'Model':<40} {'Time':<10} {'Words':<8}")
        print("-" * 60)

        fastest_time = results[0]['time']

        for r in results:
            speedup = fastest_time / r['time']
            speedup_str = f"({speedup:.1f}x)" if speedup < 1 else ""
            print(f"{r['description_label']:<40} {r['time']:.2f}s {speedup_str:<6} {r['words']:<8}")

        print("\n✅ Recommendation:")
        print(f"   Use: {results[0]['description_label']}")
        print(f"   Speed: {results[0]['time']:.2f}s")
        print(f"   Description length: {results[0]['words']} words")

        if len(results) > 1:
            improvement = (results[-1]['time'] - results[0]['time']) / results[-1]['time'] * 100
            print(f"\n🚀 Improvement: {improvement:.1f}% faster than original")

    # Cleanup
    try:
        os.remove(screenshot_path)
    except:
        pass

if __name__ == "__main__":
    main()
