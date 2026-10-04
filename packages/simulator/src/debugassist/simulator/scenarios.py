"""Scenario drivers: realistic rider traffic that exercises (and, when injected, triggers) catalog bugs.

Each driver returns a small summary of what the simulated riders experienced. Drivers never read
ground truth; they only act like riders (and, for GPS loss, like the driver app).
"""

from __future__ import annotations

import asyncio
import random
from collections import Counter
from collections.abc import Awaitable, Callable
from typing import Any

import httpx

from debugassist.simulator.assets import battery_panel_png
from debugassist.simulator.browser import (
    Fleet,
    book,
    crashed,
    gather_limited,
    open_app,
    push_payload,
    report_bug,
    set_hidden,
)
from debugassist.simulator.personas import WEAK, NetworkProfile, Persona, personas

Log = Callable[[str], None]
DISPATCH = "http://localhost:8001"


async def normal_traffic(fleet: Fleet, params: dict[str, Any], log: Log) -> dict[str, Any]:
    """Baseline sessions: browse, quote, sometimes book."""
    n = int(params.get("sessions", 20))
    riders = personas(
        n,
        seed=int(params.get("seed", 1)),
        previous_version_share=float(params.get("previous_version_share", 0)),
    )
    rng = random.Random(int(params.get("seed", 1)))  # noqa: S311
    outcomes: Counter[str] = Counter()

    async def one(p: Persona) -> None:
        async with fleet.rider(p) as page:
            if not await open_app(page, fleet.url(p)):
                outcomes["no_home"] += 1
                return
            if rng.random() < float(params.get("book_share", 0.5)):
                outcomes["booked" if await book(page, city=p.city) else "booking_failed"] += 1
                await page.wait_for_timeout(3_000)
            else:
                outcomes["browsed"] += 1
                await page.wait_for_timeout(1_500)

    await gather_limited(int(params.get("concurrency", 6)), [one(p) for p in riders])
    return {"sessions": n, **outcomes}


async def battery_drain(fleet: Fleet, params: dict[str, Any], log: Log) -> dict[str, Any]:
    """Riders background the app while waiting for the driver; one of them reports the heat."""
    hidden_real_s = float(params.get("hidden_real_s", 75))
    hidden_total_min = float(params.get("hidden_simulated_min", 17))
    others = int(params.get("background_sessions", 4))
    riders = personas(others + 1, seed=11, city="sf")
    reporter, rest = riders[0], riders[1:]
    result: dict[str, Any] = {}

    async def background(p: Persona) -> None:
        async with fleet.rider(p) as page:
            if await open_app(page, fleet.url(p)) and await book(page, city=p.city):
                await page.wait_for_timeout(5_000)
                await set_hidden(page, True)
                await page.wait_for_timeout(int(hidden_real_s * 1000))

    async def report() -> None:
        async with fleet.rider(reporter, clock=True) as page:
            if not await open_app(page, fleet.url(reporter)):
                result["reporter"] = "app did not open"
                return
            ride = await book(page, city=reporter.city)
            result["ride"] = ride
            await page.wait_for_timeout(6_000)
            log(f"reporter backgrounded the app (ride {ride}); {hidden_real_s:.0f}s real time …")
            await set_hidden(page, True)
            await page.wait_for_timeout(int(hidden_real_s * 1000))
            remaining_s = max(0.0, hidden_total_min * 60 - hidden_real_s)
            # Close the lid: jump the page clock so the background period lasts ~17 minutes.
            await page.clock.fast_forward(int(remaining_s * 1000))
            await page.wait_for_timeout(2_000)
            await set_hidden(page, False)
            await page.wait_for_timeout(3_000)
            png = battery_panel_png(
                int(params.get("battery_percent", 29)), background_min=round(hidden_total_min)
            )
            result["report"] = await report_bug(page, str(params["report_text"]), [("battery.png", png)])

    await asyncio.gather(report(), *(background(p) for p in rest))
    return result


