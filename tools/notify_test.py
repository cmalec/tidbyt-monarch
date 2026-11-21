"""Send one real Gotify alert through the app's notify module."""
from app import config, notify

print("gotify url set:", bool(config.GOTIFY_URL))
print("gotify token set:", bool(config.GOTIFY_TOKEN))
print("enabled:", notify.enabled())
ok = notify.send(
    "Tidbyt Monarch test alert",
    "If you can read this, failure alerts from the Monarch app will reach you.\n\n"
    "No action needed.",
    priority=3,
)
print("delivered:", ok)
raise SystemExit(0 if ok else 1)
