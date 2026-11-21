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
    w, h = _measure(text, font)
    y = min(y, HEIGHT - MARGIN - h)
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

    name = _ellipsize(data["name"], WIDTH - 2 * MARGIN, 7)
    draw.text((MARGIN, MARGIN), name, fill=COLOR_LABEL, font=_font(7))

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

    name = _ellipsize(data["name"], WIDTH - 2 * MARGIN, 7)
    draw.text((MARGIN, MARGIN), name, fill=COLOR_LABEL, font=_font(7))
    _draw_centered(draw, money(data.get("amount")), 9, [16, 14, 12], COLOR_TEXT)

    days = data.get("days")
    if days is not None:
        when = "today" if days <= 0 else ("tomorrow" if days == 1 else f"in {days}d")
        _draw_centered(draw, when, 23, [6, 5], COLOR_LABEL, bold=False)
    return _encode(img)


def render_error(reason: str = "") -> bytes:
    img, draw = _blank()
    _label(draw, "MONARCH", color=COLOR_NEG)
    _draw_centered(draw, "OFFLINE", 9, [16, 14, 12], COLOR_TEXT)
    if reason:
        _draw_centered(draw, reason, 23, [6, 5], COLOR_LABEL, bold=False)
    return _encode(img)


RENDERERS = {
    "networth": render_networth,
    "goal": render_goal,
    "cashflow": render_cashflow,
    "bill": render_bill,
}


def render(view: str, data: dict) -> bytes:
    return RENDERERS[view](data)
