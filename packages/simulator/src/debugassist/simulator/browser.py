"""Playwright fleet: one browser, a fresh context per simulated rider."""

from __future__ import annotations

import asyncio
import base64
import json
import random
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any, cast

from playwright.async_api import Browser, BrowserContext, Page, Playwright, Route, async_playwright

from debugassist.simulator.personas import CUSTOM_DEVICES, Persona


@dataclass
class FleetConfig:
    app_url: str = "http://localhost:8080"
    previous_app_url: str = "http://localhost:8081"
    headless: bool = True


class Fleet:
    def __init__(self, cfg: FleetConfig | None = None) -> None:
        self.cfg = cfg or FleetConfig()
        self._pw: Playwright | None = None
        self._browser: Browser | None = None

    async def __aenter__(self) -> Fleet:
        self._pw = await async_playwright().start()
        self._browser = await self._pw.chromium.launch(headless=self.cfg.headless)
        return self

    async def __aexit__(self, *exc: object) -> None:
        if self._browser:
            await self._browser.close()
        if self._pw:
            await self._pw.stop()

    def url(self, p: Persona) -> str:
        return self.cfg.previous_app_url if p.previous_version else self.cfg.app_url

    def _descriptor(self, device: str) -> dict[str, Any]:
        assert self._pw is not None
        if device in CUSTOM_DEVICES:
            return dict(CUSTOM_DEVICES[device])
        d = dict(cast(dict[str, Any], self._pw.devices[device]))  # pyright: ignore[reportUnknownMemberType]
        d.pop("default_browser_type", None)
        return d

    @asynccontextmanager
    async def rider(self, p: Persona, *, clock: bool = False) -> AsyncGenerator[Page]:
        assert self._browser is not None
        ctx: BrowserContext = await self._browser.new_context(**self._descriptor(p.device), locale=p.locale)
        try:
            page = await ctx.new_page()
            if clock:
                await page.clock.install()
            if p.network.latency_ms or p.network.download_kbps:
                cdp = await ctx.new_cdp_session(page)
                send = cast(Any, cdp.send)  # pyright: ignore[reportUnknownMemberType]
                await send("Network.enable")
                await send(
                    "Network.emulateNetworkConditions",
                    {
                        "offline": False,
                        "latency": p.network.latency_ms,
                        "downloadThroughput": p.network.download_kbps * 1024 / 8
                        if p.network.download_kbps
                        else -1,
                        "uploadThroughput": p.network.upload_kbps * 1024 / 8 if p.network.upload_kbps else -1,
                    },
                )
            if p.network.loss_pct > 0:
                rng = random.Random(p.idx)  # noqa: S311 - simulation
                lo, hi = p.network.retransmit_ms

                async def lossy(route: Route) -> None:
                    # TCP retransmission after a lost segment: the request stalls, then completes.
                    if rng.random() < p.network.loss_pct:
                        await asyncio.sleep(rng.uniform(lo, hi) / 1000)
                    await route.continue_()

                await page.route("**/graphql", lossy)
            yield page
        finally:
            await ctx.close()


# ---- rider actions --------------------------------------------------------------------------


async def crashed(page: Page) -> bool:
    """The app's crash screen, or the router's error page (a render error inside a route)."""
    if await page.get_by_role("alert").count() > 0:
        return True
    return await page.get_by_text("Unexpected Application Error").count() > 0


async def open_app(page: Page, url: str, path: str = "/") -> bool:
    """Open the app; True if the home screen rendered."""
    await page.goto(url + path, wait_until="domcontentloaded")
    try:
        await page.get_by_role("heading", name="Where to?").wait_for(timeout=8_000)
        return True
    except Exception:
        return False


async def set_city(page: Page, city: str) -> None:
    await page.get_by_label("City").select_option(city)
    await page.wait_for_timeout(400)


async def book(
    page: Page, *, city: str, pickup: str | None = None, dropoff: str | None = None, timeout_ms: int = 45_000
) -> str | None:
    """Book a ride from the home screen; returns the ride id or None on failure."""
    await set_city(page, city)
    if pickup:
        await page.get_by_test_id("pickup").select_option(label=pickup)
    if dropoff:
        await page.get_by_test_id("dropoff").select_option(label=dropoff)
    elif pickup:
        options = await page.get_by_test_id("dropoff").locator("option").all_inner_texts()
        await page.get_by_test_id("dropoff").select_option(label=next(o for o in options if o != pickup))
    await page.get_by_role("button", name="See prices").click()
    try:
        await page.get_by_test_id("fare").wait_for(timeout=15_000)
    except Exception:
        return None
    await page.get_by_role("button", name="Request MiniRide").click()
    try:
        await page.wait_for_url("**/ride/**", timeout=timeout_ms)
    except Exception:
        return None
    return page.url.rsplit("/ride/", 1)[-1]


async def set_hidden(page: Page, hidden: bool) -> None:
    """Background/foreground the app via the Page Visibility API (as a WebView host would)."""
    await page.evaluate(
        """(hidden) => {
          const state = hidden ? "hidden" : "visible";
          Object.defineProperty(document, "visibilityState", { get: () => state, configurable: true });
          Object.defineProperty(document, "hidden", { get: () => hidden, configurable: true });
          document.dispatchEvent(new Event("visibilitychange"));
        }""",
        hidden,
    )


def push_payload(deep_link: str, title: str = "Your driver is arriving") -> str:
    raw = json.dumps({"deepLink": deep_link, "title": title}).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


async def report_bug(page: Page, text: str, attachments: list[tuple[str, bytes]] | None = None) -> str | None:
    await page.get_by_test_id("bugdrop-button").click()
    await page.get_by_test_id("bugdrop-description").fill(text)
    if attachments:
        await page.get_by_test_id("bugdrop-attach").set_input_files(
            [{"name": n, "mimeType": "image/png", "buffer": b} for n, b in attachments]
        )
    await page.get_by_test_id("bugdrop-submit").click()
    try:
        done = page.get_by_test_id("bugdrop-done")
        await done.wait_for(timeout=30_000)
        text_out = await done.text_content() or ""
        return next((w.rstrip(".") for w in text_out.split() if w.startswith("BD-")), None)
    except Exception:
        return None


async def gather_limited(n: int, coros: list[Any]) -> list[Any]:
    sem = asyncio.Semaphore(n)

    async def run(c: Any) -> Any:
        async with sem:
            return await c

    return await asyncio.gather(*(run(c) for c in coros))
