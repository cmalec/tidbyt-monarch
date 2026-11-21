"""Render Monarch metrics into 64x32 WebP frames.

Rules baked in here:
- 1px margin on every edge, so nothing is clipped by the panel border.
- Lossless WebP, because a lossy encode tints black pixels and that reads as
  stray lit LEDs on the hardware.
- Every value is measured and shrunk until it fits, never truncated silently.
- A missing value is neutral, never green: an absent number is not good news.
"""
import io
import math

from PIL import Image, ImageDraw, ImageFont

WIDTH, HEIGHT = 64, 32
MARGIN = 1

COLOR_BG = (0, 0, 0)
COLOR_TEXT = (255, 255, 255)
# labels are white everywhere so the only colour on screen is the value
COLOR_LABEL = (255, 255, 255)
# accent blue is reserved for data names, not captions
COLOR_ACCENT = (120, 200, 255)
COLOR_POS = (80, 220, 120)
COLOR_NEG = (255, 110, 110)
COLOR_BAR_BG = (40, 40, 40)

GRID_VALUE_SIZES = (11, 10, 9, 8, 7, 6)

FONT_REGULAR = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
FONT_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"


def _font(size: int, bold: bool = False):
    path = FONT_BOLD if bold else FONT_REGULAR
    try:
        return ImageFont.truetype(path, size)
    except OSError:
        return ImageFont.load_default()


def _bbox(text: str, font):
    return font.getbbox(text)


def _measure(text: str, font) -> tuple[int, int]:
    bbox = _bbox(text, font)
    return bbox[2] - bbox[0], bbox[3] - bbox[1]


def _ink_bottom(text: str, font) -> int:
    """Offset from the draw origin to the last ink row.

    getbbox height omits the top offset, so placing text with
    y + height leaves ink lower than expected and clips on the last row.
    """
    return _bbox(text, font)[3]


def _fit(text: str, max_w: int, sizes, bold: bool = True):
    """Largest font in `sizes` (descending) whose rendering fits max_w."""
    fallback = _font(min(sizes), bold)
    for size in sizes:
        font = _font(size, bold)
        if _measure(text, font)[0] <= max_w:
            return font
    return fallback


def _ellipsize(text: str, max_w: int, size: int, bold: bool = False) -> str:
    font = _font(size, bold)
    if _measure(text, font)[0] <= max_w:
        return text
    while text and _measure(text + "...", font)[0] > max_w:
        text = text[:-1]
    return (text + "...") if text else "..."


def _draw_centered(draw, text: str, y: int, sizes, color, bold: bool = True,
                   max_w: int | None = None) -> None:
    """Draw text horizontally centered, clamped inside the bottom margin."""
    limit = (max_w or WIDTH) - 2 * MARGIN
    font = _fit(text, limit, sizes, bold)
    if _measure(text, font)[0] > limit:
        # still too wide at the smallest size: ellipsize instead of clipping
        text = _ellipsize(text, limit, min(sizes), bold)
        font = _font(min(sizes), bold)
    bbox = _bbox(text, font)
    y = min(y, HEIGHT - MARGIN - bbox[3])
    y = max(y, MARGIN)
    # subtract the left bearing so the ink, not the advance box, is centered
    x = (WIDTH - (bbox[2] - bbox[0])) // 2 - bbox[0]
    draw.text((x, y), text, fill=color, font=font)


def _label(draw, text: str, color=COLOR_LABEL) -> None:
    _draw_centered(draw, text, MARGIN, [8, 7, 6], color, bold=False)


def _fit_name(text: str, max_w: int) -> tuple[str, object]:
    """Best rendering of a name: whole string at the largest size that fits,
    else the most characters that fit at a smaller size."""
    for size in (7, 6):
        font = _font(size)
        if _measure(text, font)[0] <= max_w:
            return text, font
    size = 6
    return _ellipsize(text, max_w, size), _font(size)


def _finite(value):
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _tier(value):
    """Split a magnitude into (sign, amount, unit, decimals).

    Thresholds are checked against the value rounded to the unit's precision,
    so 999.6 becomes 1.0K rather than 1000, and 999_500 becomes 1.0M rather
    than 1000K.
    """
    if value is None:
        return "", 0.0, "", 0
    if value < 0.5 and value > -0.5:
        return "", 0.0, "", 0  # avoids "-$0"
    sign = "-" if value < 0 else ""
    v = abs(value)
    if v >= 999_500:
        return sign, v / 1_000_000, "M", 2
    if v >= 9_950:
        return sign, v / 1_000, "K", 0
    if v >= 999.5:
        return sign, v / 1_000, "K", 1
    return sign, v, "", 0


def _trim(number: float, decimals: int) -> str:
    """Fixed precision without trailing noise, but never dropping to a bare
    integer when a decimal was asked for: 1.00 -> 1.0, 1.24 -> 1.24."""
    text = f"{number:.{decimals}f}"
    if "." in text:
        text = text.rstrip("0")
        if text.endswith("."):
            text += "0"
    return text or "0"


