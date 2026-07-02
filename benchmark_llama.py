#!/usr/bin/env python3
"""Extensive benchmark of Gemma 4 E4B on llama.cpp: Vulkan vs SYCL, CPU vs GPU.
Tests text generation, tool calling, and vision. Unloads model between runs."""

import argparse
import base64
import os
import signal
import subprocess
import sys
import time

import requests

HOME = os.path.expanduser("~")
DEFAULT_MODEL = f"{HOME}/models/gemma4-e4b-q4km.gguf"
DEFAULT_MMPROJ = f"{HOME}/models/mmproj-gemma4-e4b-q8.gguf"
TEST_IMAGE = f"{HOME}/Pictures/Camera/room.jpeg"
PORT = 8099
API_URL = f"http://127.0.0.1:{PORT}/v1/chat/completions"
HEALTH_URL = f"http://127.0.0.1:{PORT}/health"
VERBOSE = False
MODEL = DEFAULT_MODEL
MMPROJ = DEFAULT_MMPROJ

CONFIGS = [
    {
        "name": "Vulkan GPU",
        "binary": f"{HOME}/llama.cpp/build/bin/llama-server",
        "env_setup": None,
        "device": "Vulkan0",
        "gpu_layers": 99,
    },
    {
        "name": "Vulkan CPU",
        "binary": f"{HOME}/llama.cpp/build/bin/llama-server",
        "env_setup": None,
        "device": None,
        "gpu_layers": 0,
    },
    {
        "name": "SYCL GPU",
        "binary": f"{HOME}/llama.cpp/build-sycl/bin/llama-server",
        "env_setup": "source /opt/intel/oneapi/setvars.sh 2>/dev/null",
        "device": "SYCL0",
        "gpu_layers": 99,
    },
    {
        "name": "SYCL CPU",
        "binary": f"{HOME}/llama.cpp/build-sycl/bin/llama-server",
        "env_setup": "source /opt/intel/oneapi/setvars.sh 2>/dev/null",
        "device": None,
        "gpu_layers": 0,
    },
]

SYSTEM_TEXT = "Respond directly and concisely. Do not think or reason step by step."
SYSTEM_TOOLS = "You are a silent tool-calling orchestrator. Respond ONLY with tool calls. Never explain, reason, or add commentary."
SYSTEM_VISION = "Describe directly what you see. Do not think or reason step by step."

TEXT_PROMPTS = [
    {"label": "short_answer", "prompt": "What is the capital of France? Answer in one sentence."},
    {"label": "explanation", "prompt": "Explain how a CPU cache works in 3-4 sentences."},
    {"label": "creative", "prompt": "Write a 4-line poem about a robot learning to paint."},
]

TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "window_control",
            "description": "Window management: list, focus, close, minimize, maximize, restore, screenshot windows.",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "description": "Action: list | focus | close | minimize | maximize | restore | screenshot",
                    },
                    "window_name": {
                        "type": "string",
                        "description": "Application name",
                        "default": "",
                    },
                },
                "required": ["action"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "audio_control",
            "description": "Audio control: volume set/increase/decrease, mute, unmute, media playback.",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "description": "Action: volume | mute | unmute | play | pause | next | previous",
                    },
                    "level": {"type": "integer", "description": "Volume level 0-100", "default": 0},
                },
                "required": ["action"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_datetime",
            "description": "Get the current date, time, and day of week.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
]

TOOL_PROMPTS = [
    {
        "label": "tool_maximize",
        "prompt": "Maximize the firefox window",
        "expect_tool": "window_control",
    },
    {"label": "tool_volume", "prompt": "Set volume to 50 percent", "expect_tool": "audio_control"},
    {
        "label": "tool_datetime",
        "prompt": "What time is it right now?",
        "expect_tool": "get_datetime",
    },
]

VISION_PROMPTS = [
    {"label": "vision_describe", "prompt": "Describe what you see in this image in 2-3 sentences."},
    {"label": "vision_objects", "prompt": "List the main objects visible in this image."},
]


def encode_image(path):
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def kill_server():
    try:
        result = subprocess.run(["fuser", f"{PORT}/tcp"], capture_output=True, text=True)
        pids = result.stdout.strip().split()
        for pid in pids:
            pid = pid.strip()
            if pid:
                os.kill(int(pid), signal.SIGKILL)
        if pids:
            time.sleep(2)
    except Exception:
        pass
    subprocess.run(["fuser", "-k", f"{PORT}/tcp"], capture_output=True)
    time.sleep(1)


