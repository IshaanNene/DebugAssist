"""Images riders attach to bug reports (generated; these are OS screens, not the app)."""

from __future__ import annotations

import io

from PIL import Image, ImageDraw, ImageFont


def _font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for name in (
        "/System/Library/Fonts/SFNS.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default(size)


def battery_panel_png(app_percent: int = 29, app_name: str = "MiniRide", background_min: int = 17) -> bytes:
    """A phone 'Battery usage by app' settings screen where `app_name` dominates."""
    w, h = 720, 1480
    img = Image.new("RGB", (w, h), (246, 246, 248))
    d = ImageDraw.Draw(img)
    title, label, small = _font(52), _font(34), _font(28)
    d.text((48, 90), "Battery", font=title, fill=(20, 20, 24))
    d.text((48, 170), "Battery usage since last full charge", font=small, fill=(110, 110, 118))
    d.rounded_rectangle((40, 230, w - 40, 400), radius=28, fill=(255, 255, 255))
    d.text((72, 262), "34%", font=title, fill=(20, 20, 24))
    d.text((72, 336), "Phone is warm · Charging paused", font=small, fill=(196, 72, 40))
    rows = [
        (app_name, app_percent, (230, 160, 30)),
        ("Screen", 18, (90, 120, 220)),
        ("Maps", 9, (60, 170, 90)),
        ("Messages", 6, (60, 170, 220)),
        ("Music", 4, (220, 70, 110)),
        ("System", 3, (140, 140, 150)),
    ]
    y = 450
    d.rounded_rectangle((40, y - 20, w - 40, y + 110 * len(rows) + 10), radius=28, fill=(255, 255, 255))
    for name, pct, color in rows:
        d.rounded_rectangle((72, y + 6, 136, y + 70), radius=16, fill=color)
        d.text((160, y + 4), name, font=label, fill=(20, 20, 24))
        d.text((w - 150, y + 4), f"{pct}%", font=label, fill=(20, 20, 24))
        d.rounded_rectangle((160, y + 58, 160 + int((w - 260) * pct / 40), y + 70), radius=6, fill=color)
        y += 110
    d.text(
        (48, h - 120),
        f"{app_name} used battery in the background for {background_min} min",
        font=small,
        fill=(110, 110, 118),
    )
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()
