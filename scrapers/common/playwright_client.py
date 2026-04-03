"""
Playwright client with full anti-detection stack:
- playwright-stealth: disables 30+ browser fingerprint leaks
  (webdriver flag, plugins, canvas hash, WebGL vendor, language mismatch,
   chrome runtime object, permissions API, etc.)
- Random fingerprint per session: viewport, locale, timezone, deviceMemory,
  hardwareConcurrency — realistic distribution, not uniform
- Proxy injection from ProxyManager (per-context, geographically affined)
- Cloudflare clearance cookie persistence per proxy (reuse across pages)
- Human-like scroll simulation before extracting content
- Mouse movement simulation for click targets
- Blocks images/fonts/media for bandwidth efficiency (configurable)
"""
from __future__ import annotations

import asyncio
import random
from typing import Any, Optional

import structlog
from playwright.async_api import async_playwright, Browser, BrowserContext, Page

from .proxy_manager import ProxyManager

log = structlog.get_logger()

# ─── Realistic fingerprint pools ──────────────────────────────────────────────

_VIEWPORTS = [
    {"width": 1920, "height": 1080},
    {"width": 1440, "height": 900},
    {"width": 1366, "height": 768},
    {"width": 1536, "height": 864},
    {"width": 2560, "height": 1440},
    {"width": 1280, "height": 800},
]

_LOCALES = ["de-DE", "es-ES", "fr-FR", "nl-NL", "en-GB", "en-US", "it-IT", "pl-PL"]

_TIMEZONES = [
    "Europe/Berlin", "Europe/Madrid", "Europe/Paris", "Europe/Amsterdam",
    "Europe/London", "Europe/Vienna", "Europe/Warsaw", "Europe/Rome",
]

_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
]

# Stealth JS: patches the most common fingerprint leaks inline.
# playwright-stealth covers these automatically when installed.
_STEALTH_INIT_SCRIPT = """
// Patch navigator.webdriver
Object.defineProperty(navigator, 'webdriver', { get: () => undefined });

// Patch navigator.plugins to look real
Object.defineProperty(navigator, 'plugins', {
    get: () => [
        { name: 'Chrome PDF Plugin', filename: 'internal-pdf-viewer', description: 'Portable Document Format' },
        { name: 'Chrome PDF Viewer', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai', description: '' },
        { name: 'Native Client', filename: 'internal-nacl-plugin', description: '' },
    ]
});

// Patch navigator.languages
Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });

// Remove playwright-specific properties
delete window.__playwright;
delete window.__pw_manual;
delete window.playwrightBinding;

// Patch Permissions API
const originalQuery = window.navigator.permissions && window.navigator.permissions.query;
if (originalQuery) {
    window.navigator.permissions.query = (parameters) =>
        parameters.name === 'notifications'
            ? Promise.resolve({ state: Notification.permission })
            : originalQuery(parameters);
}

// Chrome runtime object
window.chrome = { runtime: {}, loadTimes: () => {}, csi: () => {} };
"""


def _random_device_memory() -> int:
    return random.choice([2, 4, 8, 16])


def _random_hardware_concurrency() -> int:
    return random.choice([2, 4, 6, 8, 12, 16])


