"""
Playwright client for JS-heavy listing pages.
Honest CardexBot UA — CARDEX is an indexer that drives traffic back to portals.
"""
from __future__ import annotations

import asyncio
import random
from typing import Any, Optional

import structlog
from playwright.async_api import async_playwright, Browser, BrowserContext, Page

from .proxy_manager import ProxyManager

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
        proxy_manager: Optional[ProxyManager] = None,
        country: Optional[str] = None,
    ) -> None:
        self.headless = headless
        self.proxy_manager = proxy_manager
        self.country = country
        self._playwright: Any = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None

    async def __aenter__(self) -> "PlaywrightClient":
        self._playwright = await async_playwright().start()

        proxy_url = None
        if self.proxy_manager:
            proxy_url = await self.proxy_manager.get(country=self.country)

        proxy_config = None
        if proxy_url and "@" in proxy_url:
            creds = proxy_url.split("@")[0].split("://")[-1]
            u, p = creds.split(":", 1)
            server = proxy_url.split("://")[0] + "://" + proxy_url.split("@")[-1]
            proxy_config = {"server": server, "username": u, "password": p}
        elif proxy_url:
            proxy_config = {"server": proxy_url}

        self._browser = await self._playwright.chromium.launch(
            headless=self.headless,
            args=["--no-sandbox", "--disable-dev-shm-usage"],
        )
        self._context = await self._browser.new_context(
            user_agent=CARDEX_UA,
            viewport={"width": 1280, "height": 800},
            locale="en-US",
            java_script_enabled=True,
            proxy=proxy_config,
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

    async def get_cookies(self) -> list[dict[str, Any]]:
        """Return all cookies from the current browser context."""
        if not self._context:
            return []
        return await self._context.cookies()

    async def get_cookie(self, name: str) -> dict[str, Any] | None:
        """Return a specific cookie by name, or None."""
        cookies = await self.get_cookies()
        return next((c for c in cookies if c["name"] == name), None)
