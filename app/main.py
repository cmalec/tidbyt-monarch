"""Scheduler: pull Monarch data, render one view, push it, repeat."""
import asyncio
import time
import traceback

from app import config
from app.monarch_client import MonarchSource
from app.push_client import push_image
from app.renderer import render, render_error

FETCHERS = {
    "networth": "net_worth",
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


def main() -> None:
    print("=" * 50)
    print("Tidbyt Monarch")
    print("=" * 50)
    print(f"Monarch user: {config.MONARCH_EMAIL}")
    print(f"Device: {config.TIDBYT_DEVICE_ID} via {config.TIDBYT_API_BASE}")
    print(f"Views: {', '.join(config.VIEWS)}")
    print(f"Update interval: {config.UPDATE_INTERVAL}s")
    print("=" * 50)

    source = None
    index = 0
    while True:
        view = config.VIEWS[index % len(config.VIEWS)]
        try:
            if source is None:
                source = asyncio.run(_connect())
            image, data = asyncio.run(_frame(source, view))
            result = push_image(image)
            print(f"[{view}] {data} -> {result}")
            index += 1
        except Exception as exc:
            print(f"Error on view {view}: {type(exc).__name__}: {exc}")
            traceback.print_exc()
            # A stale session or a Monarch hiccup should not freeze the panel:
            # show a visible offline frame, and force a reconnect next cycle.
            source = None
            try:
                push_image(render_error(type(exc).__name__))
            except Exception as push_exc:
                print(f"Could not push offline frame: {push_exc}")

        time.sleep(config.UPDATE_INTERVAL)


if __name__ == "__main__":
    main()
