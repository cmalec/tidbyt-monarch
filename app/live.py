"""Fetch the live views from Monarch and save each rendered frame plus an 8x
upscale, printing the parsed values. Run inside the image."""
import asyncio
import io
import os
import sys

from PIL import Image

from app import config
from app.monarch_client import MonarchSource
from app.main import FETCHERS
from app.renderer import render

OUT = "/out"


async def main():
    os.makedirs(OUT, exist_ok=True)
    source = MonarchSource()
    print("session:", await source.connect())

    for view in config.VIEWS:
        try:
            data = await getattr(source, FETCHERS[view])()
        except Exception as exc:
            print(f"{view}: FETCH FAILED {type(exc).__name__}: {exc}")
            continue
        webp = render(view, data)
        img = Image.open(io.BytesIO(webp)).convert("RGB")
        img.resize((img.width * 8, img.height * 8), Image.Resampling.NEAREST).save(
            f"{OUT}/live-{view}.png"
        )
        print(f"{view:9} {len(webp):5}B  {data}")


if __name__ == "__main__":
    asyncio.run(main())
    sys.exit(0)
