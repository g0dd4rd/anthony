#!/usr/bin/env python3
"""
Test if the thinking field fix works.
"""

import ollama
import base64
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
import asyncio
import os

async def capture_screenshot():
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

print("="*60)
print("TESTING THINKING FIELD FIX")
print("="*60)

screenshot_path = asyncio.run(capture_screenshot())
print(f"✅ Screenshot: {screenshot_path}\n")

with open(screenshot_path, 'rb') as f:
    img_data = base64.b64encode(f.read()).decode('utf-8')

print("🤖 Testing NEW approach (with system message)...")

response = ollama.chat(
    model='gemma4:e4b',
    messages=[
        {
            'role': 'system',
            'content': 'You are a screen reader. Answer directly without explaining your reasoning process.'
        },
        {
            'role': 'user',
            'content': 'What applications and windows are visible on this desktop screenshot?',
            'images': [img_data]
        }
    ],
    options={
        'num_ctx': 2048,
        'num_predict': 300,
        'temperature': 0.7,
        'num_gpu': 99,
    }
)

message = response.message if hasattr(response, 'message') else response['message']
content = message.content if hasattr(message, 'content') else message.get('content', '')
thinking = message.thinking if hasattr(message, 'thinking') else message.get('thinking', '')

print(f"\n{'='*60}")
print(f"CONTENT field:")
print(f"{'='*60}")
print(f"Length: {len(content)}")
print(f"Value: '{content}'")

print(f"\n{'='*60}")
print(f"THINKING field:")
print(f"{'='*60}")
print(f"Length: {len(thinking) if thinking else 0}")
if thinking:
    print(f"First 200 chars: '{thinking[:200]}...'")
else:
    print("(empty)")

print(f"\n{'='*60}")
print(f"RESULT:")
print(f"{'='*60}")

if content and content.strip():
    print(f"✅ SUCCESS! Content field has text:")
    print(f"\n   {content}\n")
elif thinking and thinking.strip():
    print(f"⚠️  Content empty, but thinking has text.")
    print(f"   Extracting from thinking field...")
    lines = thinking.split('\n')
    description = ' '.join([l.strip() for l in lines[-3:] if l.strip() and not l.strip().startswith('*')])
    print(f"\n   Extracted: {description}\n")
else:
    print(f"❌ BOTH FIELDS EMPTY! Something is wrong.")

print(f"{'='*60}")
print(f"Done reason: {response.done_reason if hasattr(response, 'done_reason') else 'unknown'}")
print(f"Eval count: {response.eval_count if hasattr(response, 'eval_count') else 'unknown'}")
