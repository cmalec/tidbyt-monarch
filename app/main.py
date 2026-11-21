"""Scheduler: pull Monarch data, render, push when the frame changed, repeat."""
import asyncio
import hashlib
import time
import traceback

from app import config, notify
from app.monarch_client import MonarchSource
from app.push_client import push_image
from app.renderer import render, render_error

FETCHERS = {
    "dashboard": "dashboard",
    "networth": "net_worth",
    "budget": "budget",
    "goal": "goal",
    "cashflow": "cashflow",
    "bill": "next_bill",
}


async def _connect() -> MonarchSource:
    source = MonarchSource()
    how = await source.connect()
    print(f"Monarch session: {how}")
    return source


async def _frame(source: MonarchSource, view: str) -> tuple[bytes, dict]:
    data = await getattr(source, FETCHERS[view])()
    return render(view, data), data


def _should_alert(failures: int) -> bool:
    if failures == config.ALERT_AFTER_FAILURES:
        return True
    return bool(config.ALERT_REPEAT_EVERY) and failures % config.ALERT_REPEAT_EVERY == 0


def main() -> None:
    print("=" * 50)
    print("Tidbyt Monarch")
    print("=" * 50)
    print(f"Monarch user: {config.MONARCH_EMAIL}")
    print(f"Device: {config.TIDBYT_DEVICE_ID} via {config.TIDBYT_API_BASE}")
    print(f"Views: {', '.join(config.VIEWS)}")
    print(f"Update interval: {config.UPDATE_INTERVAL}s")
    print(f"Data cache: {config.CACHE_TTL}s")
    print(f"Alerts: {'Gotify' if notify.enabled() else 'disabled'}")
    print("=" * 50)

    source = None
    index = 0
    failures = 0
    last_digest = None

    while True:
        view = config.VIEWS[index % len(config.VIEWS)]
        try:
            if source is None:
                source = asyncio.run(_connect())

            image, data = asyncio.run(_frame(source, view))
            digest = hashlib.sha256(image).hexdigest()
            if digest == last_digest:
                # Same pixels as the last push. Tidbyt and Tronbyt both keep
                # showing what they already have, so repushing buys nothing.
                print(f"[{view}] unchanged, skipping push")
            else:
                result = push_image(image)
                print(f"[{view}] {data} -> {result}")
                last_digest = digest

            if failures:
                print(f"recovered after {failures} failed cycle(s)")
            failures = 0
            index += 1
        except Exception as exc:
            failures += 1
            print(f"Error on view {view} ({failures} in a row): {type(exc).__name__}: {exc}")
            traceback.print_exc()
            # A stale session or a Monarch hiccup should not freeze the panel.
            source = None
            try:
                offline = render_error(type(exc).__name__)
                offline_digest = hashlib.sha256(offline).hexdigest()
                if offline_digest != last_digest:
                    push_image(offline)
                    last_digest = offline_digest
            except Exception as push_exc:
                print(f"Could not push offline frame: {push_exc}")

            if _should_alert(failures):
                notify.send(
                    "Tidbyt Monarch is failing",
                    f"**{failures}** consecutive failed cycles.\n\n"
                    f"View: `{view}`\n\n"
                    f"`{type(exc).__name__}: {str(exc)[:300]}`",
                    priority=7,
                )

        time.sleep(config.UPDATE_INTERVAL)


if __name__ == "__main__":
    main()
