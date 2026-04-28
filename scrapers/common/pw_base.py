"""
Playwright scraper base — stealth + network request interception.

SPAs load listing data via XHR/fetch. Instead of waiting for full HTML render,
we intercept network responses matching the portal's API pattern and extract
listing URLs directly from the JSON. This is 3-5x faster than DOM scraping
and works even when the rendered HTML contains no useful hrefs.

JA3 invariant: Playwright uses its own TLS fingerprint consistently.
Stealth: navigator.webdriver removed, chrome runtime injected.
§25: This is browser-native request observation, not a frontal API attack.
"""
from __future__ import annotations

import asyncio
import logging
import re
import time
from typing import Callable

from playwright.async_api import async_playwright, Browser, Page, Response

log = logging.getLogger(__name__)

_STEALTH_JS = """
Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
Object.defineProperty(navigator, 'plugins', {get: () => [1,2,3,4,5]});
Object.defineProperty(navigator, 'languages', {get: () => ['de-DE','fr-FR','en-US','en']});
window.chrome = {runtime:{}, loadTimes:()=>{}, csi:()=>{}, app:{}};
Object.defineProperty(navigator, 'platform', {get: () => 'Win32'});
"""

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


async def make_stealth_browser():
    """Launch Playwright Chromium with stealth settings."""
    pw = await async_playwright().start()
    browser = await pw.chromium.launch(
        headless=True,
        args=[
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--disable-web-security",
            "--disable-features=IsolateOrigins,site-per-process",
        ],
    )
    return pw, browser


async def apply_stealth(page) -> None:
    """Apply playwright-stealth if available, fall back to manual JS patches."""
    try:
        from playwright_stealth import stealth_async
        await stealth_async(page)
    except ImportError:
        await page.add_init_script(_STEALTH_JS)


async def make_stealth_page(browser: Browser, locale: str = "de-DE") -> Page:
    context = await browser.new_context(
        user_agent=_UA,
        locale=locale,
        viewport={"width": 1280, "height": 900},
        extra_http_headers={"Accept-Language": f"{locale},{locale[:2]};q=0.9,en;q=0.8"},
    )
    await context.add_init_script(_STEALTH_JS)
    page = await context.new_page()
    await apply_stealth(page)
    return page


async def intercept_paginate(
    *,
    source: str,
    country: str,
    search_url_fn: Callable[[int], str],
    api_pattern: re.Pattern,
    extract_urls_fn: Callable[[str, str], list[str]],
    max_pages: int = 100,
    page_wait_ms: int = 3000,
    locale: str = "de-DE",
) -> list[str]:
    """
    Paginate a SPA portal by intercepting XHR responses matching api_pattern.

    For each page:
    1. Navigate to search_url_fn(page_num)
    2. Wait for an XHR response matching api_pattern
    3. Pass the response body to extract_urls_fn
    4. If no new URLs after 2 consecutive pages: stop
    """
    collected: set[str] = set()
    pw, browser = await make_stealth_browser()

    try:
        page = await make_stealth_page(browser, locale)
        captured: list[str] = []

        async def on_response(response: Response):
            try:
                if api_pattern.search(response.url):
                    body = await response.text()
                    urls = extract_urls_fn(body, response.url)
                    captured.extend(urls)
            except Exception:
                pass

        page.on("response", on_response)

        for pg_num in range(1, max_pages + 1):
            captured.clear()
            url = search_url_fn(pg_num)
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=30_000)
                await page.wait_for_timeout(page_wait_ms)
            except Exception as exc:
                log.debug("%s page=%d nav error: %s", source, pg_num, exc)
                break

            page_urls = set(captured)
            if not page_urls:
                # Fallback: try extracting from rendered DOM
                dom = await page.content()
                dom_urls = extract_urls_fn(dom, url)
                page_urls = set(dom_urls)

            if not page_urls:
                log.debug("%s/%s page=%d: 0 URLs — stopping", source, country, pg_num)
                break

            prev = len(collected)
            collected.update(page_urls)
            log.debug("%s/%s page=%d: +%d urls (total=%d)", source, country, pg_num, len(page_urls), len(collected))

            if len(collected) == prev:
                break

        log.info("%s/%s intercepted total_urls=%d", source, country, len(collected))
    finally:
        await browser.close()
        await pw.stop()

    return list(collected)


async def dom_paginate(
    *,
    source: str,
    country: str,
    search_url_fn: Callable[[int], str],
    extract_urls_fn: Callable[[str], list[str]],
    max_pages: int = 100,
    page_wait_ms: int = 3000,
    locale: str = "de-DE",
) -> list[str]:
    """
    Paginate a SPA by extracting URLs from rendered DOM content.
    Slower than intercept_paginate but works when XHR pattern is unknown.
    """
    collected: set[str] = set()
    pw, browser = await make_stealth_browser()

    try:
        page = await make_stealth_page(browser, locale)

        for pg_num in range(1, max_pages + 1):
            url = search_url_fn(pg_num)
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=30_000)
                await page.wait_for_timeout(page_wait_ms)
            except Exception as exc:
                log.debug("%s page=%d nav error: %s", source, pg_num, exc)
                break

            dom = await page.content()
            page_urls = set(extract_urls_fn(dom))

            if not page_urls:
                break
            prev = len(collected)
            collected.update(page_urls)
            log.debug("%s/%s page=%d: +%d (total=%d)", source, country, pg_num, len(page_urls), len(collected))
            if len(collected) == prev:
                break

        log.info("%s/%s dom total_urls=%d", source, country, len(collected))
    finally:
        await browser.close()
        await pw.stop()

    return list(collected)
