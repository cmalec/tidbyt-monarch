"""Smoke test: imports, config validation, and the push client against a stub
server that mimics a Tronbyt reply."""
import importlib
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

os.environ.update({
    "MONARCH_EMAIL": "test@example.invalid",
    "MONARCH_PASSWORD": "x",
    "TIDBYT_DEVICE_ID": "pixelnode",
    "TIDBYT_API_KEY": "dev-key",
    "TIDBYT_API_BASE": "http://127.0.0.1:18020/v0",
})

seen = {}


def serve():
    class H(BaseHTTPRequestHandler):
        def do_POST(self):
            n = int(self.headers.get("Content-Length", 0))
            self.rfile.read(n)
            seen["path"] = self.path
            seen["auth"] = self.headers.get("Authorization")
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"WebP received.")

        def log_message(self, format, *args):
            pass

    HTTPServer(("127.0.0.1", 18020), H).serve_forever()


threading.Thread(target=serve, daemon=True).start()

sys.path.insert(0, "/app")
from app import config  # noqa: E402
importlib.reload(config)
from app import push_client  # noqa: E402
importlib.reload(push_client)

import app.main  # noqa: E402,F401  (import check)
from app.monarch_client import MonarchSource  # noqa: E402
from app.renderer import render, render_error  # noqa: E402

result = push_client.push_image(render("networth", {"value": 1234}), "monarch")
print("push result:", result)
print("stub saw:", seen)
assert result == {"status": 200, "body": "WebP received."}, result
assert seen["path"] == "/v0/devices/pixelnode/push", seen
assert seen["auth"] == "Bearer dev-key", seen
assert len(render_error("boom")) > 0
assert MonarchSource is not None
print("smoke ok")
