import json
import os
import time

from uds_http import LLAMA_SOCKET_PATH, post_unix
from utils import log_and_print

CACHE_DIR = os.path.expanduser("~/.config/anthony")
CACHE_FILE = os.path.join(CACHE_DIR, "hw_profile.json")

# 1x1 white PNG for vision warmup
_WHITE_1X1_PNG = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4"
    "nGP4z8BQDwAEgAF/pooBPQAAAABJRU5ErkJggg=="
)


def _read_cache():
    try:
        with open(CACHE_FILE) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def _write_cache(tok_per_sec):
    os.makedirs(CACHE_DIR, exist_ok=True)
    with open(CACHE_FILE, "w") as f:
        json.dump({"tok_per_sec": round(tok_per_sec, 2)}, f)


def _text_benchmark(socket_path):
    try:
        post_unix(
            socket_path,
            "/v1/chat/completions",
            {
                "messages": [{"role": "user", "content": "Hi"}],
                "max_tokens": 5,
                "temperature": 0.0,
            },
            timeout=30,
        )
    except Exception:
        pass

    start = time.time()
    result = post_unix(
        socket_path,
        "/v1/chat/completions",
        {
            "messages": [{"role": "user", "content": "Count from 1 to 20."}],
            "max_tokens": 60,
            "temperature": 0.0,
        },
        timeout=60,
    )
    elapsed = time.time() - start

    tokens = result.get("usage", {}).get("completion_tokens", 0)
    if tokens == 0 or elapsed == 0:
        return 0.0
    return tokens / elapsed


def _vision_warmup(socket_path):
    post_unix(
        socket_path,
        "/v1/chat/completions",
        {
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/png;base64,{_WHITE_1X1_PNG}"},
                        },
                        {"type": "text", "text": "What color?"},
                    ],
                }
            ],
            "max_tokens": 5,
            "temperature": 0.0,
        },
        timeout=30,
    )


def warmup(socket_path=None, has_vision=False):
    if socket_path is None:
        socket_path = LLAMA_SOCKET_PATH

    cached = _read_cache()
    if cached:
        log_and_print(f"[WARMUP] Cached: {cached['tok_per_sec']} tok/s")
    else:
        log_and_print("[WARMUP] Running text benchmark...")
        try:
            tok_per_sec = _text_benchmark(socket_path)
            if tok_per_sec > 0:
                log_and_print(f"[WARMUP] Text: {tok_per_sec:.1f} tok/s")
                _write_cache(tok_per_sec)
            else:
                log_and_print("[WARMUP] Text benchmark returned 0 tokens")
        except Exception as e:
            log_and_print(f"[WARMUP] Text benchmark failed: {e}")

    if has_vision:
        log_and_print("[WARMUP] Loading vision weights...")
        try:
            start = time.time()
            _vision_warmup(socket_path)
            elapsed = time.time() - start
            log_and_print(f"[WARMUP] Vision ready ({elapsed:.1f}s)")
        except Exception as e:
            log_and_print(f"[WARMUP] Vision warmup failed: {e}")
