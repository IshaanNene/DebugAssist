import base64
import io
import json

from PIL import Image

from debugassist.simulator.assets import battery_panel_png
from debugassist.simulator.browser import push_payload
from debugassist.simulator.personas import WEAK, personas


def test_personas_are_reproducible_and_weighted() -> None:
    a = personas(200, seed=3, previous_version_share=0.25)
    b = personas(200, seed=3, previous_version_share=0.25)
    assert a == b
    prev = sum(p.previous_version for p in a) / len(a)
    assert 0.15 < prev < 0.35
    assert {p.city for p in a} == {"sf", "nyc", "blr", "tokyo"}
    assert all(p.locale for p in a)


def test_bare_locales_share() -> None:
    ps = personas(300, seed=5, locales=["ar", "he"], locale_share=0.2)
    share = sum(p.locale in ("ar", "he") for p in ps) / len(ps)
    assert 0.12 < share < 0.28


def test_weak_profile_is_lossy_and_slow() -> None:
    assert WEAK.latency_ms >= 2000 and WEAK.loss_pct > 0


def test_push_payload_matches_client_decoder() -> None:
    raw = push_payload("/ride/abc")
    assert "=" not in raw and "+" not in raw and "/" not in raw
    padded = raw + "=" * (-len(raw) % 4)
    assert json.loads(base64.urlsafe_b64decode(padded))["deepLink"] == "/ride/abc"


def test_battery_panel_is_a_png() -> None:
    img = Image.open(io.BytesIO(battery_panel_png(29)))
    assert img.format == "PNG" and img.size == (720, 1480)