def start_server(config, use_mmproj=False):
    kill_server()

    cmd_parts = []
    if config["env_setup"]:
        cmd_parts.append(config["env_setup"])
        cmd_parts.append("&&")

    cmd_parts.append(config["binary"])
    cmd_parts.extend(["--model", MODEL])
    cmd_parts.extend(["--ctx-size", "4096"])
    cmd_parts.extend(["--n-gpu-layers", str(config["gpu_layers"])])
    cmd_parts.extend(["--port", str(PORT)])
    cmd_parts.extend(["--host", "127.0.0.1"])
    cmd_parts.extend(["--threads", "6"])
    cmd_parts.extend(["--parallel", "1"])
    cmd_parts.append("--cont-batching")
    cmd_parts.extend(["--flash-attn", "auto"])
    cmd_parts.append("--jinja")

    if config["device"]:
        cmd_parts.extend(["--device", config["device"]])

    if use_mmproj and MMPROJ:
        cmd_parts.extend(["--mmproj", MMPROJ])

    shell_cmd = " ".join(cmd_parts)
    print(f"  CMD: {shell_cmd}")

    proc = subprocess.Popen(
        shell_cmd,
        shell=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )

    print("  Waiting for server", end="", flush=True)
    for _i in range(180):
        time.sleep(1)
        print(".", end="", flush=True)
        try:
            r = requests.get(HEALTH_URL, timeout=2)
            if r.status_code == 200:
                data = r.json()
                if data.get("status") == "ok":
                    print(" ready! Warming up...", end="", flush=True)
                    try:
                        call_api([{"role": "user", "content": "Hi"}], max_tokens=1)
                        print(" done!")
                    except Exception:
                        print(" (warmup failed, continuing)")
                    return proc
        except requests.exceptions.ConnectionError:
            pass
        except Exception:
            pass

    print(" TIMEOUT - server did not start")
    kill_server()
    return None


def call_api(messages, tools=None, max_tokens=200):
    payload = {
        "messages": messages,
        "temperature": 0.0,
        "max_tokens": max_tokens,
        "model": "gemma",
        "chat_template_kwargs": {"enable_thinking": False},
    }
    if tools:
        payload["tools"] = tools

    t0 = time.perf_counter()
    resp = requests.post(API_URL, json=payload, timeout=120)
    elapsed = time.perf_counter() - t0

    resp.raise_for_status()
    data = resp.json()

    usage = data.get("usage", {})
    choice = data["choices"][0]
    message = choice["message"]

    content = message.get("content", "") or ""
    reasoning = message.get("reasoning_content", "") or ""

    return {
        "content": content,
        "reasoning_content": reasoning,
        "response_text": content if content.strip() else reasoning,
        "tool_calls": message.get("tool_calls", []),
        "prompt_tokens": usage.get("prompt_tokens", 0),
        "completion_tokens": usage.get("completion_tokens", 0),
        "elapsed": elapsed,
    }


def run_text_tests():
    results = []
    for t in TEXT_PROMPTS:
        messages = [
            {"role": "system", "content": SYSTEM_TEXT},
            {"role": "user", "content": t["prompt"]},
        ]
        r = call_api(messages, max_tokens=300)
        tps = r["completion_tokens"] / r["elapsed"] if r["elapsed"] > 0 else 0
        result = {
            "label": t["label"],
            "prompt_tokens": r["prompt_tokens"],
            "completion_tokens": r["completion_tokens"],
            "elapsed": r["elapsed"],
            "tokens_per_sec": tps,
            "response": r["response_text"][:150],
        }
        results.append(result)
        print(
            f"    {t['label']}: {r['completion_tokens']} tok / {r['elapsed']:.2f}s = {tps:.1f} tok/s"
        )
        if VERBOSE:
            if r["reasoning_content"]:
                print(f"      [thinking] {r['reasoning_content']}")
            print(f"      [content]  {r['content']}")
    return results


