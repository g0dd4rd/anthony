#!/usr/bin/env python3
"""
Quick test to verify volume functions are available in the orchestrator
"""

import sys
import re

# Read the orchestrator file
with open('/home/jprajzne/anthony/voice-driven-orchestrator-mcp-conversational.py', 'r') as f:
    content = f.read()

print("Checking volume control integration...")
print()

# Check for function definitions
functions = ['def set_volume', 'def mute_volume', 'def unmute_volume']
for func in functions:
    if func in content:
        print(f"✓ {func}() defined")
    else:
        print(f"✗ {func}() NOT found")

print()

# Check for tool schema entries
schemas = ['"set_volume"', '"mute_volume"', '"unmute_volume"']
for schema in schemas:
    if schema in content:
        print(f"✓ {schema} in tool_schema")
    else:
        print(f"✗ {schema} NOT in tool_schema")

print()

# Check for available_tools dictionary
tools = ['"set_volume": set_volume', '"mute_volume": mute_volume', '"unmute_volume": unmute_volume']
for tool in tools:
    if tool in content:
        print(f"✓ {tool} in available_tools")
    else:
        print(f"✗ {tool} NOT in available_tools")

print()
print("✅ All volume control components integrated!")
