#!/usr/bin/env python3
"""
Benchmark different token limits for vision description
Compare speed vs quality tradeoff
"""

import sys
import time
import base64
import ollama

sys.path.insert(0, '/home/jprajzne/anthony')
from mcp_client import MCPClient


def take_screenshot() -> str:
    """Take a screenshot and return base64 encoded data."""
    print("[SYSTEM] Taking screenshot...")
    client = MCPClient("gnome-desktop-mcp")

    result = client.call_tool("screenshot", {"include_cursor": False, "format": "path"})
    if result.startswith("Error"):
        raise Exception(f"Screenshot failed: {result}")

    screenshot_path = result.strip()
    print(f"[SYSTEM] Screenshot saved: {screenshot_path}")

    with open(screenshot_path, 'rb') as img_file:
        img_data = base64.b64encode(img_file.read()).decode('utf-8')

    file_size_kb = len(img_data) / 1024
    print(f"[SYSTEM] Image size: {file_size_kb:.1f} KB\n")

    return img_data


def test_token_limit(image_data: str, num_predict: int, num_ctx: int = 2048) -> dict:
    """Test vision with specific token limit."""
    print(f"{'='*70}")
    print(f"Testing: num_predict={num_predict}, num_ctx={num_ctx}")
    print(f"{'='*70}")

    system_prompt = "You are a screen reader for visually impaired users. Describe what you see in plain text without any formatting. Do not use markdown, asterisks, or special characters. Answer directly without explaining your reasoning process."

    start_time = time.time()

    response = ollama.chat(
        model='gemma4:e4b',
        messages=[
            {
                'role': 'system',
                'content': system_prompt
            },
            {
                'role': 'user',
                'content': 'What applications and windows are visible on this desktop screenshot?',
                'images': [image_data]
            }
        ],
        options={
            'num_ctx': num_ctx,
            'num_predict': num_predict,
            'temperature': 0.7,
            'num_gpu': 99,
        }
    )

    elapsed_time = time.time() - start_time

    message = response.message if hasattr(response, 'message') else response['message']
    description = message.content if hasattr(message, 'content') else message.get('content', '')

    print(f"\n⏱️  Time: {elapsed_time:.2f}s")
    print(f"📊 Stats: {len(description)} chars, ~{len(description.split())} words")
    print(f"\n📝 Response:")
    print("-" * 70)
    print(description)
    print("-" * 70)

    # Check for truncation indicators
    truncated = description.endswith('...') or len(description) < 50

    return {
        'num_predict': num_predict,
        'num_ctx': num_ctx,
        'time': elapsed_time,
        'response': description,
        'length': len(description),
        'words': len(description.split()),
        'truncated': truncated
    }


def main():
    """Run token limit comparison."""
    print("\n" + "="*70)
    print("TOKEN LIMIT BENCHMARK: Speed vs Quality")
    print("="*70 + "\n")

    # Take screenshot once
    image_data = take_screenshot()

    # Test different token limits
    configs = [
        {'num_predict': 800, 'num_ctx': 2048, 'label': 'Current (800 tokens)'},
        {'num_predict': 500, 'num_ctx': 2048, 'label': 'Medium (500 tokens)'},
        {'num_predict': 300, 'num_ctx': 2048, 'label': 'Reduced (300 tokens)'},
        {'num_predict': 200, 'num_ctx': 1024, 'label': 'Minimal (200 tokens, 1k ctx)'},
    ]

    results = []

    for config in configs:
        result = test_token_limit(
            image_data,
            num_predict=config['num_predict'],
            num_ctx=config['num_ctx']
        )
        result['label'] = config['label']
        results.append(result)
        print("\n\n")

    # Summary comparison
    print("="*70)
    print("COMPARISON SUMMARY")
    print("="*70)

    print(f"\n{'Configuration':<30} {'Time':<10} {'Words':<8} {'Speedup':<10} {'Quality'}")
    print("-" * 70)

    baseline_time = results[0]['time']

    for result in results:
        speedup = baseline_time / result['time']
        speedup_str = f"{speedup:.2f}x" if speedup != 1.0 else "baseline"
        quality = "⚠️ truncated" if result['truncated'] else "✓ complete"

        print(f"{result['label']:<30} {result['time']:>6.2f}s  {result['words']:>6}  {speedup_str:<10} {quality}")

    # Find optimal
    print("\n" + "="*70)
    print("RECOMMENDATION")
    print("="*70)

    # Find fastest complete response
    complete_results = [r for r in results if not r['truncated']]
    if complete_results:
        optimal = min(complete_results, key=lambda r: r['time'])
        speedup = baseline_time / optimal['time']
        time_saved = baseline_time - optimal['time']

        print(f"\n🏆 OPTIMAL: {optimal['label']}")
        print(f"   Time: {optimal['time']:.2f}s (saves {time_saved:.2f}s)")
        print(f"   Speedup: {speedup:.2f}x faster than current")
        print(f"   Quality: Complete description ({optimal['words']} words)")
    else:
        print("\n⚠️  All descriptions were truncated. Stick with current 800 tokens.")

    print("="*70 + "\n")


if __name__ == "__main__":
    main()
