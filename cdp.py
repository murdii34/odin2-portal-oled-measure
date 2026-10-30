"""Minimal Chrome DevTools client for Steam's UI (debug port 8080)."""
import json
import urllib.request

import websocket

URL = "http://localhost:8080/json"


class Target:
    def __init__(self, title):
        targets = json.load(urllib.request.urlopen(URL, timeout=5))
        url = next(t["webSocketDebuggerUrl"] for t in targets if t["title"] == title)
        self.ws = websocket.create_connection(url, timeout=30, suppress_origin=True)
        self.n = 0

    def eval(self, expr):
        """Evaluate JS (awaiting promises) and return its JSON value."""
        self.n += 1
        self.ws.send(json.dumps({"id": self.n, "method": "Runtime.evaluate", "params": {
            "expression": expr, "awaitPromise": True, "returnByValue": True}}))
        while True:
            msg = json.loads(self.ws.recv())
            if msg.get("id") == self.n:
                res = msg.get("result", {})
                if "exceptionDetails" in res:
                    raise RuntimeError(res["exceptionDetails"].get("text", "JS error"))
                return res.get("result", {}).get("value")

    def close(self):
        self.ws.close()


def shared():
    return Target("SharedJSContext")


def ui():
    return Target("Steam Big Picture Mode")
