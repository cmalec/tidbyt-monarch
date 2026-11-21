"""Scheduler: pull Monarch data, render, push when the frame changed, repeat.

One event loop for the life of the process. Fetch failures drop the session so
the next cycle re-authenticates; push failures never do, because a Tronbyt blip
should not cost a password login or the data cache.
"""
import asyncio
import hashlib
import re
import signal

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

_SECRETISH = re.compile(r"[A-Za-z0-9_\-]{24,}")


def _safe_detail(exc: Exception) -> str:
    """Exception text safe for a log line or a push notification."""
    text = _SECRETISH.sub("<redacted>", str(exc))[:200]
    return f"{type(exc).__name__}: {text}"


def _should_alert(failures: int) -> bool:
    """True at the threshold, then every ALERT_REPEAT_EVERY failures after it."""
    if failures < config.ALERT_AFTER_FAILURES:
        return False
    if failures == config.ALERT_AFTER_FAILURES:
        return True
    if config.ALERT_REPEAT_EVERY <= 0:
        return False
    return (failures - config.ALERT_AFTER_FAILURES) % config.ALERT_REPEAT_EVERY == 0


async def _connect() -> MonarchSource:
    source = MonarchSource()
    how = await source.connect()
    print(f"Monarch session: {how}")
    return source


async def _render(source: MonarchSource, view: str) -> tuple[bytes, dict]:
    data = await getattr(source, FETCHERS[view])()
    return render(view, data), data


async def _push(image: bytes, installation_id: str = "monarch") -> dict:
    return await asyncio.to_thread(push_image, image, installation_id)


def _banner() -> None:
    print("=" * 50)
    print("Tidbyt Monarch")
    print("=" * 50)
    print(f"Monarch user: {config.MONARCH_EMAIL}")
    print(f"Device: {config.TIDBYT_DEVICE_ID} via {config.TIDBYT_API_BASE}")
    print(f"Views: {', '.join(config.VIEWS)}")
    print(f"Update interval: {config.UPDATE_INTERVAL}s")
    print(f"Data cache: {config.CACHE_TTL}s")
    print(f"Values in logs: {'yes' if config.DEBUG_VALUES else 'no'}")
    print(f"Alerts: {'Gotify' if notify.enabled() else 'disabled'}")
    print("=" * 50)


async def _run() -> None:
    _banner()
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, stop.set)
        except (NotImplementedError, RuntimeError):
            pass

    source: MonarchSource | None = None
    index = 0
    failures = 0
    last_digest = None

    while not stop.is_set():
        view = config.VIEWS[index % len(config.VIEWS)]

        # --- fetch and render -------------------------------------------
        try:
            if source is None:
                source = await _connect()
            image, data = await _render(source, view)
        except Exception as exc:
            failures += 1
            print(f"Fetch failed on {view} ({failures} in a row): {_safe_detail(exc)}")
            if source is not None:
                await source.close()
                source = None
            try:
                offline = render_error(type(exc).__name__)
                digest = hashlib.sha256(offline).hexdigest()
                if digest != last_digest:
                    await _push(offline)
                    last_digest = digest
                    print("[offline] frame pushed")
            except Exception as push_exc:
                print(f"Could not push offline frame: {_safe_detail(push_exc)}")
            if _should_alert(failures):
                notify.send(
                    "Tidbyt Monarch is failing",
                    f"**{failures}** consecutive failed cycles.\n\n"
                    f"View: `{view}`\n\n`{_safe_detail(exc)}`",
                    priority=7,
                )
        else:
            # --- push: failure here keeps the session and the cache ------
            try:
                digest = hashlib.sha256(image).hexdigest()
                if digest == last_digest:
                    # Same pixels as the last push; both Tidbyt and Tronbyt
                    # keep showing what they already have.
                    print(f"[{view}] unchanged, skipping push")
                else:
                    result = await _push(image)
                    last_digest = digest
                    detail = f" {data}" if config.DEBUG_VALUES else ""
                    print(f"[{view}] {len(image)}B sha={digest[:8]} -> {result}{detail}")
                if failures:
                    print(f"recovered after {failures} failed cycle(s)")
                failures = 0
                index += 1
            except Exception as exc:
                failures += 1
                print(f"Push failed on {view} ({failures} in a row): {_safe_detail(exc)}")
                if _should_alert(failures):
                    notify.send(
                        "Tidbyt Monarch cannot reach the display",
                        f"**{failures}** consecutive failed pushes. Data cache is kept.\n\n"
                        f"`{_safe_detail(exc)}`",
                        priority=6,
                    )

        try:
            await asyncio.wait_for(stop.wait(), timeout=config.UPDATE_INTERVAL)
        except asyncio.TimeoutError:
            pass

    if source is not None:
        await source.close()
    print("stopped")


def main() -> None:
    try:
        asyncio.run(_run())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
