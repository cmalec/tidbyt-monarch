"""Smoke test: imports, then the push client against a stub server that mimics
a Tronbyt reply.

    python -m tools.smoke
"""
import importlib
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

PORT = 18020

os.environ.update({
    "MONARCH_EMAIL": "test@example.invalid",
    "MONARCH_PASSWORD": "x",
    "TIDBYT_DEVICE_ID": "pixelnode",
    "TIDBYT_API_KEY": "dev-key",
    "TIDBYT_API_BASE": f"http://127.0.0.1:{PORT}/v0",
})

seen = {}


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        self.rfile.read(length)
        seen["path"] = self.path
        seen["auth"] = self.headers.get("Authorization")
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(b"WebP received.")

    def log_message(self, *args):
        pass


def main() -> int:
    server = HTTPServer(("127.0.0.1", PORT), Handler)
    # HTTPServer binds in the constructor, so the socket is listening before
    # the thread starts: no race between serve_forever and the first request.
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from app import config  # noqa: E402

    importlib.reload(config)
    from app import push_client  # noqa: E402

    importlib.reload(push_client)
    import app.main  # noqa: E402,F401  (import check)
    from app.monarch_client import MonarchSource  # noqa: E402
    from app.renderer import render, render_error  # noqa: E402

    try:
        result = push_client.push_image(render("networth", {"value": 1234}), "monarch")
    finally:
        server.shutdown()
        server.server_close()

    print("push result:", result)
    print("stub saw:", seen)
    assert result == {"status": 200, "body": "WebP received."}, result
    assert seen["path"] == "/v0/devices/pixelnode/push", seen
    assert seen["auth"] == "Bearer dev-key", seen
    assert len(render_error("boom")) > 0
    assert MonarchSource is not None
    print("smoke ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
