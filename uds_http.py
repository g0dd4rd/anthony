import http.client
import json
import os
import socket as socket_mod

_SOCKET_DIR = os.path.join(os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}"), "anthony")
LLAMA_SOCKET_PATH = os.path.join(_SOCKET_DIR, "llama.sock")


class _UnixHTTPConnection(http.client.HTTPConnection):
    def __init__(self, socket_path, timeout=120):
        super().__init__("localhost", timeout=timeout)
        self._socket_path = socket_path

    def connect(self):
        self.sock = socket_mod.socket(socket_mod.AF_UNIX, socket_mod.SOCK_STREAM)
        self.sock.settimeout(self.timeout)
        self.sock.connect(self._socket_path)


def post_unix(socket_path, path, payload, timeout=120):
    conn = _UnixHTTPConnection(socket_path, timeout=timeout)
    body = json.dumps(payload).encode()
    conn.request("POST", path, body=body, headers={"Content-Type": "application/json"})
    resp = conn.getresponse()
    data = resp.read().decode()
    conn.close()
    if resp.status >= 400:
        raise ConnectionError(f"HTTP {resp.status}: {data}")
    return json.loads(data)


def get_unix(socket_path, path, timeout=2):
    conn = _UnixHTTPConnection(socket_path, timeout=timeout)
    conn.request("GET", path)
    resp = conn.getresponse()
    data = resp.read().decode()
    conn.close()
    return resp.status, json.loads(data)
