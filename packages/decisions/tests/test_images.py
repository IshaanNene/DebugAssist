import base64
import io

import pytest
from PIL import Image

from debugassist.decisions.images import fit_image, prepare_images
from debugassist.decisions.schema import MAX_IMAGE_PIXELS, ClefRequestError


def png(w: int, h: int, noise: bool = False) -> bytes:
    img = Image.effect_noise((w, h), 80).convert("RGB") if noise else Image.new("RGB", (w, h), (20, 120, 200))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def decode(url: str) -> Image.Image:
    return Image.open(io.BytesIO(base64.b64decode(url.split(",", 1)[1])))


def test_small_png_passes_through_unchanged() -> None:
    raw = png(64, 64)
    mime, data = fit_image(raw)
    assert mime == "image/png" and data == raw


def test_oversized_pixels_are_downscaled() -> None:
    mime, data = fit_image(Image.new("RGB", (5000, 4000)))  # 20 MP
    img = Image.open(io.BytesIO(data))
    assert img.width * img.height <= MAX_IMAGE_PIXELS
    assert mime in ("image/png", "image/webp")


def test_oversized_bytes_are_recompressed() -> None:
    raw = png(1800, 1800, noise=True)  # noisy PNG ≫ 1 MiB
    assert len(raw) > 1024 * 1024
    _, data = fit_image(raw, max_bytes=1024 * 1024)
    assert len(data) <= 1024 * 1024


def test_prepare_images_returns_data_urls_within_total_budget() -> None:
    urls = prepare_images([png(1500, 1500, noise=True) for _ in range(4)])
    assert len(urls) == 4
    total = sum(len(base64.b64decode(u.split(",", 1)[1])) for u in urls)
    assert total <= 8 * 1024 * 1024
    assert all(u.startswith("data:image/") for u in urls)
    decode(urls[0]).load()


def test_data_url_and_path_inputs(tmp_path: object) -> None:
    raw = png(10, 10)
    url = "data:image/png;base64," + base64.b64encode(raw).decode()
    assert prepare_images([url])[0] == url


def test_too_many_images() -> None:
    with pytest.raises(ClefRequestError):
        prepare_images([png(4, 4)] * 5)
