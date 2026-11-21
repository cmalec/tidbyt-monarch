"""Render every view from synthetic data and write 8x PNGs for inspection.

    python -m tools.preview /out
"""
import io
import os
import sys

from PIL import Image

from app.renderer import dashboard_fit_report, render, render_error, money

SYNTHETIC = {
    "dashboard": {
        "networth": {"value": 1_786_495.49},
        "budget": {"name": "TOTAL", "planned": 24993, "actual": 18692, "pct": 74.8},
        "cashflow": {"income": 24417, "expense": 18867, "savings": 5549.54, "rate": 0.2273},
    },
    "networth": {"value": 412_345.67, "accounts": 9},
    "budget": {"name": "TOTAL", "planned": 4200, "actual": 3100, "pct": 73.8, "month": "Nov"},
    "goal": {"name": "Emergency Fund", "target": 20000, "current": 13600, "pct": 68.0},
    "cashflow": {"income": 8100, "expense": 5740, "savings": 2360, "month": "Nov"},
    "bill": {"name": "Mortgage", "amount": 2140, "days": 6},
}

# Edge cases worth eyeballing: huge number, negative cashflow, long names, no data.
EDGE = {
    "dashboard": {
        "networth": {"value": -1_234_567},
        "budget": {"name": "TOTAL", "planned": 1000, "actual": 1450, "pct": 145.0},
        "cashflow": {"income": 8100, "expense": 12000, "savings": -3900, "rate": -0.48},
    },
    "networth": {"value": -1_234_567, "accounts": 3},
    "budget": {"name": "TOTAL", "planned": 1000, "actual": 1450, "pct": 145.0, "month": "Nov"},
    "goal": {"name": "Kitchen Remodel And Then Some", "target": 50000, "current": 50000, "pct": 100.0},
    "cashflow": {"income": 8100, "expense": 12000, "savings": -3900, "month": "Nov"},
    "bill": {"name": "American Express Platinum Card", "amount": 12890.44, "days": 0},
}

failures = []


def emit(view: str, data: dict, out_dir: str, label: str | None = None) -> None:
    webp = render(view, data)
    img = Image.open(io.BytesIO(webp)).convert("RGB")
    assert img.size == (64, 32), img.size
    up = img.resize((img.width * 8, img.height * 8), Image.Resampling.NEAREST)
    path = os.path.join(out_dir, f"{label or view}.png")
    up.save(path)
    print(f"{label or view:14} {len(webp):5}B -> {path}")


def check_fit() -> None:
    """No rendered frame may have lit pixels touching the frame edge."""
    for name, data in list(SYNTHETIC.items()) + list(EDGE.items()):
        img = Image.open(io.BytesIO(render(name, data))).convert("RGB")
        px = img.load()  # type: ignore[assignment]
        for x in (0, img.width - 1):
            if any(px[x, y] != (0, 0, 0) for y in range(img.height)):
                failures.append(f"{name}: lit pixel on vertical edge x={x}")
        for y in (0, img.height - 1):
            if any(px[x, y] != (0, 0, 0) for x in range(img.width)):
                failures.append(f"{name}: lit pixel on horizontal edge y={y}")


def check_dashboard() -> None:
    """Every dashboard value must fit its 32px cell."""
    for label, data in (("synthetic", SYNTHETIC["dashboard"]), ("edge", EDGE["dashboard"])):
        for problem in dashboard_fit_report(data):
            failures.append(f"dashboard[{label}]: {problem}")


def check_money() -> None:
    cases = {
        987: "$987",
        8_200: "$8.2K",
        42_000: "$42K",
        412_345: "$412K",
        1_240_000: "$1.24M",
        1_234_567: "$1.23M",
        12_400_000: "$12.4M",
        -412_345: "-$412K",
    }
    for value, expected in cases.items():
        got = money(value)
        if got != expected:
            failures.append(f"money({value}) = {got!r}, expected {expected!r}")


def main() -> int:
    out_dir = sys.argv[1] if len(sys.argv) > 1 else "/tmp/preview"
    os.makedirs(out_dir, exist_ok=True)
    for view, data in SYNTHETIC.items():
        emit(view, data, out_dir)
    print("-- edge cases --")
    for view, data in EDGE.items():
        emit(view, data, out_dir, label=f"{view}-edge")
    err = render_error("RuntimeError")
    Image.open(io.BytesIO(err)).convert("RGB").resize((512, 256), Image.Resampling.NEAREST).save(
        os.path.join(out_dir, "error.png")
    )
    print("-- checks --")
    check_fit()
    check_dashboard()
    check_money()
    for problem in failures:
        print("FAIL:", problem)
    print("ok" if not failures else f"{len(failures)} failures")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