def run_tool_tests():
    results = []
    for t in TOOL_PROMPTS:
        messages = [
            {"role": "system", "content": SYSTEM_TOOLS},
            {"role": "user", "content": t["prompt"]},
        ]
        r = call_api(messages, tools=TOOL_SCHEMAS, max_tokens=300)
        tps = r["completion_tokens"] / r["elapsed"] if r["elapsed"] > 0 else 0

        tool_name = None
        if r["tool_calls"]:
            tool_name = r["tool_calls"][0].get("function", {}).get("name")
        correct = tool_name == t["expect_tool"]

        result = {
            "label": t["label"],
            "prompt_tokens": r["prompt_tokens"],
            "completion_tokens": r["completion_tokens"],
            "elapsed": r["elapsed"],
            "tokens_per_sec": tps,
            "tool_called": tool_name,
            "expected": t["expect_tool"],
            "correct": correct,
        }
        results.append(result)
        mark = "OK" if correct else "WRONG"
        print(f"    {t['label']}: {tool_name} [{mark}] / {r['elapsed']:.2f}s = {tps:.1f} tok/s")
        if VERBOSE:
            if r["reasoning_content"]:
                print(f"      [thinking] {r['reasoning_content']}")
            print(f"      [content]  {r['content']}")
            if r["tool_calls"]:
                for tc in r["tool_calls"]:
                    print(
                        f"      [tool]     {tc['function']['name']}({tc['function']['arguments']})"
                    )
    return results


def run_vision_tests(image_b64):
    results = []
    for t in VISION_PROMPTS:
        messages = [
            {"role": "system", "content": SYSTEM_VISION},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": t["prompt"]},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"},
                    },
                ],
            },
        ]
        r = call_api(messages, max_tokens=300)
        tps = r["completion_tokens"] / r["elapsed"] if r["elapsed"] > 0 else 0
        has_response = len(r["response_text"].strip()) > 10

        result = {
            "label": t["label"],
            "prompt_tokens": r["prompt_tokens"],
            "completion_tokens": r["completion_tokens"],
            "elapsed": r["elapsed"],
            "tokens_per_sec": tps,
            "has_response": has_response,
            "response": r["response_text"][:150],
        }
        results.append(result)
        mark = "OK" if has_response else "EMPTY"
        print(
            f"    {t['label']}: {r['completion_tokens']} tok / {r['elapsed']:.2f}s = {tps:.1f} tok/s [{mark}]"
        )
        if VERBOSE:
            if r["reasoning_content"]:
                print(f"      [thinking] {r['reasoning_content']}")
            print(f"      [content]  {r['content']}")
    return results


def print_summary(all_results):
    # Collect all rows with config name attached
    rows = []
    for config_name, categories in all_results.items():
        for category, tests in categories.items():
            for t in tests:
                if "correct" in t:
                    status = "OK" if t["correct"] else "WRONG"
                elif "has_response" in t:
                    status = "OK" if t["has_response"] else "EMPTY"
                else:
                    status = ""
                rows.append({**t, "config": config_name, "category": category, "status": status})

    # Group by test label, sort each group by time
    test_order = (
        [t["label"] for t in TEXT_PROMPTS]
        + [t["label"] for t in TOOL_PROMPTS]
        + [t["label"] for t in VISION_PROMPTS]
    )

    print()
    print("=" * 90)
    print("BENCHMARK RESULTS (ordered by response time)")
    print("=" * 90)

    for test_label in test_order:
        test_rows = sorted(
            [r for r in rows if r["label"] == test_label], key=lambda r: r["elapsed"]
        )
        if not test_rows:
            continue
        cat = test_rows[0]["category"]
        print(f"\n  {cat}: {test_label}")
        for i, r in enumerate(test_rows):
            rank = i + 1
            status = f"  [{r['status']}]" if r["status"] else ""
            print(
                f"    {rank}. {r['config']:<16} {r['elapsed']:>6.2f}s  {r['tokens_per_sec']:>5.1f} tok/s  "
                f"({r['completion_tokens']} tok){status}"
            )

    # Averages table sorted by total time
    print()
    print("=" * 90)
    print("AVERAGES (sorted by total response time)")
    print("=" * 90)
    print(
        f"  {'Config':<16} {'Avg Time':>10} {'Avg Tok/s':>10} {'Text':>10} {'Tools':>10} {'Vision':>10}"
    )
    print(f"  {'-' * 70}")

    config_stats = []
    for config_name, categories in all_results.items():
        all_times = []
        all_tps = []
        cat_tps = {}
        for cat, tests in categories.items():
            times = [t["elapsed"] for t in tests]
            tps = [t["tokens_per_sec"] for t in tests]
            cat_tps[cat] = sum(tps) / len(tps) if tps else 0
            all_times.extend(times)
            all_tps.extend(tps)
        avg_time = sum(all_times) / len(all_times) if all_times else 0
        avg_tps = sum(all_tps) / len(all_tps) if all_tps else 0
        config_stats.append((config_name, avg_time, avg_tps, cat_tps))

    for config_name, avg_time, avg_tps, cat_tps in sorted(config_stats, key=lambda x: x[1]):
        print(
            f"  {config_name:<16} {avg_time:>9.2f}s {avg_tps:>9.1f} "
            f"{cat_tps.get('text', 0):>9.1f} {cat_tps.get('tools', 0):>9.1f} "
            f"{cat_tps.get('vision', 0):>9.1f}"
        )