def money(value) -> str:
    """Currency with enough precision to stay honest: $987, $8.2K, $42K,
    $412K, $1.24M, $999K, -$412K."""
    number = _finite(value)
    if number is None:
        return "n/a"
    sign, amount, unit, decimals = _tier(number)
    return f"{sign}${_trim(amount, decimals)}{unit}"


def compact_money(value) -> str:
    """Money sized for a narrow grid cell: at most 7 characters with a sign.

    Callers should still measure: `dashboard_fit_report` is the authority on
    whether a string fits its cell.
    """
    number = _finite(value)
    if number is None:
        return "n/a"
    sign, amount, unit, decimals = _tier(number)
    if unit == "M":
        decimals = 1
    return f"{sign}${_trim(amount, decimals)}{unit}"


def _encode(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="WEBP", lossless=True)
    return buf.getvalue()


def _blank():
    img = Image.new("RGB", (WIDTH, HEIGHT), COLOR_BG)
    return img, ImageDraw.Draw(img)


def _bar(draw, y: int, height: int, pct, color) -> None:
    """Progress bar, drawn only for a positive percentage."""
    left, right = MARGIN, WIDTH - MARGIN - 1
    draw.rectangle([left, y, right, y + height - 1], fill=COLOR_BAR_BG)
    if pct is None or pct <= 0:
        return
    span = right - left
    width = max(1, min(int(round(span * min(pct, 100.0) / 100.0)), span))
    draw.rectangle([left, y, left + width - 1, y + height - 1], fill=color)


def render_networth(data: dict) -> bytes:
    img, draw = _blank()
    _label(draw, "NET WORTH")
    value = _finite(data.get("value"))
    color = COLOR_TEXT if value is None else (COLOR_POS if value >= 0 else COLOR_NEG)
    _draw_centered(draw, money(value), 12, [20, 18, 16, 14, 12], color)
    return _encode(img)


def render_goal(data: dict) -> bytes:
    img, draw = _blank()
    if not data.get("name"):
        _label(draw, "NO GOAL")
        return _encode(img)

    name, name_font = _fit_name(str(data["name"]), WIDTH - 2 * MARGIN)
    draw.text((MARGIN, MARGIN), name, fill=COLOR_ACCENT, font=name_font)

    pct = _finite(data.get("pct"))
    color = COLOR_TEXT if pct is None else (COLOR_POS if pct <= 100 else COLOR_NEG)
    _draw_centered(draw, f"{pct:.0f}%" if pct is not None else "n/a",
                   9, [16, 14, 12], color)
    _bar(draw, 26, 4, pct, COLOR_POS)
    return _encode(img)


def render_budget(data: dict) -> bytes:
    img, draw = _blank()
    if data.get("missing"):
        _label(draw, "NO CATEGORY", color=COLOR_NEG)
        _draw_centered(draw, _ellipsize(str(data["missing"]), WIDTH - 2, 9),
                       12, [10, 8, 7], COLOR_TEXT, bold=False)
        return _encode(img)

    month = data.get("month") or ""
    label = "BUDGET" if data.get("name") == "TOTAL" else str(data.get("name") or "BUDGET")
    _label(draw, _ellipsize(f"{label} {month}".strip(), WIDTH - 2, 7))

    pct = _finite(data.get("pct"))
    if pct is None:
        _draw_centered(draw, "n/a", 9, [16, 14, 12], COLOR_TEXT)
        return _encode(img)

    color = COLOR_POS if pct <= 100 else COLOR_NEG
    _draw_centered(draw, f"{pct:.0f}%", 8, [18, 16, 14, 12], color)
    _bar(draw, 25, 3, pct, color)
    return _encode(img)


def render_cashflow(data: dict) -> bytes:
    img, draw = _blank()
    month = data.get("month") or ""
    _label(draw, f"CASHFLOW {month}".strip())

    savings = _finite(data.get("savings"))
    if savings is None:
        text, color = "n/a", COLOR_TEXT
    else:
        text = ("+" if savings >= 0 else "") + money(savings)
        color = COLOR_POS if savings >= 0 else COLOR_NEG
    _draw_centered(draw, text, 9, [16, 14, 12], color)

    income = _finite(data.get("income"))
    expense = _finite(data.get("expense"))
    if income is not None and expense is not None:
        small = f"in {money(income)} out {money(expense)}"
        _draw_centered(draw, small, 23, [6, 5], COLOR_TEXT, bold=False)
    return _encode(img)


def render_bill(data: dict) -> bytes:
    img, draw = _blank()
    if not data.get("name"):
        _label(draw, "NO BILL FOUND")
        return _encode(img)

    name, name_font = _fit_name(str(data["name"]), WIDTH - 2 * MARGIN)
    draw.text((MARGIN, MARGIN), name, fill=COLOR_ACCENT, font=name_font)
    _draw_centered(draw, money(data.get("amount")), 9, [16, 14, 12], COLOR_TEXT)

    days = data.get("days")
    if isinstance(days, int):
        when = "today" if days <= 0 else ("tomorrow" if days == 1 else f"in {days}d")
        _draw_centered(draw, when, 23, [6, 5], COLOR_ACCENT, bold=False)
    return _encode(img)


