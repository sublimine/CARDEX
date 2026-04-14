"""
Playwright client for JS-heavy listing pages.
Honest CardexBot UA — CARDEX is an indexer that drives traffic back to portals.
"""
from __future__ import annotations

import asyncio
import json
import random
from typing import Any, Optional

import structlog
from playwright.async_api import async_playwright, Browser, BrowserContext, Page

log = structlog.get_logger()

CARDEX_UA = (
    "CardexBot/1.0 (+https://cardex.eu/bot; indexing@cardex.eu) "
    "Playwright/1.44 Chromium"
)


class PlaywrightClient:
    """
    Async Playwright wrapper for JS-rendered listing pages.
    Identifies honestly as CardexBot. Use only for portals that
    require JS rendering and don't expose sitemaps/JSON APIs.
    """

    def __init__(
        self,
        headless: bool = True,
        country: Optional[str] = None,
    ) -> None:
        self.headless = headless
        self.country = country
        self._playwright: Any = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None

    async def __aenter__(self) -> "PlaywrightClient":
        self._playwright = await async_playwright().start()

        self._browser = await self._playwright.chromium.launch(
            headless=self.headless,
            args=["--no-sandbox", "--disable-dev-shm-usage"],
        )
        self._context = await self._browser.new_context(
            user_agent=CARDEX_UA,
            viewport={"width": 1280, "height": 800},
            locale="en-US",
            java_script_enabled=True,
        )
        # Block images, fonts, media to reduce bandwidth
        await self._context.route(
            "**/*.{png,jpg,jpeg,gif,webp,svg,ico,woff,woff2,ttf,mp4,webm}",
            lambda route: route.abort()
        )
        return self

    async def __aexit__(self, *_: Any) -> None:
        if self._context:
            await self._context.close()
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()

    async def new_page(self) -> Page:
        assert self._context is not None
        return await self._context.new_page()

    async def get_page_content(
        self,
        url: str,
        wait_for: str | None = None,
        timeout: int = 30_000,
    ) -> str:
        """Navigate to URL, optionally wait for a selector, return HTML."""
        page = await self.new_page()
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=timeout)
            if wait_for:
                try:
                    await page.wait_for_selector(wait_for, timeout=8_000)
                except Exception:
                    pass
            await asyncio.sleep(random.uniform(0.5, 1.5))
            return await page.content()
        finally:
            await page.close()

    async def get_page_with_interception(
        self,
        url: str,
        wait_for: str | None = None,
        timeout: int = 30_000,
    ) -> tuple[str, list[dict], list[str]]:
        """Navigate, intercept JSON responses, return (html, intercepted_json_list, iframe_srcs)."""
        page = await self.new_page()
        intercepted: list[dict] = []

        async def on_response(response):
            try:
                ct = response.headers.get("content-type", "")
                if response.status == 200 and ("json" in ct or "javascript" in ct):
                    body = await response.body()
                    if len(body) > 1024:
                        data = json.loads(body)
                        intercepted.append(data)
            except Exception:
                pass

        page.on("response", on_response)

        try:
            await page.goto(url, wait_until="networkidle", timeout=timeout)
            if wait_for:
                try:
                    await page.wait_for_selector(wait_for, timeout=5000)
                except Exception:
                    pass
            await asyncio.sleep(1.0)
            html = await page.content()

            # Extract iframe sources
            iframes = await page.query_selector_all("iframe[src]")
            iframe_srcs: list[str] = []
            for iframe in iframes:
                src = await iframe.get_attribute("src")
                if src:
                    iframe_srcs.append(src)

            return html, intercepted, iframe_srcs
        finally:
            await page.close()

    async def get_cookies(self) -> list[dict[str, Any]]:
        """Return all cookies from the current browser context."""
        if not self._context:
            return []
        return await self._context.cookies()

    async def get_cookie(self, name: str) -> dict[str, Any] | None:
        """Return a specific cookie by name, or None."""
        cookies = await self.get_cookies()
        return next((c for c in cookies if c["name"] == name), None)
