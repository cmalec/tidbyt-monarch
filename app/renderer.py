"""Render Monarch metrics into 64x32 WebP frames.

Rules baked in here:
- 1px margin on every edge, so nothing is clipped by the panel border.
- Lossless WebP, because a lossy encode tints black pixels and that reads as
  stray lit LEDs on the hardware.
- Every value is measured and shrunk until it fits, never truncated silently.
"""
import io

from PIL import Image, ImageDraw, ImageFont

WIDTH, HEIGHT = 64, 32
MARGIN = 1

COLOR_BG = (0, 0, 0)
COLOR_TEXT = (255, 255, 255)
COLOR_LABEL = (120, 200, 255)
COLOR_POS = (80, 220, 120)
COLOR_NEG = (255, 110, 110)
COLOR_BAR_BG = (40, 40, 40)

FONT_REGULAR = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
FONT_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"


def _font(size: int, bold: bool = False):
    path = FONT_BOLD if bold else FONT_REGULAR
    try:
        return ImageFont.truetype(path, size)
    except OSError:
        return ImageFont.load_default()


def _measure(text: str, font) -> tuple[int, int]:
    bbox = font.getbbox(text)
    return bbox[2] - bbox[0], bbox[3] - bbox[1]


def _ink_bottom(text: str, font) -> int:
    """Offset from the draw origin to the last ink row.

    getbbox height omits the top offset, so placing text with
    y + height leaves ink lower than expected and clips on the last row.
    """
    return font.getbbox(text)[3]


def _fit(text: str, max_w: int, sizes, bold: bool = True):
    """Largest font in `sizes` (descending) whose rendering fits max_w."""
    fallback = _font(min(sizes), bold)
    for size in sizes:
        font = _font(size, bold)
        if _measure(text, font)[0] <= max_w:
            return font
    return fallback


