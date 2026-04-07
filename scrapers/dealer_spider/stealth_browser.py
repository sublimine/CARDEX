"""
Stealth Browser — Playwright with anti-detection for the Dealer Spider.

Features:
  - playwright-stealth patches (webdriver, chrome.runtime, plugins, etc.)
  - Network interceptor: aborts image/media/font/stylesheet/websocket
  - Realistic context: viewport, locale, timezone per country
  - Human-like cadence: scroll simulation before extraction
  - Context reuse: one browser context serves 5-10 dealers
  - Whale CAPTCHA solver: 2Captcha API for is_whale=true dealers

Used exclusively for Vector 3+4 (XHR interception, iframe extraction)
when curl_cffi vectors fail or when dealer requires JS rendering.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import random
from typing import Any

from playwright.async_api import (
    async_playwright,
    Browser,
    BrowserContext,
    Page,
    Route,
    Request,
)

log = logging.getLogger("spider.stealth_browser")

# ── Country-specific browser context profiles ─────────────────────────────────

_COUNTRY_CONTEXT = {
    "DE": {
        "locale": "de-DE",
        "timezone_id": "Europe/Berlin",
        "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    },
    "FR": {
        "locale": "fr-FR",
        "timezone_id": "Europe/Paris",
        "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
    },
    "ES": {
        "locale": "es-ES",
        "timezone_id": "Europe/Madrid",
        "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    },
    "NL": {
        "locale": "nl-NL",
        "timezone_id": "Europe/Amsterdam",
        "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    },
    "BE": {
        "locale": "nl-BE",
        "timezone_id": "Europe/Brussels",
        "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    },
    "CH": {
        "locale": "de-CH",
        "timezone_id": "Europe/Zurich",
        "user_agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_4) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
    },
}

# Realistic viewport sizes (common desktop resolutions)
_VIEWPORTS = [
    {"width": 1920, "height": 1080},
    {"width": 1366, "height": 768},
    {"width": 1440, "height": 900},
    {"width": 1536, "height": 864},
    {"width": 1680, "height": 1050},
]

# Resource types to block — saves bandwidth, especially on T2 residential
_BLOCKED_RESOURCE_TYPES = {"image", "media", "font", "stylesheet", "websocket", "other"}

# Proxy env vars
_PROXY_T1 = os.environ.get("PROXY_T1", "")
_PROXY_T2 = os.environ.get("PROXY_T2", "")

# 2Captcha for whale dealers
_CAPTCHA_API_KEY = os.environ.get("CAPTCHA_API_KEY", "")


# ── Network Interceptor ──────────────────────────────────────────────────────

async def _intercept_route(route: Route, request: Request) -> None:
    """
    Network interceptor — abort non-essential resources to minimize bandwidth.
    Only HTML, JSON, and JS pass through. Everything else is killed.
    """
    resource_type = request.resource_type
    if resource_type in _BLOCKED_RESOURCE_TYPES:
        await route.abort()
        return

    # Also block by URL pattern (tracking pixels, analytics, ads)
    url = request.url.lower()
    if any(tracker in url for tracker in (
        "google-analytics", "googletagmanager", "facebook.net",
        "doubleclick", "adservice", "hotjar", "crisp.chat",
        "intercom", "hubspot", "segment.io", "mixpanel",
    )):
        await route.abort()
        return

    await route.continue_()


# ── Human-like Scroll Simulation ─────────────────────────────────────────────

async def _simulate_human_scroll(page: Page) -> None:
    """Scroll down 2-3 times with random delays to mimic human reading."""
    scroll_count = random.randint(2, 3)
    for _ in range(scroll_count):
        scroll_amount = random.randint(300, 800)
        await page.evaluate(f"window.scrollBy(0, {scroll_amount})")
        await asyncio.sleep(random.uniform(0.4, 1.2))


# ── CAPTCHA Solver (Whales only) ─────────────────────────────────────────────

async def _solve_captcha_2captcha(page: Page, site_key: str, page_url: str) -> str | None:
    """
    Send CAPTCHA to 2Captcha API, wait for solution, inject it.
    Only called for whale dealers. Returns token or None.
    """
    if not _CAPTCHA_API_KEY:
        log.warning("stealth_browser: CAPTCHA_API_KEY not set, cannot solve")
        return None

    import httpx

    try:
        # Submit task
        async with httpx.AsyncClient(timeout=30) as client:
            submit = await client.post("https://2captcha.com/in.php", params={
                "key": _CAPTCHA_API_KEY,
                "method": "userrecaptcha",
                "googlekey": site_key,
                "pageurl": page_url,
                "json": 1,
            })
            result = submit.json()
            if result.get("status") != 1:
                log.warning("stealth_browser: 2captcha submit failed: %s", result)
                return None

            task_id = result["request"]

            # Poll for result (max 120s)
            for _ in range(24):
                await asyncio.sleep(5)
                poll = await client.get("https://2captcha.com/res.php", params={
                    "key": _CAPTCHA_API_KEY,
                    "action": "get",
                    "id": task_id,
                    "json": 1,
                })
                poll_result = poll.json()
                if poll_result.get("status") == 1:
                    return poll_result["request"]  # CAPTCHA token
                if poll_result.get("request") == "ERROR_CAPTCHA_UNSOLVABLE":
                    return None
    except Exception as exc:
        log.warning("stealth_browser: 2captcha error: %s", exc)

    return None


# ── Stealth Browser Client ───────────────────────────────────────────────────

class StealthBrowser:
    """
    Playwright browser with anti-detection for the Dealer Spider.

    Usage:
        async with StealthBrowser(country="ES", proxy_tier=1) as browser:
            html, json_payloads, iframes = await browser.extract(url)
    """

    def __init__(
        self,
        country: str = "DE",
        proxy_tier: int = 0,
        headless: bool = True,
    ):
        self._country = country
        self._proxy_tier = proxy_tier
        self._headless = headless
        self._playwright: Any = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None
        self._pages_used = 0
        self._max_pages_per_context = random.randint(5, 10)

    async def __aenter__(self) -> StealthBrowser:
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(
            headless=self._headless,
            args=[
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-blink-features=AutomationControlled",
            ],
        )
        await self._create_context()
        return self

    async def __aexit__(self, *exc) -> None:
        if self._context:
            await self._context.close()
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()

    async def _create_context(self) -> None:
        """Create a new browser context with stealth patches and country profile."""
        if self._context:
            await self._context.close()

        ctx_config = _COUNTRY_CONTEXT.get(self._country, _COUNTRY_CONTEXT["DE"])
        viewport = random.choice(_VIEWPORTS)

        # Proxy config
        proxy_config = None
        proxy_url = ""
        if self._proxy_tier == 1:
            proxy_url = _PROXY_T1
        elif self._proxy_tier >= 2:
            proxy_url = _PROXY_T2

        if proxy_url:
            if "@" in proxy_url:
                creds_part = proxy_url.split("@")[0].split("://")[-1]
                user, pwd = creds_part.split(":", 1)
                server = proxy_url.split("://")[0] + "://" + proxy_url.split("@")[-1]
                proxy_config = {"server": server, "username": user, "password": pwd}
            else:
                proxy_config = {"server": proxy_url}

        self._context = await self._browser.new_context(
            user_agent=ctx_config["user_agent"],
            viewport=viewport,
            locale=ctx_config["locale"],
            timezone_id=ctx_config["timezone_id"],
            java_script_enabled=True,
            proxy=proxy_config,
            color_scheme=random.choice(["light", "dark", "no-preference"]),
        )

        # Apply stealth patches
        try:
            from playwright_stealth import stealth_async
            await stealth_async(self._context)
        except ImportError:
            # Manual stealth patches if playwright-stealth not installed
            await self._context.add_init_script("""
                // Hide webdriver flag
                Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
                // Fake plugins
                Object.defineProperty(navigator, 'plugins', {
                    get: () => [1, 2, 3, 4, 5],
                });
                // Fake languages
                Object.defineProperty(navigator, 'languages', {
                    get: () => ['""" + ctx_config["locale"] + """', 'en-US', 'en'],
                });
                // Remove chrome.runtime in headless
                if (!window.chrome) { window.chrome = {}; }
                if (!window.chrome.runtime) { window.chrome.runtime = {}; }
                // Permissions
                const originalQuery = window.navigator.permissions.query;
                window.navigator.permissions.query = (parameters) =>
                    parameters.name === 'notifications'
                        ? Promise.resolve({ state: Notification.permission })
                        : originalQuery(parameters);
            """)

        # Network interceptor — block non-essential resources
        await self._context.route("**/*", _intercept_route)

        self._pages_used = 0

    async def _ensure_fresh_context(self) -> None:
        """Rotate context after N pages to avoid fingerprint accumulation."""
        self._pages_used += 1
        if self._pages_used >= self._max_pages_per_context:
            log.debug("stealth_browser: rotating context after %d pages", self._pages_used)
            await self._create_context()
            self._max_pages_per_context = random.randint(5, 10)

    async def extract(
        self,
        url: str,
        timeout: int = 30_000,
    ) -> tuple[str, list[dict], list[str]]:
        """
        Navigate to URL, intercept JSON responses, extract iframes.
        Returns (html, intercepted_json_list, iframe_srcs).
        """
        await self._ensure_fresh_context()

        page = await self._context.new_page()
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

            # Human-like scroll before extraction
            await _simulate_human_scroll(page)

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

    async def solve_challenge_if_whale(
        self,
        url: str,
        is_whale: bool,
        timeout: int = 30_000,
    ) -> tuple[str, list[dict], list[str]] | None:
        """
        Navigate to URL. If challenged and dealer is_whale, attempt CAPTCHA solve.
        Returns extraction result or None if solve fails.
        """
        await self._ensure_fresh_context()
        page = await self._context.new_page()
        intercepted: list[dict] = []

        async def on_response(response):
            try:
                ct = response.headers.get("content-type", "")
                if response.status == 200 and ("json" in ct):
                    body = await response.body()
                    if len(body) > 1024:
                        intercepted.append(json.loads(body))
            except Exception:
                pass

        page.on("response", on_response)

        try:
            await page.goto(url, wait_until="networkidle", timeout=timeout)
            html = await page.content()

            # Check if we hit a CAPTCHA challenge
            has_captcha = await page.query_selector(
                "[data-sitekey], .g-recaptcha, .h-captcha, #cf-turnstile"
            )

            if has_captcha and is_whale and _CAPTCHA_API_KEY:
                site_key = await has_captcha.get_attribute("data-sitekey")
                if site_key:
                    log.info("stealth_browser: whale CAPTCHA detected on %s, solving...", url)
                    token = await _solve_captcha_2captcha(page, site_key, url)
                    if token:
                        # Inject solution
                        await page.evaluate(f"""
                            document.getElementById('g-recaptcha-response').value = '{token}';
                            // Trigger callback if exists
                            if (typeof ___grecaptcha_cfg !== 'undefined') {{
                                Object.keys(___grecaptcha_cfg.clients).forEach(key => {{
                                    const client = ___grecaptcha_cfg.clients[key];
                                    if (client && client.M && client.M.callback) {{
                                        client.M.callback('{token}');
                                    }}
                                }});
                            }}
                        """)
                        await asyncio.sleep(3)
                        # Re-navigate after solve
                        await page.goto(url, wait_until="networkidle", timeout=timeout)
                        html = await page.content()
                    else:
                        log.warning("stealth_browser: CAPTCHA solve failed for %s", url)
                        return None
            elif has_captcha:
                # Not a whale — don't solve
                return None

            await _simulate_human_scroll(page)

            iframes = await page.query_selector_all("iframe[src]")
            iframe_srcs = []
            for iframe in iframes:
                src = await iframe.get_attribute("src")
                if src:
                    iframe_srcs.append(src)

            return html, intercepted, iframe_srcs
        finally:
            await page.close()