async def push_tap_fleet(fleet: Fleet, params: dict[str, Any], log: Log) -> dict[str, Any]:
    """Riders open the app from a push notification (tap → cold start with the payload) or normally."""
    n = int(params.get("sessions", 200))
    riders = personas(
        n,
        seed=int(params.get("seed", 2)),
        previous_version_share=float(params.get("previous_version_share", 0.25)),
    )
    rng = random.Random(int(params.get("seed", 2)))  # noqa: S311
    share = float(params.get("fast_tap_share", 0.6))
    outcomes: Counter[str] = Counter()
    links = ["/ride/{id}", "/notifications"]

    async def one(p: Persona) -> None:
        async with fleet.rider(p) as page:
            if rng.random() < share:
                link = rng.choice(links).format(id=f"{rng.getrandbits(64):016x}")
                await page.goto(f"{fleet.url(p)}/?push={push_payload(link)}", wait_until="domcontentloaded")
                kind = "push"
            else:
                await page.goto(fleet.url(p), wait_until="domcontentloaded")
                kind = "normal"
            await page.wait_for_timeout(2_500)
            version = "prev" if p.previous_version else "current"
            outcomes[f"{kind}:{version}:{'crash' if await crashed(page) else 'ok'}"] += 1

    done = 0
    batch = int(params.get("concurrency", 8))
    for i in range(0, n, 40):
        await gather_limited(batch, [one(p) for p in riders[i : i + 40]])
        done = min(n, i + 40)
        log(f"{done}/{n} sessions")
    return {"sessions": n, **dict(sorted(outcomes.items()))}


async def weak_network_booking(fleet: Fleet, params: dict[str, Any], log: Log) -> dict[str, Any]:
    """Some riders are on a congested airport network; one of them complains."""
    profile = NetworkProfile(
        "airport",
        int(params.get("latency_ms", WEAK.latency_ms)),
        int(params.get("download_kbps", WEAK.download_kbps)),
        int(params.get("upload_kbps", WEAK.upload_kbps)),
        loss_pct=float(params.get("loss_pct", WEAK.loss_pct)),
    )
    weak = personas(
        int(params.get("weak_sessions", 4)), seed=31, city=str(params.get("city", "sf")), network=profile
    )
    normal = personas(int(params.get("normal_sessions", 6)), seed=32)
    out: dict[str, Any] = {"weak": [], "normal": Counter()}
    reported = asyncio.Lock()

    async def weak_one(p: Persona) -> None:
        async with fleet.rider(p) as page:
            if not await open_app(page, fleet.url(p)):
                out["weak"].append("no_home")
                return
            ride = await book(
                page, city=p.city, pickup=str(params.get("pickup", "SFO Airport")), timeout_ms=90_000
            )
            # The rider notices when two "Driver assigned" notifications arrive for one booking.
            await page.wait_for_timeout(12_000)
            badge = page.get_by_test_id("unread-count")
            unread = int(await badge.text_content() or 0) if await badge.count() else 0
            out["weak"].append({"ride": ride, "driver_notifications": unread})
            if unread >= 2 and not reported.locked():
                async with reported:
                    out["report"] = await report_bug(page, str(params["report_text"]))

    async def normal_one(p: Persona) -> None:
        async with fleet.rider(p) as page:
            ok = await open_app(page, fleet.url(p)) and await book(page, city=p.city)
            out["normal"]["booked" if ok else "failed"] += 1

    await asyncio.gather(*(weak_one(p) for p in weak), *(normal_one(p) for p in normal))
    out["normal"] = dict(out["normal"])
    return out


async def gps_loss(fleet: Fleet, params: dict[str, Any], log: Log) -> dict[str, Any]:
    """Riders wait for drivers; some driver apps lose their GPS fix (null coordinates)."""
    riders = personas(int(params.get("sessions", 6)), seed=41)
    rng = random.Random(41)  # noqa: S311
    share = float(params.get("gps_lost_share", 0.5))
    out: dict[str, Any] = {"rides": []}

    async def one(p: Persona, reporter: bool) -> None:
        async with fleet.rider(p) as page, httpx.AsyncClient(timeout=10) as http:
            if not (await open_app(page, fleet.url(p)) and (ride := await book(page, city=p.city))):
                out["rides"].append("booking_failed")
                return
            ride_info: dict[str, Any] = (await http.get(f"{DISPATCH}/rides/{ride}")).json()
            driver: dict[str, Any] = ride_info.get("driver") or {}
            lost = rng.random() < share or reporter
            if driver.get("id"):
                body = (
                    {"lat": None, "lng": None}
                    if lost
                    else {"lat": driver.get("lat"), "lng": driver.get("lng")}
                )
                await http.put(f"{DISPATCH}/internal/drivers/{driver['id']}/location", json=body)
            await page.wait_for_timeout(20_000)
            eta = await page.get_by_test_id("eta").text_content()
            out["rides"].append({"ride": ride, "gps_lost": lost, "eta_shown": eta})
            if reporter:
                out["report"] = await report_bug(page, str(params["report_text"]))

    await asyncio.gather(*(one(p, i == 0) for i, p in enumerate(riders)))
    return out