def _draw_centered(draw, text: str, y: int, sizes, color, bold: bool = True,
                   max_w: int | None = None) -> None:
    """Draw text horizontally centered, clamped inside the bottom margin."""
    font = _fit(text, (max_w or WIDTH) - 2 * MARGIN, sizes, bold)
    w, _ = _measure(text, font)
    y = min(y, HEIGHT - MARGIN - _ink_bottom(text, font))
    y = max(y, MARGIN)
    draw.text(((WIDTH - w) // 2, y), text, fill=color, font=font)


def _label(draw, text: str, color=COLOR_LABEL) -> None:
    _draw_centered(draw, text, MARGIN, [8, 7, 6], color, bold=False)


def _ellipsize(text: str, max_w: int, size: int) -> str:
    font = _font(size)
    if _measure(text, font)[0] <= max_w:
        return text
    while text and _measure(text + "...", font)[0] > max_w:
        text = text[:-1]
    return (text + "...") if text else "..."


def _fit_name(text: str, max_w: int) -> tuple[str, object]:
    """Best rendering of a name: whole string at the largest size that fits,
    else the most characters that fit at a smaller size."""
    for size in (7, 6):
        font = _font(size)
        if _measure(text, font)[0] <= max_w:
            return text, font
    size = 6
    return _ellipsize(text, max_w, size), _font(size)


def money(value) -> str:
    """Compact currency: $987, $8.2K, $42K, $412K, $1.24M, -$412K."""
    if value is None:
        return "n/a"
    sign = "-" if value < 0 else ""
    v = abs(float(value))
    if v >= 1_000_000:
        return f"{sign}${v / 1_000_000:.2f}M" if v < 10_000_000 else f"{sign}${v / 1_000_000:.1f}M"
    if v >= 10_000:
        return f"{sign}${v / 1_000:.0f}K"
    if v >= 1_000:
        return f"{sign}${v / 1_000:.1f}K"
    return f"{sign}${v:.0f}"


def _encode(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="WEBP", lossless=True)
    return buf.getvalue()


def _blank():
    img = Image.new("RGB", (WIDTH, HEIGHT), COLOR_BG)
    return img, ImageDraw.Draw(img)


def render_networth(data: dict) -> bytes:
    img, draw = _blank()
    _label(draw, "NET WORTH")
    _draw_centered(draw, money(data.get("value")), 12, [20, 18, 16, 14, 12], COLOR_TEXT)
    return _encode(img)


def render_goal(data: dict) -> bytes:
    img, draw = _blank()
    if not data.get("name"):
        _label(draw, "NO GOAL")
        return _encode(img)

    name, name_font = _fit_name(data["name"], WIDTH - 2 * MARGIN)
    draw.text((MARGIN, MARGIN), name, fill=COLOR_LABEL, font=name_font)

    pct = data.get("pct")
    text = f"{pct:.0f}%" if pct is not None else "n/a"
    _draw_centered(draw, text, 9, [16, 14, 12], COLOR_POS)

    bar_y, bar_h = 26, 4
    left, right = MARGIN, WIDTH - MARGIN - 1
    draw.rectangle([left, bar_y, right, bar_y + bar_h - 1], fill=COLOR_BAR_BG)
    if pct:
        fill_w = left + max(1, int((right - left) * min(pct, 100.0) / 100.0))
        draw.rectangle([left, bar_y, min(fill_w, right), bar_y + bar_h - 1], fill=COLOR_POS)
    return _encode(img)


def render_budget(data: dict) -> bytes:
    img, draw = _blank()
    if data.get("missing"):
        _label(draw, "NO CATEGORY", color=COLOR_NEG)
        _draw_centered(draw, data["missing"], 12, [10, 8, 7], COLOR_TEXT, bold=False)
        return _encode(img)

    month = data.get("month") or ""
    label = "BUDGET" if data.get("name") == "TOTAL" else data.get("name", "BUDGET")
    _label(draw, f"{label} {month}".strip()[:18])

    pct = data.get("pct")
    if pct is None:
        _draw_centered(draw, "n/a", 9, [16, 14, 12], COLOR_LABEL)
        return _encode(img)

    color = COLOR_POS if pct <= 100 else COLOR_NEG
    _draw_centered(draw, f"{pct:.0f}%", 8, [18, 16, 14, 12], color)

    bar_y, bar_h = 25, 3
    left, right = MARGIN, WIDTH - MARGIN - 1
    draw.rectangle([left, bar_y, right, bar_y + bar_h - 1], fill=COLOR_BAR_BG)
    fill_w = left + max(1, min(int((right - left) * pct / 100.0), right - left))
    draw.rectangle([left, bar_y, min(fill_w, right), bar_y + bar_h - 1], fill=color)
    return _encode(img)


def render_cashflow(data: dict) -> bytes:
    img, draw = _blank()
    month = data.get("month") or ""
    _label(draw, f"CASHFLOW {month}".strip())

    savings = data.get("savings")
    text = "n/a" if savings is None else (("+" if savings >= 0 else "") + money(savings))
    color = COLOR_POS if (savings or 0) >= 0 else COLOR_NEG
    _draw_centered(draw, text, 9, [16, 14, 12], color)

    if data.get("income") is not None and data.get("expense") is not None:
        small = f"in {money(data['income'])} out {money(data['expense'])}"
        _draw_centered(draw, small, 23, [6, 5], COLOR_TEXT, bold=False)
    return _encode(img)


def render_bill(data: dict) -> bytes:
    img, draw = _blank()
    if not data.get("name"):
        _label(draw, "NO BILL FOUND")
        return _encode(img)

    name, name_font = _fit_name(data["name"], WIDTH - 2 * MARGIN)
    draw.text((MARGIN, MARGIN), name, fill=COLOR_LABEL, font=name_font)
    _draw_centered(draw, money(data.get("amount")), 9, [16, 14, 12], COLOR_TEXT)

    days = data.get("days")
    if days is not None:
        when = "today" if days <= 0 else ("tomorrow" if days == 1 else f"in {days}d")
        _draw_centered(draw, when, 23, [6, 5], COLOR_LABEL, bold=False)
    return _encode(img)



def compact_money(value) -> str:
    """Money for a 32px-wide cell: at most 5 characters plus a sign."""
    if value is None:
        return "n/a"
    sign = "-" if value < 0 else ""
    v = abs(float(value))
    if v >= 1_000_000:
        return f"{sign}${v / 1_000_000:.1f}M"
    if v >= 10_000:
        return f"{sign}${v / 1_000:.0f}K"
    if v >= 1_000:
        return f"{sign}${v / 1_000:.1f}K"
    return f"{sign}${v:.0f}"


def _dashboard_cells(data: dict) -> list[dict]:
    """Build the four grid cells, including their fitted fonts."""
    networth = data.get("networth") or {}
    budget = data.get("budget") or {}
    cashflow = data.get("cashflow") or {}

    pct = budget.get("pct")
    rate = cashflow.get("rate")
    savings = cashflow.get("savings")

    specs = [
        ("NW", compact_money(networth.get("value")), COLOR_LABEL, COLOR_TEXT),
        ("BUD", f"{pct:.0f}%" if pct is not None else "n/a", COLOR_LABEL,
         COLOR_POS if (pct or 0) <= 100 else COLOR_NEG),
        ("SAVE", f"{rate * 100:.0f}%" if rate is not None else "n/a", COLOR_LABEL,
         COLOR_POS if (rate or 0) >= 0 else COLOR_NEG),
        ("CF", ("+" if (savings or 0) >= 0 else "") + compact_money(savings), COLOR_LABEL,
         COLOR_POS if (savings or 0) >= 0 else COLOR_NEG),
    ]

    cells = []
    cell_w, cell_h = WIDTH // 2, HEIGHT // 2
    for idx, (label, value, label_color, value_color) in enumerate(specs):
        x = (idx % 2) * cell_w
        y = (idx // 2) * cell_h
        label_font = _fit(label, cell_w - 2, [7, 6, 5], bold=True)
        value_font = _fit(value, cell_w - 2, [11, 10, 9, 8, 7, 6], bold=True)
        value_w = _measure(value, value_font)[0]
        cells.append({
            "x": x, "y": y, "w": cell_w, "h": cell_h,
            "label": label, "value": value,
            "label_color": label_color, "value_color": value_color,
            "label_font": label_font, "value_font": value_font,
            "fits": value_w <= cell_w - 2,
            "value_w": value_w,
        })
    return cells


def dashboard_fit_report(data: dict) -> list[str]:
    """Problems a caller can assert on: any value wider than its cell."""
    problems = []
    for cell in _dashboard_cells(data):
        if not cell["fits"]:
            problems.append(
                f"dashboard {cell['label']}: {cell['value']!r} is {cell['value_w']}px, "
                f"cell is {cell['w'] - 2}px"
            )
    return problems


def render_dashboard(data: dict) -> bytes:
    """Four metrics in a 2x2 grid: net worth, budget, savings rate, cashflow."""
    img, draw = _blank()
    for cell in _dashboard_cells(data):
        lw, _ = _measure(cell["label"], cell["label_font"])
        draw.text((cell["x"] + (cell["w"] - lw) // 2, cell["y"]),
                  cell["label"], fill=cell["label_color"], font=cell["label_font"])
        vw, _ = _measure(cell["value"], cell["value_font"])
        value_y = cell["y"] + cell["h"] - _ink_bottom(cell["value"], cell["value_font"]) - 1
        value_y = max(cell["y"] + 1, value_y)
        draw.text((cell["x"] + (cell["w"] - vw) // 2, value_y),
                  cell["value"], fill=cell["value_color"], font=cell["value_font"])
    return _encode(img)

def render_error(reason: str = "") -> bytes:
    img, draw = _blank()
    _label(draw, "MONARCH", color=COLOR_NEG)
    _draw_centered(draw, "OFFLINE", 9, [16, 14, 12], COLOR_TEXT)
    if reason:
        _draw_centered(draw, reason, 23, [6, 5], COLOR_LABEL, bold=False)
    return _encode(img)


RENDERERS = {
    "dashboard": render_dashboard,
    "networth": render_networth,
    "budget": render_budget,
    "goal": render_goal,
    "cashflow": render_cashflow,
    "bill": render_bill,
}


def render(view: str, data: dict) -> bytes:
    return RENDERERS[view](data)
