"""Tiny Chrome DevTools Protocol client for checking the plugin UI on a Steam Deck.

Steam's UI is a CEF app with remote debugging on 127.0.0.1:8080 (Decky enables it).
Run this on the Deck as the deck user, stdlib only:

    python3 cdp.py targets
    python3 cdp.py eval SharedJSContext 'document.title'
    python3 cdp.py shot QuickAccess /tmp/qam.png
"""
import base64
import json
import os
import socket
import struct
import sys
import urllib.request

DEBUG_HOST = "127.0.0.1"
DEBUG_PORT = 8080


def targets() -> list[dict]:
    with urllib.request.urlopen(f"http://{DEBUG_HOST}:{DEBUG_PORT}/json", timeout=5) as r:
        return json.load(r)


def find_target(title_part: str) -> dict:
    for t in targets():
        if title_part in t.get("title", ""):
            return t
    raise SystemExit(f"no target whose title contains {title_part!r}")


class WebSocket:
    def __init__(self, url: str):
        path = url.split(f":{DEBUG_PORT}", 1)[1]
        self.sock = socket.create_connection((DEBUG_HOST, DEBUG_PORT), timeout=20)
        key = base64.b64encode(os.urandom(16)).decode()
        self.sock.sendall(
            f"GET {path} HTTP/1.1\r\nHost: {DEBUG_HOST}:{DEBUG_PORT}\r\nUpgrade: websocket\r\n"
            f"Connection: Upgrade\r\nSec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n".encode()
        )
        head = b""
        while b"\r\n\r\n" not in head:
            head += self.sock.recv(4096)
        self.buf = head.split(b"\r\n\r\n", 1)[1]
        self.next_id = 0

    def _read(self, n: int) -> bytes:
        while len(self.buf) < n:
            chunk = self.sock.recv(65536)
            if not chunk:
                raise ConnectionError("websocket closed")
            self.buf += chunk
        data, self.buf = self.buf[:n], self.buf[n:]
        return data

    def send(self, payload: dict):
        data = json.dumps(payload).encode()
        header = bytearray([0x81])
        n = len(data)
        if n < 126:
            header.append(0x80 | n)
        elif n < 65536:
            header += bytes([0x80 | 126]) + struct.pack(">H", n)
        else:
            header += bytes([0x80 | 127]) + struct.pack(">Q", n)
        mask = os.urandom(4)
        self.sock.sendall(bytes(header) + mask + bytes(b ^ mask[i % 4] for i, b in enumerate(data)))

    def recv(self) -> dict:
        message = b""
        while True:
            b0, b1 = self._read(2)
            n = b1 & 0x7F
            if n == 126:
                n = struct.unpack(">H", self._read(2))[0]
            elif n == 127:
                n = struct.unpack(">Q", self._read(8))[0]
            message += self._read(n)
            if b0 & 0x80:  # FIN
                return json.loads(message)

    def call(self, method: str, params: dict | None = None) -> dict:
        self.next_id += 1
        self.send({"id": self.next_id, "method": method, "params": params or {}})
        while True:
            msg = self.recv()
            if msg.get("id") == self.next_id:
                if "error" in msg:
                    raise SystemExit(f"{method}: {msg['error']}")
                return msg["result"]


def evaluate(title_part: str, expression: str):
    ws = WebSocket(find_target(title_part)["webSocketDebuggerUrl"])
    result = ws.call("Runtime.evaluate", {
        "expression": expression,
        "awaitPromise": True,
        "returnByValue": True,
    })
    if "exceptionDetails" in result:
        raise SystemExit(f"exception: {result['exceptionDetails'].get('exception', {}).get('description')}")
    return result["result"].get("value")


def screenshot(title_part: str, path: str):
    ws = WebSocket(find_target(title_part)["webSocketDebuggerUrl"])
    data = ws.call("Page.captureScreenshot", {"format": "png"})["data"]
    with open(path, "wb") as f:
        f.write(base64.b64decode(data))
    print(path)


def main(argv: list[str]):
    if argv[:1] == ["targets"]:
        for t in targets():
            print(t.get("title"))
    elif argv[:1] == ["eval"] and len(argv) == 3:
        print(json.dumps(evaluate(argv[1], argv[2]), ensure_ascii=False, indent=2))
    elif argv[:1] == ["shot"] and len(argv) == 3:
        screenshot(argv[1], argv[2])
    else:
        raise SystemExit(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])