def main():
    parser = argparse.ArgumentParser(
        description="Benchmark Gemma on llama.cpp (Vulkan/SYCL, CPU/GPU)"
    )
    parser.add_argument(
        "--configs",
        nargs="+",
        choices=["vulkan-gpu", "vulkan-cpu", "sycl-gpu", "sycl-cpu"],
        help="Run only specific configs (default: all)",
    )
    parser.add_argument("--model", default=DEFAULT_MODEL, help="Path to GGUF model")
    parser.add_argument("--mmproj", default=DEFAULT_MMPROJ, help="Path to mmproj GGUF")
    parser.add_argument(
        "--no-mmproj",
        action="store_true",
        help="Don't use mmproj (for models with built-in vision like Qwen VL)",
    )
    parser.add_argument("--skip-tools", action="store_true", help="Skip tool calling tests")
    parser.add_argument("--skip-vision", action="store_true", help="Skip vision tests")
    parser.add_argument("--image", default=TEST_IMAGE, help="Image path for vision tests")
    parser.add_argument(
        "--verbose", "-v", action="store_true", help="Show full LLM output (thinking + content)"
    )
    args = parser.parse_args()

    global VERBOSE, MODEL, MMPROJ
    VERBOSE = args.verbose
    MODEL = args.model
    MMPROJ = None if args.no_mmproj else args.mmproj

    config_map = {
        "vulkan-gpu": 0,
        "vulkan-cpu": 1,
        "sycl-gpu": 2,
        "sycl-cpu": 3,
    }
    if args.configs:
        configs = [CONFIGS[config_map[c]] for c in args.configs]
    else:
        configs = CONFIGS

    image_b64 = None
    if not args.skip_vision:
        if not os.path.exists(args.image):
            print(f"ERROR: Vision test image not found: {args.image}")
            sys.exit(1)
        image_b64 = encode_image(args.image)

    print(f"Model: {MODEL}")
    print(f"Vision projector: {MMPROJ or 'built-in'}")
    print(f"Test image: {args.image}")
    print(f"Configs to test: {', '.join(c['name'] for c in configs)}")
    print(f"Port: {PORT}")
    print()

    all_results = {}

    for config in configs:
        print("=" * 60)
        print(f"CONFIG: {config['name']}")
        print("=" * 60)

        print("\n  Starting server...")
        proc = start_server(config, use_mmproj=True)
        if not proc:
            print(f"  SKIPPING {config['name']} — server failed to start")
            all_results[config["name"]] = {"text": [], "tools": [], "vision": []}
            continue

        config_results = {}

        print("\n  [TEXT GENERATION]")
        try:
            config_results["text"] = run_text_tests()
        except Exception as e:
            print(f"    ERROR: {e}")
            config_results["text"] = []

        if not args.skip_tools:
            print("\n  [TOOL CALLING]")
            try:
                config_results["tools"] = run_tool_tests()
            except Exception as e:
                print(f"    ERROR: {e}")
                config_results["tools"] = []
        else:
            config_results["tools"] = []

        if image_b64 and not args.skip_vision:
            print("\n  [VISION]")
            try:
                config_results["vision"] = run_vision_tests(image_b64)
            except Exception as e:
                print(f"    ERROR: {e}")
                config_results["vision"] = []
        else:
            config_results["vision"] = []

        print("\n  Stopping server...")
        kill_server()
        print("  Server stopped.")

        all_results[config["name"]] = config_results
        print()

    print_summary(all_results)


if __name__ == "__main__":
    main()
