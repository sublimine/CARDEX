"""
wallapop.es — C2C marketplace ES.

React SPA. Playwright with stealth — mandatory per §25.
Uses offset-based pagination via API that is embedded in the SPA.
Listing URL pattern: https://es.wallapop.com/item/{slug}

Stealth approach: navigator.webdriver removed, chrome runtime injected,
headless=False not required since we use CDP stealth overrides.
"""
from __future__ import annotations

import asyncio
import logging
import re

from playwright.async_api import async_playwright, Page

from scrapers.common.indexer import run_portal

log = logging.getLogger(__name__)

_SOURCE = "wallapop"
_COUNTRY = "ES"
_DOMAIN = "es.wallapop.com"
_LISTING_RE = re.compile(
    r'https://es\.wallapop\.com/item/[a-z0-9_-]+-\d+',
    re.IGNORECASE,
)
_SEARCH_URL = (
    "https://es.wallapop.com/app/search"
    "?category_ids=100"
    "&filters_source=search_box"
    "&order_by=newest"
)
_ITEMS_PER_PAGE = 40
_MAX_PAGES = 150
_SLEEP = 2.0

_STEALTH_JS = """
Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});
Object.defineProperty(navigator, 'languages', {get: () => ['es-ES', 'es', 'en']});
window.chrome = {runtime: {}, loadTimes: function(){}, csi: function(){}, app: {}};
"""


async def _collect() -> list[str]:
    collected: set[str] = set()

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-dev-shm-usage",
            ],
        )
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            ),
            locale="es-ES",
            viewport={"width": 1280, "height": 900},
        )
        await context.add_init_script(_STEALTH_JS)
        page = await context.new_page()

        try:
            for pg_num in range(_MAX_PAGES):
                start = pg_num * _ITEMS_PER_PAGE
                url = f"{_SEARCH_URL}&start={start}"
                await page.goto(url, wait_until="domcontentloaded", timeout=30_000)
                await asyncio.sleep(_SLEEP)

                content = await page.content()
                page_urls = set(_LISTING_RE.findall(content))
                if not page_urls:
                    break
                prev = len(collected)
                collected.update(page_urls)
                if len(collected) == prev:
                    break
                log.debug("wallapop page=%d found=%d total=%d", pg_num + 1, len(page_urls), len(collected))
        finally:
            await browser.close()

    return list(collected)


async def run(): await run_portal(source=_SOURCE, country=_COUNTRY, domain=_DOMAIN, fetch_all_urls=_collect)
if __name__ == "__main__": asyncio.run(run())
