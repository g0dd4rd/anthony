import json
import re
import subprocess

from commands import _get_friendly_app_name, _mcp_client, _smart_match_window, step
from utils import log_and_print


def _normalize_spoken_path(query):
    normalized = re.sub(r"\s+slash\s+", "/", query, flags=re.IGNORECASE)
    normalized = re.sub(r"\btilde(?:au)?\s*slash\s*", "~/", normalized, flags=re.IGNORECASE)
    normalized = re.sub(r"\btilde(?:au)?\b", "~", normalized, flags=re.IGNORECASE)
    normalized = re.sub(
        r"\s+dot\s+(" + "|".join(sorted(_FILE_EXTENSIONS, key=len, reverse=True)) + r")\b",
        r".\1",
        normalized,
        flags=re.IGNORECASE,
    )
    return normalized


@step(
    "open {query}",
    "launch {query}",
    "start {query}",
    category="search",
    help_text="Open an application, file, or URL",
)
def handle_open(context, query):
    query = query.strip()
    normalized = _normalize_spoken_path(query)
    if normalized != query:
        log_and_print(f"[SEARCH] Path normalization: '{query}' → '{normalized}'")
        query = normalized

    if _is_file_path(query):
        return _open_file(query)

    if _is_url(query):
        return _open_url(query)

    return _open_app(query)


@step("go to {url}", category="search", help_text="Open a website in the browser")
def handle_go_to(context, url):
    return _open_url(url)


@step("find {query}", "search for {query}", category="search", help_text="Search for files")
def handle_search_files(context, query):
    result = _mcp_client.call_tool(
        "search_files", {"query": query, "file_type": "files", "limit": 5}
    )
    try:
        data = json.loads(result)
        count = data.get("count", 0)
        if count == 0:
            return f"No files found matching '{query}'"
        files = data.get("results", [])[:5]
        names = [f.split("/")[-1] for f in files]
        return f"Found {count} files: {', '.join(names)}"
    except Exception:
        return result


_FILE_EXTENSIONS = {
    "txt",
    "pdf",
    "doc",
    "docx",
    "odt",
    "csv",
    "py",
    "js",
    "ts",
    "jsx",
    "png",
    "jpg",
    "jpeg",
    "gif",
    "svg",
    "bmp",
    "webp",
    "mp3",
    "mp4",
    "mkv",
    "avi",
    "wav",
    "flac",
    "ogg",
    "html",
    "json",
    "xml",
    "md",
    "sh",
    "conf",
    "log",
    "yaml",
    "yml",
    "zip",
    "tar",
    "gz",
    "rpm",
    "deb",
}


def _is_file_path(query):
    if "/" in query or query.startswith("~"):
        return True
    if "." in query and " " not in query:
        ext = query.rsplit(".", 1)[-1].lower()
        if ext in _FILE_EXTENSIONS:
            return True
    return False


def _is_url(query):
    if query.startswith(("http://", "https://", "www.")):
        return True
    if "." in query and " " not in query:
        ext = query.rsplit(".", 1)[-1].lower()
        if ext in _FILE_EXTENSIONS:
            return False
        parts = query.split(".")
        if len(parts) >= 2 and len(parts[-1]) >= 2:
            return True
    return False


def _open_url(url):
    import time

    url = url.replace(" ", "")
    if not url.startswith(("http://", "https://")):
        if not url.startswith("www."):
            url = f"https://www.{url}"
        else:
            url = f"https://{url}"
    subprocess.run(
        ["xdg-open", url], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )
    time.sleep(0.5)
    try:
        win_list = json.loads(_mcp_client.call_tool("list_windows", {}))
        browser = (
            _smart_match_window("firefox", win_list)
            or _smart_match_window("chromium", win_list)
            or _smart_match_window("chrome", win_list)
        )
        if browser:
            _mcp_client.call_tool("focus_window", {"window_id": browser["id"]})
    except Exception:
        pass
    return f"Opening {url} in browser"


def _open_file(path):
    import os

    expanded = os.path.expanduser(path)
    if not os.path.isabs(expanded):
        home_path = os.path.join(os.path.expanduser("~"), expanded)
        if os.path.isfile(home_path):
            expanded = home_path
    if os.path.isfile(expanded):
        result = _mcp_client.call_tool("open_file", {"path": expanded})
        return result

    try:
        search_result = _mcp_client.call_tool(
            "search_files", {"query": os.path.basename(path), "file_type": "files", "limit": 1}
        )
        data = json.loads(search_result)
        if data.get("count", 0) > 0:
            found_path = data["results"][0]
            result = _mcp_client.call_tool("open_file", {"path": found_path})
            return result
    except Exception:
        pass

    return f"File not found: {path}"


def _open_app(query):
    try:
        win_list = json.loads(_mcp_client.call_tool("list_windows", {}))
        match = _smart_match_window(query, win_list)
        if match:
            _mcp_client.call_tool("focus_window", {"window_id": match["id"]})
            friendly = _get_friendly_app_name(match.get("wmClass", query))
            return f"{friendly} is already running. Switched to it."
    except Exception:
        pass

    result = _mcp_client.call_tool("gnome_search", {"query": query})
    return result
