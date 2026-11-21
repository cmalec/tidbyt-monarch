"""Push each view once to the device, pausing so the rotation is visible."""
import asyncio
import time

from app import config
from app.main import FETCHERS
from app.monarch_client import MonarchSource
from app.push_client import push_image
from app.renderer import render


async def fetch_all(source):
    out = []
    for view in config.VIEWS:
        data = await getattr(source, FETCHERS[view])()
        out.append((view, render(view, data), data))
    return out


def main():
    source = MonarchSource()
    print("session:", asyncio.run(source.connect()))
    frames = asyncio.run(fetch_all(source))
    for view, webp, data in frames:
        result = push_image(webp, "monarch")
        print(f"[{view}] {data} -> {result}")
        time.sleep(10)
    print("done, last frame stays on screen")


if __name__ == "__main__":
    main()
