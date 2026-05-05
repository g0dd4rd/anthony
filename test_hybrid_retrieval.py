#!/usr/bin/env python3
"""
Test the hybrid namespace + retrieval system
"""

import sys
sys.path.insert(0, '/home/jprajzne/anthony')

# Import just the retrieval components
from sentence_transformers import SentenceTransformer
import torch

# Define namespaces (same as in orchestrator)
namespaces = {
    "app": {
        "description": "Launching applications, managing installed apps, application control",
        "tools": ["launch_application", "list_installed_applications"]
    },
    "file": {
        "description": "Opening existing files by filename or path - PDFs, images, pictures, screenshots, documents, downloads. Searching for files in folders like Pictures, Documents, Downloads. Opening web URLs and websites.",
        "tools": ["open_file", "open_url", "search_files"]
    },
    "window": {
        "description": "Window management - maximize, minimize, close, focus, move, resize, restore windows. List currently open windows.",
        "tools": ["list_open_windows", "focus_window_by_name", "close_window_by_name",
                  "maximize_window_by_name", "minimize_window_by_name", "restore_window_by_name",
                  "screenshot_window_by_name", "screenshot_area", "move_resize_window_by_name"]
    },
    "workspace": {
        "description": "Virtual desktops, workspace switching, multi-desktop management",
        "tools": ["list_workspaces", "activate_workspace"]
    },
    "input": {
        "description": "Keyboard input, typing text, pressing keys, key combinations, shortcuts, mouse clicks, dragging, scrolling",
        "tools": ["type_text_in_window", "press_key_combo", "key_press", "mouse_click",
                  "mouse_double_click", "drag_item", "scroll_page"]
    },
    "volume": {
        "description": "Sound volume control, mute, unmute, audio levels, speaker settings",
        "tools": ["set_volume", "mute_volume", "unmute_volume"]
    },
    "media": {
        "description": "Media playback control - play, pause, stop, next track, previous track, music control, audio player control",
        "tools": ["media_play", "media_pause", "media_play_pause", "media_next", "media_previous", "media_stop"]
    },
    "settings": {
        "description": "System settings - dark mode, light mode, night light, notifications, do not disturb, WiFi, Bluetooth, quick settings toggles",
        "tools": ["toggle_dark_mode", "toggle_night_light", "toggle_do_not_disturb",
                  "toggle_wifi", "toggle_bluetooth"]
    },
    "vision": {
        "description": "Analyzing current screen content, describing what's visible on desktop right now, color picking from display, monitor configuration. Not for opening files.",
        "tools": ["describe_desktop", "pick_color", "get_monitors"]
    },
    "system": {
        "description": "System automation control, notifications, reminders, timers, cleanup, maintenance",
        "tools": ["set_enabled", "send_notification", "cleanup_screenshots"]
    }
}

# Load model
print("Loading embedding model...")
embedding_model = SentenceTransformer('all-MiniLM-L6-v2')

# Pre-compute namespace embeddings
namespace_names = list(namespaces.keys())
namespace_descriptions = [namespaces[ns]["description"] for ns in namespace_names]
namespace_embeddings = embedding_model.encode(namespace_descriptions, convert_to_tensor=True)

def retrieve_relevant_namespaces(user_input: str, top_k: int = 3) -> list:
    """Retrieve most relevant namespaces for a user input"""
    from sentence_transformers.util import cos_sim

    # Encode user input
    query_embedding = embedding_model.encode(user_input, convert_to_tensor=True)

    # Compute cosine similarity
    similarities = cos_sim(query_embedding, namespace_embeddings)[0]

    # Get top-k indices
    top_indices = similarities.argsort(descending=True)[:top_k]

    # Return namespace names
    relevant_namespaces = [namespace_names[i] for i in top_indices]

    return relevant_namespaces, similarities

def test_query(query: str):
    """Test a query and show results"""
    print(f"\n{'='*70}")
    print(f"Query: '{query}'")
    print(f"{'='*70}")

    relevant_ns, similarities = retrieve_relevant_namespaces(query, top_k=3)

    # Show all namespaces ranked
    print("\nAll namespaces (ranked by relevance):")
    ranked_indices = similarities.argsort(descending=True)
    for i, idx in enumerate(ranked_indices):
        ns = namespace_names[idx]
        score = similarities[idx].item()
        tools = namespaces[ns]["tools"]
        marker = "★" if i < 3 else " "
        print(f"  {marker} {i+1}. {ns:12} (score: {score:.3f}) - {len(tools)} tools: {tools}")

    print(f"\n✓ Selected namespaces: {relevant_ns}")

    # Collect tools
    all_tools = []
    for ns in relevant_ns:
        all_tools.extend(namespaces[ns]["tools"])

    print(f"✓ Total tools shown to LLM: {len(all_tools)}")
    print(f"  Tools: {all_tools}")

if __name__ == "__main__":
    # Test queries
    test_queries = [
        "open screenshot.png in pictures folder",
        "maximize firefox",
        "set volume to 50",
        "play next track",
        "turn on dark mode",
        "what's on my desktop",
        "type hello world",
        "find all PDFs",
        "switch to workspace 2",
        "turn on wifi",
    ]

    for query in test_queries:
        test_query(query)

    print(f"\n{'='*70}")
    print("✅ Hybrid retrieval test completed!")
    print(f"{'='*70}")
