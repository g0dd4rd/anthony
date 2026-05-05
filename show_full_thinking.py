#!/usr/bin/env python3
"""
Show the FULL thinking field to see if the description is in there.
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

screenshot_path = asyncio.run(capture_screenshot())
print(f"Screenshot: {screenshot_path}\n")

with open(screenshot_path, 'rb') as f:
    img_data = base64.b64encode(f.read()).decode('utf-8')

print("Testing with 1000 tokens (generous limit)...\n")

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
        'num_predict': 1000,  # Very generous
        'temperature': 0.7,
        'num_gpu': 99,
    }
)

message = response.message
content = message.content
thinking = message.thinking if hasattr(message, 'thinking') else ''

print("="*60)
print("CONTENT field:")
print("="*60)
print(f"Length: {len(content)}")
print(f"Value:\n{content}")

print("\n" + "="*60)
print("THINKING field (FULL):")
print("="*60)
print(f"Length: {len(thinking) if thinking else 0}")
if thinking:
    print(thinking)
    print("\n" + "="*60)
    print("Looking for the actual answer in thinking field...")
    print("="*60)

    # The answer is usually after "OUTPUT:" or at the very end
    if "OUTPUT:" in thinking:
        parts = thinking.split("OUTPUT:")
        print(f"\n✅ Found 'OUTPUT:' marker")
        print(f"Text after OUTPUT:\n{parts[-1][:500]}")
    elif "FINAL ANSWER:" in thinking:
        parts = thinking.split("FINAL ANSWER:")
        print(f"\n✅ Found 'FINAL ANSWER:' marker")
        print(f"Text after FINAL ANSWER:\n{parts[-1][:500]}")
    else:
        print(f"\n⚠️  No clear marker. Last 300 chars of thinking:")
        print(thinking[-300:])
else:
    print("(empty)")

print("\n" + "="*60)
print(f"Done reason: {response.done_reason}")
print(f"Eval count: {response.eval_count}")