def _dashboard_cells(data: dict) -> list[dict]:
    """Build the four grid cells, including their fitted fonts."""
    networth = data.get("networth") or {}
    budget = data.get("budget") or {}
    cashflow = data.get("cashflow") or {}

    nw = _finite(networth.get("value"))
    pct = _finite(budget.get("pct"))
    rate = _finite(cashflow.get("rate"))
    savings = _finite(cashflow.get("savings"))

    def value_color(number, good):
        # a missing number is neutral, never green
        return COLOR_TEXT if number is None else (COLOR_POS if good else COLOR_NEG)

    specs = [
        ("NW", compact_money(nw), value_color(nw, (nw or 0) >= 0)),
        ("BUD", f"{pct:.0f}%" if pct is not None else "n/a",
         value_color(pct, (pct or 0) <= 100)),
        ("SAVE", f"{rate * 100:.0f}%" if rate is not None else "n/a",
         value_color(rate, (rate or 0) >= 0)),
        ("CF", "n/a" if savings is None else
         (("+" if savings >= 0 else "") + compact_money(savings)),
         value_color(savings, (savings or 0) >= 0)),
    ]

    cells = []
    cell_w, cell_h = WIDTH // 2, HEIGHT // 2
    for idx, (label, value, value_color) in enumerate(specs):
        x = (idx % 2) * cell_w
        y = (idx // 2) * cell_h

        label_font = _fit(label, cell_w - 2, [7, 6, 5], bold=True)
        label_bbox = _bbox(label, label_font)
        label_bottom = y + label_bbox[3] - 1  # last ink row

        # Largest size that fits the cell width AND leaves one clear row
        # between the label ink and the value ink.
        value_font = None
        value_y = y + cell_h - 1
        widest_fit = None
        for size in GRID_VALUE_SIZES:
            candidate = _font(size, bold=True)
            if _measure(value, candidate)[0] > cell_w - 2:
                continue
            if widest_fit is None:
                widest_fit = (candidate, y + cell_h - _ink_bottom(value, candidate) - 1)
            candidate_y = y + cell_h - _ink_bottom(value, candidate) - 1
            candidate_top = candidate_y + _bbox(value, candidate)[1]
            if candidate_top >= label_bottom + 2:
                value_font, value_y = candidate, candidate_y
                break
        if value_font is None:
            # nothing satisfied the gap rule; keep the widest that fits
            value_font, value_y = widest_fit or (
                _font(min(GRID_VALUE_SIZES), bold=True),
                y + cell_h - _ink_bottom(value, _font(min(GRID_VALUE_SIZES), bold=True)) - 1,
            )

        value_bbox = _bbox(value, value_font)
        value_top = value_y + value_bbox[1]
        cells.append({
            "x": x, "y": y, "w": cell_w, "h": cell_h,
            "label": label, "value": value,
            "label_color": COLOR_LABEL, "value_color": value_color,
            "label_font": label_font, "value_font": value_font,
            "label_x": x + (cell_w - (label_bbox[2] - label_bbox[0])) // 2 - label_bbox[0],
            "value_y": value_y,
            "value_x": x + (cell_w - (value_bbox[2] - value_bbox[0])) // 2 - value_bbox[0],
            "fits": _measure(value, value_font)[0] <= cell_w - 2,
            "value_w": _measure(value, value_font)[0],
            "gap": value_top - label_bottom - 1,
        })
    return cells


def dashboard_fit_report(data: dict) -> list[str]:
    """Problems a caller can assert on: a value too wide or too tall for its cell."""
    problems = []
    for cell in _dashboard_cells(data):
        if not cell["fits"]:
            problems.append(
                f"dashboard {cell['label']}: {cell['value']!r} is {cell['value_w']}px, "
                f"cell is {cell['w'] - 2}px"
            )
        if cell["gap"] < 1:
            problems.append(
                f"dashboard {cell['label']}: only {cell['gap']}px between label and value"
            )
    return problems


def render_dashboard(data: dict) -> bytes:
    """Four metrics in a 2x2 grid: net worth, budget, savings rate, cashflow."""
    img, draw = _blank()
    for cell in _dashboard_cells(data):
        draw.text((cell["label_x"], cell["y"]), cell["label"],
                  fill=cell["label_color"], font=cell["label_font"])
        draw.text((cell["value_x"], cell["value_y"]), cell["value"],
                  fill=cell["value_color"], font=cell["value_font"])
    return _encode(img)


def render_error(reason: str = "") -> bytes:
    img, draw = _blank()
    _label(draw, "MONARCH", color=COLOR_NEG)
    _draw_centered(draw, "OFFLINE", 9, [16, 14, 12], COLOR_TEXT)
    if reason:
        _draw_centered(draw, str(reason), 23, [6, 5], COLOR_ACCENT, bold=False)
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
