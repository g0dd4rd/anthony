import base64
import json
import os

import requests
import webcolors

from commands import step, _mcp_client, _get_friendly_app_name
from utils import log_and_print

LLAMA_VISION_URL = 'http://127.0.0.1:8081/v1/chat/completions'


def _call_vision(system_prompt, user_prompt, img_base64):
    payload = {
        'messages': [
            {'role': 'system', 'content': system_prompt},
            {'role': 'user', 'content': [
                {'type': 'text', 'text': user_prompt},
                {'type': 'image_url', 'image_url': {
                    'url': f'data:image/png;base64,{img_base64}'
                }}
            ]}
        ],
        'temperature': 0.7,
        'max_tokens': 300,
        'chat_template_kwargs': {'enable_thinking': False},
    }
    resp = requests.post(LLAMA_VISION_URL, json=payload, timeout=120)
    resp.raise_for_status()
    return resp.json()['choices'][0]['message']['content']


# --- Screenshot ---

@step('take a screenshot', 'take screenshot', 'capture screen',
      'screenshot', 'screen capture', 'grab the screen', 'capture the screen',
      category='vision', help_text='Take a full screenshot of the screen')
def handle_screenshot(context):
    result = _mcp_client.call_tool("screenshot", {"include_cursor": False, "format": "path"})
    if result.startswith("Error"):
        return result
    return "Screenshot saved to Screenshots."


@step('screenshot area', 'capture area',
      category='vision', help_text='Take a screenshot of a screen area')
def handle_screenshot_area(context):
    return "Area screenshot requires coordinates. Use 'screenshot' for full screen."


# --- Describe screen (uses LLM) ---

@step('describe the screen', "what's on the screen", 'describe screen',
      'what do you see', 'what is on the screen',
      category='vision', uses_llm=True,
      help_text='Describe what is currently visible on screen')
def handle_describe_screen(context):
    result = _mcp_client.call_tool("screenshot", {"include_cursor": False, "format": "path"})
    if result.startswith("Error"):
        return result

    screenshot_path = result.strip()
    with open(screenshot_path, 'rb') as f:
        img_data = base64.b64encode(f.read()).decode('utf-8')

    description = _call_vision(
        'Give a brief 2-3 sentence summary. Read the window title bar to identify the application. Use plain text, no markdown.',
        'What is on this screen?',
        img_data
    )

    try:
        os.remove(screenshot_path)
    except Exception:
        pass
    return description


# --- Describe window (uses LLM) ---

@step('describe the window', 'describe this window', 'describe window',
      "what's in this window",
      'describe this image', 'describe this picture',
      "what's in this picture", "what's this image",
      category='vision', uses_llm=True,
      help_text='Describe the content of the focused window')
def handle_describe_window(context):
    result = _mcp_client.call_tool("list_windows", {})
    if result.startswith("Error"):
        return result
    windows = json.loads(result)
    focused = next((w for w in windows if w.get('focused', False)), None)
    if not focused:
        return "No focused window found."

    window_id = focused['id']
    friendly = _get_friendly_app_name(focused.get('wmClass', ''))

    result = _mcp_client.call_tool("screenshot_window", {
        "window_id": window_id, "include_frame": False,
        "include_cursor": False, "format": "path"
    })
    if result.startswith("Error"):
        return result

    screenshot_path = result.strip()
    with open(screenshot_path, 'rb') as f:
        img_data = base64.b64encode(f.read()).decode('utf-8')

    description = _call_vision(
        'Describe what you see in this application window in plain text without any formatting. Do not use markdown, asterisks, or special characters. Answer directly.',
        f'Describe the content shown in this {friendly} window.',
        img_data
    )

    try:
        os.remove(screenshot_path)
    except Exception:
        pass
    return description


# --- Describe image file (uses LLM) ---

@step('describe {path}', "what's in {path}",
      category='vision', uses_llm=True,
      help_text='Describe an image file')
def handle_describe_file(context, path):
    file_path = os.path.expanduser(path)
    if not os.path.isfile(file_path):
        try:
            search_result = _mcp_client.call_tool("search_files", {
                "query": os.path.basename(path), "file_type": "files", "limit": 5
            })
            results = json.loads(search_result)
            if results.get("count", 0) > 0:
                file_path = results["results"][0]
            else:
                return f"File not found: {path}"
        except Exception:
            return f"File not found: {path}"

    with open(file_path, 'rb') as f:
        img_data = base64.b64encode(f.read()).decode('utf-8')

    return _call_vision(
        'Describe the image in plain text without any formatting. Do not use markdown, asterisks, or special characters. Answer directly without explaining your reasoning process.',
        f'Describe this image: {os.path.basename(file_path)}',
        img_data
    )


# --- Pick color ---

@step('pick color at {x:d} {y:d}', 'what color is at {x:d} {y:d}',
      'get color at {x:d} {y:d}',
      category='vision', help_text='Get the color of a pixel at screen coordinates')
def handle_pick_color(context, x, y):
    result = _mcp_client.call_tool("pick_color", {"x": x, "y": y})
    try:
        rgb_data = json.loads(result)
        r, g, b = int(rgb_data['r']), int(rgb_data['g']), int(rgb_data['b'])
        try:
            color_name = webcolors.rgb_to_name((r, g, b), spec='css3')
        except ValueError:
            min_distance = float('inf')
            closest_name = None
            for name in webcolors.names('css3'):
                named_rgb = webcolors.name_to_rgb(name)
                distance = sum((a - bv) ** 2 for a, bv in zip((r, g, b), named_rgb)) ** 0.5
                if distance < min_distance:
                    min_distance = distance
                    closest_name = name
            color_name = closest_name
        return f"{color_name} (RGB: {r}, {g}, {b})"
    except Exception:
        return result


# --- Monitor info ---

@step('get monitors', 'show monitor info', 'monitor info',
      'how many monitors', 'which monitors',
      category='vision', help_text='Show monitor configuration')
def handle_monitors(context):
    result = _mcp_client.call_tool("get_monitors", {})
    try:
        monitors = json.loads(result)
        if len(monitors) == 0:
            return "No monitors detected"
        elif len(monitors) == 1:
            m = monitors[0]
            primary_tag = " primary" if m.get('primary') else ""
            return f"1{primary_tag} monitor, resolution {m['width']}x{m['height']} at scale {m.get('scale', 1)}"
        else:
            lines = [f"{len(monitors)} monitors connected:"]
            for i, m in enumerate(monitors):
                primary_tag = " (primary)" if m.get('primary') else ""
                lines.append(f"Monitor {i+1}{primary_tag}, resolution {m['width']}x{m['height']}")
            return " ".join(lines)
    except Exception:
        return result