async def fare_quotes(fleet: Fleet, params: dict[str, Any], log: Log) -> dict[str, Any]:
    """Riders check prices (some sessions are in the surge-pricing rollout)."""
    riders = personas(int(params.get("sessions", 40)), seed=51)
    outcomes: Counter[str] = Counter()

    async def one(p: Persona) -> None:
        async with fleet.rider(p) as page:
            if not await open_app(page, fleet.url(p)):
                outcomes["no_home"] += 1
                return
            await page.get_by_label("City").select_option(p.city)
            await page.wait_for_timeout(400)
            await page.get_by_role("button", name="See prices").click()
            try:
                await page.get_by_test_id("fare").wait_for(timeout=8_000)
                outcomes["quoted"] += 1
            except Exception:
                outcomes["no_price"] += 1

    await gather_limited(int(params.get("concurrency", 6)), [one(p) for p in riders])
    return dict(outcomes)


async def _book_and_report(
    fleet: Fleet, params: dict[str, Any], seed: int, timeout_ms: int
) -> dict[str, Any]:
    riders = personas(int(params.get("sessions", 6)), seed=seed)
    outcomes: Counter[str] = Counter()
    out: dict[str, Any] = {}

    async def one(p: Persona, reporter: bool) -> None:
        async with fleet.rider(p) as page:
            if not await open_app(page, fleet.url(p)):
                outcomes["no_home"] += 1
                return
            ok = await book(page, city=p.city, timeout_ms=timeout_ms)
            outcomes["booked" if ok else "failed"] += 1
            if reporter and not ok:
                out["report"] = await report_bug(page, str(params["report_text"]))

    await asyncio.gather(*(one(p, i == 0) for i, p in enumerate(riders)))
    return {**out, **outcomes}


async def degraded_backend(fleet: Fleet, params: dict[str, Any], log: Log) -> dict[str, Any]:
    return await _book_and_report(fleet, params, seed=61, timeout_ms=60_000)


async def booking_failures(fleet: Fleet, params: dict[str, Any], log: Log) -> dict[str, Any]:
    return await _book_and_report(fleet, params, seed=71, timeout_ms=30_000)


async def locale_mix(fleet: Fleet, params: dict[str, Any], log: Log) -> dict[str, Any]:
    """Riders with a mix of device locales, including bare language tags ("ar", "he")."""
    riders = personas(
        int(params.get("sessions", 30)),
        seed=81,
        locales=[str(x) for x in params.get("bare_locales", ["ar", "he"])],
        locale_share=float(params.get("bare_locale_share", 0.2)),
    )
    outcomes: Counter[str] = Counter()
    out: dict[str, Any] = {}
    reported = False

    async def one(p: Persona) -> None:
        nonlocal reported
        async with fleet.rider(p) as page:
            ok = await open_app(page, fleet.url(p))
            outcomes[f"{p.locale}:{'ok' if ok else 'blank'}"] += 1
            if not ok and not reported:
                reported = True
                out["report"] = await report_bug(page, str(params["report_text"]))

    await gather_limited(int(params.get("concurrency", 6)), [one(p) for p in riders])
    return {**out, "outcomes": dict(sorted(outcomes.items()))}


SCENARIOS: dict[str, Callable[[Fleet, dict[str, Any], Log], Awaitable[dict[str, Any]]]] = {
    "normal_traffic": normal_traffic,
    "battery_drain": battery_drain,
    "push_tap_fleet": push_tap_fleet,
    "weak_network_booking": weak_network_booking,
    "gps_loss": gps_loss,
    "fare_quotes": fare_quotes,
    "degraded_backend": degraded_backend,
    "booking_failures": booking_failures,
    "locale_mix": locale_mix,
}


async def run_scenario(
    name: str, params: dict[str, Any], *, log: Log = print, headless: bool = True
) -> dict[str, Any]:
    from debugassist.simulator.browser import FleetConfig

    async with Fleet(FleetConfig(headless=headless)) as fleet:
        return await SCENARIOS[name](fleet, params, log)
