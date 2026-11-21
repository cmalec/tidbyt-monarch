"""Verify the grid's colour rules by sampling rendered pixels per cell."""
import io
import sys
from collections import Counter

from PIL import Image

sys.path.insert(0, "/app")

from app.renderer import render  # noqa: E402

POS = (80, 220, 120)
NEG = (255, 110, 110)
TEXT = (255, 255, 255)

CASES = [
    ("all positive", {
        "networth": {"value": 1_786_495},
        "budget": {"pct": 75.7},
        "cashflow": {"rate": 0.218, "savings": 5325.54},
    }, {"NW": TEXT, "BUD": POS, "SAVE": POS, "CF": POS}),
    ("negative net worth", {
        "networth": {"value": -1_234_567},
        "budget": {"pct": 75.7},
        "cashflow": {"rate": 0.218, "savings": 5325.54},
    }, {"NW": NEG, "BUD": POS, "SAVE": POS, "CF": POS}),
    ("over budget, negative flow", {
        "networth": {"value": 1_786_495},
        "budget": {"pct": 145.0},
        "cashflow": {"rate": -0.48, "savings": -3900},
    }, {"NW": TEXT, "BUD": NEG, "SAVE": NEG, "CF": NEG}),
]

CELLS = {"NW": (0, 0), "BUD": (32, 0), "SAVE": (0, 16), "CF": (32, 16)}
failures = []

for label, data, expected in CASES:
    img = Image.open(io.BytesIO(render("dashboard", data))).convert("RGB")
    px = img.load()
    for cell, (x0, y0) in CELLS.items():
        colors = Counter()
        for y in range(y0 + 6, y0 + 16):          # value rows only
            for x in range(x0, x0 + 32):
                c = px[x, y]
                if c != (0, 0, 0):
                    colors[c] += 1
        if not colors:
            failures.append(f"{label} {cell}: no lit pixels")
            continue
        dominant = colors.most_common(1)[0][0]
        want = expected[cell]
        # antialiasing produces blends; accept anything closer to the target
        dist = sum(abs(a - b) for a, b in zip(dominant, want))
        ok = dist < 90
        print(f"{label:28} {cell:5} dominant={dominant} want={want} {'ok' if ok else 'MISMATCH'}")
        if not ok:
            failures.append(f"{label} {cell}: got {dominant}, want {want}")

print()
for f in failures:
    print("FAIL:", f)
print("colour checks ok" if not failures else f"{len(failures)} failures")
sys.exit(0 if not failures else 1)
