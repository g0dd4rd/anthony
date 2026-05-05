#!/usr/bin/env python3
"""
Benchmark vision models: llama3.2-vision:11b vs gemma4:e4b
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


def test_model(model_name: str, image_data: str, prompt: str) -> dict:
    """Test a vision model and return timing + response."""
    print(f"{'='*70}")
    print(f"Testing: {model_name}")
    print(f"{'='*70}")

    system_prompt = "You are a screen reader for visually impaired users. Describe what you see in plain text without any formatting. Do not use markdown, asterisks, or special characters. Answer directly without explaining your reasoning process."

    start_time = time.time()

    response = ollama.chat(
        model=model_name,
        messages=[
            {
                'role': 'system',
                'content': system_prompt
            },
            {
                'role': 'user',
                'content': prompt,
                'images': [image_data]
            }
        ],
        options={
            'num_ctx': 2048,
            'num_predict': 800,
            'temperature': 0.7,
            'num_gpu': 99,
        }
    )

    elapsed_time = time.time() - start_time

    message = response.message if hasattr(response, 'message') else response['message']
    description = message.content if hasattr(message, 'content') else message.get('content', '')

    print(f"\n⏱️  Time: {elapsed_time:.2f}s")
    print(f"\n📝 Response ({len(description)} chars):")
    print("-" * 70)
    print(description)
    print("-" * 70)

    return {
        'model': model_name,
        'time': elapsed_time,
        'response': description,
        'length': len(description)
    }


def main():
    """Run benchmark comparison."""
    print("\n" + "="*70)
    print("VISION MODEL BENCHMARK: llama3.2-vision:11b vs gemma4:e4b")
    print("="*70 + "\n")

    # Take screenshot once
    image_data = take_screenshot()

    # Same prompt for both
    prompt = "What applications and windows are visible on this desktop screenshot?"

    # Test both models
    results = []

    # Test gemma4 first (baseline)
    gemma_result = test_model("gemma4:e4b", image_data, prompt)
    results.append(gemma_result)

    print("\n\n")

    # Test llama3.2-vision
    llama_result = test_model("llama3.2-vision:11b", image_data, prompt)
    results.append(llama_result)

    # Summary comparison
    print("\n\n" + "="*70)
    print("COMPARISON SUMMARY")
    print("="*70)

    print(f"\n{'Model':<25} {'Time':<12} {'Response Length':<20} {'Speedup'}")
    print("-" * 70)

    baseline_time = gemma_result['time']

    for result in results:
        speedup = baseline_time / result['time']
        speedup_str = f"{speedup:.2f}x" if speedup != 1.0 else "baseline"

        print(f"{result['model']:<25} {result['time']:>6.2f}s      {result['length']:>6} chars       {speedup_str}")

    # Winner determination
    print("\n" + "="*70)
    if llama_result['time'] < gemma_result['time']:
        speedup = gemma_result['time'] / llama_result['time']
        improvement = ((gemma_result['time'] - llama_result['time']) / gemma_result['time']) * 100
        print(f"🏆 WINNER: llama3.2-vision:11b")
        print(f"   {speedup:.2f}x faster ({improvement:.1f}% improvement)")
    else:
        print(f"🏆 WINNER: gemma4:e4b (faster)")

    print("="*70 + "\n")


if __name__ == "__main__":
    main()
