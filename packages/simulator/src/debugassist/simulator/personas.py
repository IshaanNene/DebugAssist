"""Simulated riders: city, device, locale, network profile and app version, drawn reproducibly."""

from __future__ import annotations

import random
from dataclasses import dataclass, field

DEVICES = [("Pixel 7", 0.35), ("Galaxy S24", 0.2), ("iPhone 15", 0.3), ("iPhone 13", 0.15)]
CITIES = [("sf", 0.35), ("nyc", 0.3), ("blr", 0.2), ("tokyo", 0.15)]
LOCALES = {"sf": "en-US", "nyc": "en-US", "blr": "en-IN", "tokyo": "ja-JP"}

# Playwright has no descriptor for Galaxy S24; emulate it explicitly.
CUSTOM_DEVICES: dict[str, dict[str, object]] = {
    "Galaxy S24": {
        "user_agent": "Mozilla/5.0 (Linux; Android 14; SM-S921B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Mobile Safari/537.36",
        "viewport": {"width": 384, "height": 832},
        "device_scale_factor": 3,
        "is_mobile": True,
        "has_touch": True,
    }
}


@dataclass(frozen=True)
class NetworkProfile:
    name: str
    latency_ms: int = 0
    download_kbps: int = 0  # 0 = unthrottled
    upload_kbps: int = 0
    loss_pct: float = 0.0  # share of requests that hit a lost packet and wait for retransmission
    retransmit_ms: tuple[int, int] = (1000, 3000)


GOOD = NetworkProfile("wifi")
WEAK = NetworkProfile("weak-3g", latency_ms=2000, download_kbps=250, upload_kbps=100, loss_pct=0.3)


@dataclass(frozen=True)
class Persona:
    idx: int
    city: str
    device: str
    locale: str
    network: NetworkProfile = GOOD
    previous_version: bool = False
    tags: dict[str, object] = field(default_factory=dict[str, object])


def _pick(rng: random.Random, weighted: list[tuple[str, float]]) -> str:
    return rng.choices([v for v, _ in weighted], [w for _, w in weighted])[0]


def personas(
    n: int,
    *,
    seed: int = 7,
    previous_version_share: float = 0.0,
    city: str | None = None,
    locales: list[str] | None = None,
    locale_share: float = 0.0,
    network: NetworkProfile | None = None,
) -> list[Persona]:
    rng = random.Random(seed)  # noqa: S311 - simulation, not security
    out: list[Persona] = []
    for i in range(n):
        c = city or _pick(rng, CITIES)
        loc = LOCALES[c]
        if locales and rng.random() < locale_share:
            loc = rng.choice(locales)
        out.append(
            Persona(
                idx=i,
                city=c,
                device=_pick(rng, DEVICES),
                locale=loc,
                network=network or GOOD,
                previous_version=rng.random() < previous_version_share,
            )
        )
    return out
