"""Optional Gotify alerting, so a dead Monarch session is not silent.

Configured entirely by env; if GOTIFY_URL or GOTIFY_TOKEN is unset, alerts are
skipped and the app behaves as before.
"""
import json
import urllib.error
import urllib.request

from app import config

MARKDOWN_EXTRA = {"client::display": {"contentType": "text/markdown"}}


def enabled() -> bool:
    return bool(config.GOTIFY_URL and config.GOTIFY_TOKEN)


def send(title: str, message: str, priority: int = 5) -> bool:
    """POST a message to Gotify. Returns True when accepted."""
    if not enabled():
        return False
    payload = {
        "title": title,
        "message": message,
        "priority": priority,
        "extras": MARKDOWN_EXTRA,
    }
    req = urllib.request.Request(
        f"{config.GOTIFY_URL.rstrip('/')}/message",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", "X-Gotify-Key": config.GOTIFY_TOKEN},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return 200 <= r.status < 300
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as exc:
        print(f"Gotify alert failed: {type(exc).__name__}: {exc}")
        return False
