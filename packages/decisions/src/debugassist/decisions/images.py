"""Image preparation for Clef's ``images`` field: normalise to data URLs and fit the limits.

Limits (Workers AI): ≤4 images; PNG/JPEG/WebP; ≤4 MiB and ≤16 MP each; ≤8 MiB total decoded.
Oversized images are downscaled and, if still too large, re-encoded as WebP with falling quality.
"""

from __future__ import annotations

import base64
import io
import math
from pathlib import Path

from PIL import Image

from debugassist.decisions.schema import (
    MAX_IMAGE_BYTES,
    MAX_IMAGE_PIXELS,
    MAX_IMAGES,
    MAX_IMAGES_TOTAL_BYTES,
    ClefRequestError,
)

type ImageSource = bytes | Path | str | Image.Image  # str = data URL or file path

_FORMATS = {"PNG": "image/png", "JPEG": "image/jpeg", "WEBP": "image/webp"}


def _load(src: ImageSource) -> tuple[Image.Image, bytes | None, str | None]:
    if isinstance(src, Image.Image):
        return src, None, None
    if isinstance(src, str) and src.startswith("data:"):
        header, _, data = src.partition(",")
        raw = base64.b64decode(data)
        return Image.open(io.BytesIO(raw)), raw, header[5:].split(";")[0]
    raw = Path(src).read_bytes() if isinstance(src, str | Path) else src
    img = Image.open(io.BytesIO(raw))
    return img, raw, _FORMATS.get(img.format or "")


def _encode(img: Image.Image, fmt: str, quality: int = 90) -> bytes:
    buf = io.BytesIO()
    if fmt == "JPEG" and img.mode not in ("RGB", "L"):
        img = img.convert("RGB")
    img.save(buf, format=fmt, quality=quality, optimize=True)
    return buf.getvalue()


def fit_image(src: ImageSource, *, max_bytes: int = MAX_IMAGE_BYTES) -> tuple[str, bytes]:
    """Return ``(mime, bytes)`` within the per-image byte and pixel limits."""
    img, raw, mime = _load(src)
    img.load()
    w, h = img.size
    if (
        raw is not None
        and mime is not None
        and mime in _FORMATS.values()
        and w * h <= MAX_IMAGE_PIXELS
        and len(raw) <= max_bytes
    ):
        return mime, raw
    if w * h > MAX_IMAGE_PIXELS:
        scale = math.sqrt(MAX_IMAGE_PIXELS / (w * h)) * 0.99
        img = img.resize((max(1, int(w * scale)), max(1, int(h * scale))), Image.Resampling.LANCZOS)  # pyright: ignore[reportUnknownMemberType]
    data = _encode(img, "PNG")
    if len(data) <= max_bytes:
        return "image/png", data
    for quality in (90, 80, 65, 50, 35):
        data = _encode(img, "WEBP", quality)
        if len(data) <= max_bytes:
            return "image/webp", data
    while len(data) > max_bytes:  # last resort: keep halving resolution
        img = img.resize((max(1, img.width // 2), max(1, img.height // 2)), Image.Resampling.LANCZOS)  # pyright: ignore[reportUnknownMemberType]
        data = _encode(img, "WEBP", 60)
    return "image/webp", data


def prepare_images(sources: list[ImageSource]) -> list[str]:
    """Normalise up to four images to data URLs that satisfy every Clef image limit."""
    if len(sources) > MAX_IMAGES:
        raise ClefRequestError(f"at most {MAX_IMAGES} images, got {len(sources)}")
    if not sources:
        return []
    per_image = min(MAX_IMAGE_BYTES, MAX_IMAGES_TOTAL_BYTES // len(sources))
    out: list[str] = []
    for src in sources:
        mime, data = fit_image(src, max_bytes=per_image)
        out.append(f"data:{mime};base64,{base64.b64encode(data).decode()}")
    return out
