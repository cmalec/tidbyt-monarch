"""Measure the dashboard cell glyph widths at each candidate size."""
from app.renderer import _font, _measure

CELL = 32 - 2  # cell width minus 2px margin
values = ["$1.79M", "-$1.2M", "75%", "145%", "23%", "77%", "+$5.5K", "-$3.9K", "+$24.4K"]
labels = ["NW", "BUD", "SAVE", "CF"]

print(f"usable width per cell: {CELL}px\n")
for text in values:
    row = []
    for size in (11, 10, 9, 8, 7):
        w, _ = _measure(text, _font(size, bold=True))
        row.append(f"{size}pt={w}")
    biggest = max((s for s in (11, 10, 9, 8, 7)
                   if _measure(text, _font(s, bold=True))[0] <= CELL), default=None)
    print(f"{text:9} {'  '.join(row)}   -> largest that fits: {biggest}")
print()
for text in labels:
    w, h = _measure(text, _font(7, bold=True))
    print(f"{text:5} label 7pt width={w} height={h}")
