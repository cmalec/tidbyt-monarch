"""Combine preview PNGs into one contact sheet for review.

    python -m tools.contact <dir>
"""
import os
import sys

from PIL import Image, ImageDraw

DEFAULT_NAMES = [
    "dashboard", "networth", "budget", "goal", "cashflow", "bill",
    "dashboard-edge", "networth-edge", "budget-edge", "goal-edge",
    "cashflow-edge", "bill-edge", "error",
]


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: python -m tools.contact <dir>")
        return 2
    out_dir = sys.argv[1]
    tiles = []
    for name in DEFAULT_NAMES:
        path = os.path.join(out_dir, f"{name}.png")
        if os.path.exists(path):
            tiles.append((name, Image.open(path).convert("RGB")))
    if not tiles:
        print(f"no preview PNGs found in {out_dir}")
        return 1

    w = max(tile.width for _, tile in tiles)
    h = max(tile.height for _, tile in tiles)
    cols = 2
    rows = (len(tiles) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * (w + 10) + 10, rows * (h + 26) + 10), (25, 25, 25))
    draw = ImageDraw.Draw(sheet)
    for idx, (name, tile) in enumerate(tiles):
        cx = 10 + (idx % cols) * (w + 10)
        cy = 10 + (idx // cols) * (h + 26)
        sheet.paste(tile, (cx, cy + 16))
        draw.text((cx, cy + 2), name, fill=(200, 200, 200))
    path = os.path.join(out_dir, "contact.png")
    sheet.save(path)
    print("wrote", path, sheet.size)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
