#!/usr/bin/env python3
"""
Simplest possible vision test with gemma4.
"""

import ollama
import base64
import subprocess

print("Creating a simple test image...")

# Create a simple colored image with text
subprocess.run([
    'convert', '-size', '400x200', '-background', 'lightblue',
    '-fill', 'black', '-pointsize', '40', '-gravity', 'center',
    'label:HELLO WORLD', '/tmp/simple_test.png'
], check=False)

print("Loading image...")
with open('/tmp/simple_test.png', 'rb') as f:
    img_data = base64.b64encode(f.read()).decode('utf-8')

print(f"Image size: {len(img_data) / 1024:.1f} KB")

print("\nTest 1: Simple prompt")
print("-" * 60)

response = ollama.chat(
    model='gemma4:e4b',
    messages=[{
        'role': 'user',
        'content': 'What text do you see in this image?',
        'images': [img_data]
    }]
)

content = response['message']['content']
print(f"Response: '{content}'")
print(f"Length: {len(content)}")

print("\n\nTest 2: Same prompt as orchestrator")
print("-" * 60)

response2 = ollama.chat(
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

content2 = response2['message']['content']
print(f"Response: '{content2}'")
print(f"Length: {len(content2)}")

print("\n\nTest 3: No options")
print("-" * 60)

response3 = ollama.chat(
    model='gemma4:e4b',
    messages=[{
        'role': 'user',
        'content': 'Describe this image.',
        'images': [img_data]
    }]
)

content3 = response3['message']['content']
print(f"Response: '{content3}'")
print(f"Length: {len(content3)}")

if not content or not content2 or not content3:
    print("\n⚠️  WARNING: Some responses are empty!")
    print("\nFull response objects:")
    print("\nTest 1:", response)
    print("\nTest 2:", response2)
    print("\nTest 3:", response3)
else:
    print("\n✅ All tests returned content!")
