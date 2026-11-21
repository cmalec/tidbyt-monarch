"""Combine preview PNGs into one contact sheet for review."""
import os
import sys

from PIL import Image, ImageDraw

out_dir = sys.argv[1]
names = ["networth", "goal", "cashflow", "bill",
         "networth-edge", "goal-edge", "cashflow-edge", "bill-edge", "error"]

tiles = []
for name in names:
    path = os.path.join(out_dir, f"{name}.png")
    if os.path.exists(path):
        tiles.append((name, Image.open(path).convert("RGB")))

w = max(t.width for _, t in tiles)
h = max(t.height for _, t in tiles)
cols = 2
rows = (len(tiles) + cols - 1) // cols
sheet = Image.new("RGB", (cols * (w + 10) + 10, rows * (h + 26) + 10), (25, 25, 25))
draw = ImageDraw.Draw(sheet)
for idx, (name, tile) in enumerate(tiles):
    cx = 10 + (idx % cols) * (w + 10)
    cy = 10 + (idx // cols) * (h + 26)
    sheet.paste(tile, (cx, cy + 16))
    draw.text((cx, cy + 2), name, fill=(200, 200, 200))
sheet.save(os.path.join(out_dir, "contact.png"))
print("wrote", os.path.join(out_dir, "contact.png"), sheet.size)