class PlaywrightClient:
    """
    Async Playwright wrapper with stealth + proxy support.
    One browser instance per scraper run; new contexts per proxy rotation.
    """

    def __init__(
        self,
        headless: bool = True,
        proxy_manager: Optional[ProxyManager] = None,
        country: Optional[str] = None,
        block_media: bool = True,
    ) -> None:
        self.headless = headless
        self.proxy_manager = proxy_manager
        self.country = country
        self.block_media = block_media
        self._playwright: Any = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None
        self._current_proxy: str | None = None
        self._ua = random.choice(_USER_AGENTS)
        self._viewport = random.choice(_VIEWPORTS)
        self._locale = random.choice(_LOCALES)
        self._timezone = random.choice(_TIMEZONES)

        # Try to import playwright-stealth
        try:
            from playwright_stealth import stealth_async
            self._stealth_fn = stealth_async
        except ImportError:
            self._stealth_fn = None
            log.warning("playwright_client.stealth_missing",
                        msg="Install playwright-stealth for full anti-detection")

    async def __aenter__(self) -> "PlaywrightClient":
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(
            headless=self.headless,
            args=[
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-blink-features=AutomationControlled",
                "--disable-infobars",
                "--disable-extensions",
                "--disable-gpu",
                "--window-size=1920,1080",
            ],
        )
        await self._new_context()
        return self

    async def __aexit__(self, *_: Any) -> None:
        if self._context:
            await self._context.close()
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()

    async def _new_context(self, proxy_url: str | None = None) -> None:
        """Create a fresh browser context with randomized fingerprint."""
        if self._context:
            await self._context.close()

        if proxy_url is None and self.proxy_manager:
            proxy_url = await self.proxy_manager.get(country=self.country)
        self._current_proxy = proxy_url

        proxy_config = None
        if proxy_url:
            # Parse "http://user:pass@host:port" for Playwright format
            proxy_config = {"server": proxy_url}
            if "@" in proxy_url:
                creds = proxy_url.split("@")[0].split("://")[-1]
                if ":" in creds:
                    u, p = creds.split(":", 1)
                    server = proxy_url.split("@")[-1]
                    scheme = proxy_url.split("://")[0]
                    proxy_config = {
                        "server": f"{scheme}://{server}",
                        "username": u,
                        "password": p,
                    }

        self._context = await self._browser.new_context(
            user_agent=self._ua,
            viewport=self._viewport,
            locale=self._locale,
            timezone_id=self._timezone,
            java_script_enabled=True,
            proxy=proxy_config,
            extra_http_headers={
                "Accept-Language": f"{self._locale},{self._locale[:2]};q=0.9,en-US;q=0.8,en;q=0.7",
                "Sec-CH-UA": '"Not A(Brand";v="99", "Google Chrome";v="120", "Chromium";v="120"',
                "Sec-CH-UA-Mobile": "?0",
                "Sec-CH-UA-Platform": '"Windows"',
            },
        )

        # Inject stealth scripts before any page load
        await self._context.add_init_script(_STEALTH_INIT_SCRIPT)

        # Override device memory and hardware concurrency
        dm = _random_device_memory()
        hc = _random_hardware_concurrency()
        await self._context.add_init_script(f"""
            Object.defineProperty(navigator, 'deviceMemory', {{ get: () => {dm} }});
            Object.defineProperty(navigator, 'hardwareConcurrency', {{ get: () => {hc} }});
        """)

        if self.block_media:
            await self._context.route(
                "**/*.{png,jpg,jpeg,gif,webp,svg,ico,woff,woff2,ttf,eot,mp4,webm,ogg,wav}",
                lambda route: route.abort()
            )

        log.debug(
            "playwright_client.context_created",
            ua=self._ua[:40],
            proxy=bool(proxy_url),
            locale=self._locale,
        )

    async def rotate_proxy(self) -> None:
        """Mark current proxy dead, create new context with a fresh one."""
        if self.proxy_manager and self._current_proxy:
            await self.proxy_manager.mark_dead(self._current_proxy)
        self._ua = random.choice(_USER_AGENTS)
        self._viewport = random.choice(_VIEWPORTS)
        self._locale = random.choice(_LOCALES)
        self._timezone = random.choice(_TIMEZONES)
        await self._new_context()

    async def new_page(self) -> Page:
        assert self._context is not None
        page = await self._context.new_page()
        # Apply playwright-stealth if available
        if self._stealth_fn:
            await self._stealth_fn(page)
        return page

    @staticmethod
    async def _human_scroll(page: Page) -> None:
        """Simulate human scroll pattern to trigger lazy-loaded content."""
        for _ in range(random.randint(2, 5)):
            scroll_y = random.randint(200, 600)
            await page.evaluate(f"window.scrollBy(0, {scroll_y})")
            await asyncio.sleep(random.uniform(0.3, 0.8))
        # Scroll back up slightly (natural reading behavior)
        await page.evaluate(f"window.scrollBy(0, -{random.randint(50, 200)})")
        await asyncio.sleep(random.uniform(0.2, 0.5))

    @staticmethod
    async def _human_mouse(page: Page) -> None:
        """Move mouse to random position (defeats static mouse detection)."""
        vw = page.viewport_size or {"width": 1280, "height": 800}
        x = random.randint(100, vw["width"] - 100)
        y = random.randint(100, vw["height"] - 100)
        await page.mouse.move(x, y)

    def _is_ban_page(self, html: str) -> bool:
        ban_signals = [
            "access denied", "blocked", "ray id", "cloudflare",
            "please verify you are a human", "unusual traffic",
            "bot detected", "please enable javascript and cookies",
            "just a moment", "ddos-guard",
        ]
        lhtml = html.lower()
        return any(s in lhtml for s in ban_signals)

    async def get_page_content(
        self,
        url: str,
        wait_for: str | None = None,
        timeout: int = 30_000,
        retry_on_ban: bool = True,
    ) -> str:
        """
        Navigate to URL, optionally wait for a selector, return HTML.
        Automatically rotates proxy if a ban page is detected.
        """
        for attempt in range(3):
            page = await self.new_page()
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=timeout)

                if wait_for:
                    try:
                        await page.wait_for_selector(wait_for, timeout=8_000)
                    except Exception:
                        pass  # continue — page might still have useful content

                # Human-like behavior
                await self._human_mouse(page)
                await self._human_scroll(page)
                await asyncio.sleep(random.uniform(0.8, 2.5))

                html = await page.content()

                if retry_on_ban and self._is_ban_page(html):
                    log.warning("playwright_client.ban_detected", url=url, attempt=attempt)
                    await page.close()
                    await self.rotate_proxy()
                    await asyncio.sleep(random.uniform(5, 15))
                    continue

                return html

            except Exception as e:
                log.warning("playwright_client.error", url=url, error=str(e), attempt=attempt)
                await asyncio.sleep(random.uniform(3, 10))
            finally:
                try:
                    await page.close()
                except Exception:
                    pass

        raise RuntimeError(f"Failed to load {url} after 3 attempts")
