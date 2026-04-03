"""
Playwright client for JS-heavy pages (SPAs, lazy-loaded listings).
- Honest User-Agent (same CardexBot UA)
- No TLS spoofing, no stealth plugins, no fingerprint manipulation
- Conservative viewport, no JS injection to defeat bot detection
"""
from __future__ import annotations

import asyncio
import random
from typing import Any

import structlog
from playwright.async_api import async_playwright, Browser, BrowserContext, Page

log = structlog.get_logger()

CARDEX_UA = (
    "CardexBot/1.0 (+https://cardex.eu/bot; scraping@cardex.eu) "
    "Playwright/1.44 Chromium"
)


class PlaywrightClient:
    """
    Async Playwright wrapper — one browser instance per scraper run.
    Use as async context manager.
    """

    def __init__(self, headless: bool = True) -> None:
        self.headless = headless
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

    async def get_page_content(self, url: str, wait_for: str | None = None) -> str:
        """Navigate to URL, optionally wait for a selector, return HTML."""
        page = await self.new_page()
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=30_000)
            if wait_for:
                await page.wait_for_selector(wait_for, timeout=10_000)
            # Small random pause to avoid mechanical timing patterns
            await asyncio.sleep(random.uniform(0.5, 1.5))
            return await page.content()
        finally:
            await page.close()
