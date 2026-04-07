"""
Stealth Browser — Playwright with anti-detection for the Dealer Spider.

Two operational modes:
  1. extract()        — passive XHR capture on a single URL (legacy)
  2. extract_spa()    — ACTIVE targeted interception across inventory paths,
                        filters responses by vehicle-API patterns, closes page
                        the instant usable JSON arrives. Zero DOM wait.

CAPTCHA resilience:
  - If CAPTCHA_API_KEY is absent or 2Captcha fails, the browser does NOT crash.
  - Raises CaptchaUnavailableError so the spider can mark the dealer
    WAF_BLOCKED_NO_CAPTCHA in PostgreSQL and move on.

All Playwright contexts auto-close on exit — no orphan processes.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import random
from typing import Any

from playwright.async_api import (
    async_playwright,
    Browser,
    BrowserContext,
    Page,
    Route,
    Request,
    Response as PWResponse,
)

log = logging.getLogger("spider.stealth_browser")


# ── Exceptions ───────────────────────────────────────────────────────────────

class CaptchaUnavailableError(Exception):
    """CAPTCHA required but cannot be solved (no key, no balance, solve failed)."""
    def __init__(self, reason: str, waf_type: str = "captcha"):
        self.reason = reason
        self.waf_type = waf_type
        super().__init__(f"CAPTCHA unavailable: {reason}")


# ── Country-specific browser context profiles ────────────────────────────────

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

_VIEWPORTS = [
    {"width": 1920, "height": 1080},
    {"width": 1366, "height": 768},
    {"width": 1440, "height": 900},
    {"width": 1536, "height": 864},
    {"width": 1680, "height": 1050},
]

_BLOCKED_RESOURCE_TYPES = {"image", "media", "font", "stylesheet", "websocket", "other"}

_PROXY_T1 = os.environ.get("PROXY_T1", "")
_PROXY_T2 = os.environ.get("PROXY_T2", "")
_CAPTCHA_API_KEY = os.environ.get("CAPTCHA_API_KEY", "")

# ── Vehicle API endpoint patterns ────────────────────────────────────────────
# These match the internal XHR calls that SPA dealer sites make to their backends.
# When we see a response URL matching any of these AND the body is JSON >1KB,
# we grab it immediately.

_VEHICLE_API_RE = re.compile(
    r"("
    r"/api/|/v\d+/|/rest/|/graphql|/gql"
    r"|/vehicles|/vehicle|/stock|/inventory|/listings|/cars"
    r"|/search|/results|/catalog|/offers"
    r"|/fahrzeuge|/voitures|/coches|/autos|/occasions"
    r"|/tweedehands|/occasionen|/gebrauchtwagen"
    r"|/wp-json/|/feed/|/_next/data/"
    r")",
    re.IGNORECASE,
)

# Inventory page paths to try with Playwright (multilingual)
_SPA_INVENTORY_PATHS = [
    "/", "/stock", "/inventory", "/vehicles", "/cars", "/used-cars",
    "/coches", "/fahrzeuge", "/voitures", "/occasion", "/gebrauchtwagen",
    "/tweedehands", "/occasions", "/gamas/ocasion", "/angebote",
    "/usados", "/coches-ocasion", "/autos", "/fleet",
]

# CAPTCHA selectors — covers reCAPTCHA v2/v3, hCaptcha, Cloudflare Turnstile
_CAPTCHA_SELECTORS = "[data-sitekey], .g-recaptcha, .h-captcha, #cf-turnstile, #captcha-container"

# Challenge page markers in HTML (Cloudflare, Datadome, Akamai)
_CHALLENGE_MARKERS = [
    "managed_checking_msg",        # Cloudflare
    "cf-browser-verification",     # Cloudflare legacy
    "geo.captcha-delivery.com",    # Datadome
    "datadome",                    # Datadome
    "akamai-browser-challenge",    # Akamai
    "_sec_cpt",                    # Akamai cookie challenge
    "px-captcha",                  # PerimeterX
]


# ── Network Interceptor ─────────────────────────────────────────────────────

async def _intercept_route(route: Route, request: Request) -> None:
    """Block non-essential resources. Only HTML/JSON/JS pass through."""
    if request.resource_type in _BLOCKED_RESOURCE_TYPES:
        await route.abort()
        return

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
    scroll_count = random.randint(2, 3)
    for _ in range(scroll_count):
        scroll_amount = random.randint(300, 800)
        await page.evaluate(f"window.scrollBy(0, {scroll_amount})")
        await asyncio.sleep(random.uniform(0.4, 1.2))


# ── CAPTCHA Solver (resilient) ───────────────────────────────────────────────

async def _solve_captcha_2captcha(site_key: str, page_url: str) -> str:
    """
    Send CAPTCHA to 2Captcha, wait for solution, return token.
    Raises CaptchaUnavailableError on ANY failure — never returns None.
    """
    if not _CAPTCHA_API_KEY:
        raise CaptchaUnavailableError("CAPTCHA_API_KEY not set")

    import httpx

    try:
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
                error_text = result.get("request", "unknown")
                if "ERROR_ZERO_BALANCE" in str(error_text):
                    raise CaptchaUnavailableError("2captcha zero balance")
                if "ERROR_WRONG_USER_KEY" in str(error_text) or "ERROR_KEY_DOES_NOT_EXIST" in str(error_text):
                    raise CaptchaUnavailableError("2captcha invalid API key")
                raise CaptchaUnavailableError(f"2captcha submit rejected: {error_text}")

            task_id = result["request"]

            for _ in range(24):  # 120s max
                await asyncio.sleep(5)
                poll = await client.get("https://2captcha.com/res.php", params={
                    "key": _CAPTCHA_API_KEY,
                    "action": "get",
                    "id": task_id,
                    "json": 1,
                })
                poll_result = poll.json()
                if poll_result.get("status") == 1:
                    return poll_result["request"]
                if poll_result.get("request") == "ERROR_CAPTCHA_UNSOLVABLE":
                    raise CaptchaUnavailableError("2captcha could not solve")

            raise CaptchaUnavailableError("2captcha timeout (120s)")

    except CaptchaUnavailableError:
        raise
    except Exception as exc:
        raise CaptchaUnavailableError(f"2captcha network error: {exc}") from exc


# ── Challenge Detection ──────────────────────────────────────────────────────

def _is_challenge_page(html: str) -> bool:
    """Detect if the page is a WAF challenge/interstitial, not real content."""
    html_lower = html[:5000].lower()
    hits = sum(1 for marker in _CHALLENGE_MARKERS if marker in html_lower)
    return hits >= 1


# ── Stealth Browser Client ──────────────────────────────────────────────────

class StealthBrowser:
    """
    Playwright browser with anti-detection for the Dealer Spider.

    Usage:
        async with StealthBrowser(country="ES", proxy_tier=1) as browser:
            # Active SPA extraction — tries multiple paths, intercepts API calls
            vehicles_json, html = await browser.extract_spa(
                base_url="https://dealer.com",
                is_whale=True,
            )
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
            try:
                await self._context.close()
            except Exception:
                pass
        if self._browser:
            try:
                await self._browser.close()
            except Exception:
                pass
        if self._playwright:
            try:
                await self._playwright.stop()
            except Exception:
                pass

    async def _create_context(self) -> None:
        """Create a new browser context with stealth patches and country profile."""
        if self._context:
            try:
                await self._context.close()
            except Exception:
                pass

        ctx_config = _COUNTRY_CONTEXT.get(self._country, _COUNTRY_CONTEXT["DE"])
        viewport = random.choice(_VIEWPORTS)

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

        # Stealth patches
        try:
            from playwright_stealth import stealth_async
            await stealth_async(self._context)
        except ImportError:
            await self._context.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
                Object.defineProperty(navigator, 'plugins', {
                    get: () => [1, 2, 3, 4, 5],
                });
                Object.defineProperty(navigator, 'languages', {
                    get: () => ['""" + ctx_config["locale"] + """', 'en-US', 'en'],
                });
                if (!window.chrome) { window.chrome = {}; }
                if (!window.chrome.runtime) { window.chrome.runtime = {}; }
                const originalQuery = window.navigator.permissions.query;
                window.navigator.permissions.query = (parameters) =>
                    parameters.name === 'notifications'
                        ? Promise.resolve({ state: Notification.permission })
                        : originalQuery(parameters);
            """)

        await self._context.route("**/*", _intercept_route)
        self._pages_used = 0

    async def _ensure_fresh_context(self) -> None:
        """Rotate context after N pages to avoid fingerprint accumulation."""
        self._pages_used += 1
        if self._pages_used >= self._max_pages_per_context:
            log.debug("stealth_browser: rotating context after %d pages", self._pages_used)
            await self._create_context()
            self._max_pages_per_context = random.randint(5, 10)

    # ── Core: targeted XHR interception on a single page ─────────────────

    async def _intercept_page(
        self,
        url: str,
        timeout: int = 30_000,
    ) -> tuple[str, list[dict], list[str]]:
        """
        Navigate to URL with TARGETED XHR interception.
        Captures only responses whose URL matches _VEHICLE_API_RE and body is JSON >1KB.
        Returns (html, intercepted_vehicle_json_list, iframe_srcs).
        """
        await self._ensure_fresh_context()
        page = await self._context.new_page()
        intercepted: list[dict] = []

        async def _on_response(response: PWResponse) -> None:
            try:
                resp_url = response.url
                ct = response.headers.get("content-type", "")

                # Only capture JSON from vehicle-related API endpoints
                if response.status != 200:
                    return
                if "json" not in ct and "javascript" not in ct:
                    return

                # Targeted filter: URL must match vehicle API patterns
                if not _VEHICLE_API_RE.search(resp_url):
                    return

                body = await response.body()
                if len(body) < 512:  # too small to be inventory
                    return

                data = json.loads(body)
                intercepted.append(data)
                log.debug("stealth_browser: intercepted API response from %s (%d bytes)",
                          resp_url, len(body))
            except Exception:
                pass

        page.on("response", _on_response)

        try:
            await page.goto(url, wait_until="networkidle", timeout=timeout)
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

    # ── CAPTCHA handling with resilient fallback ─────────────────────────

    async def _handle_captcha_if_present(
        self,
        page: Page,
        url: str,
        is_whale: bool,
    ) -> None:
        """
        Check page for CAPTCHA. If found:
          - whale + key available → solve and inject
          - otherwise → raise CaptchaUnavailableError (spider marks dealer + moves on)
        """
        has_captcha = await page.query_selector(_CAPTCHA_SELECTORS)

        if not has_captcha:
            # Also check HTML body for challenge interstitials
            html_snippet = await page.content()
            if not _is_challenge_page(html_snippet):
                return  # no challenge, proceed normally

        # We have a challenge
        site_key = None
        if has_captcha:
            site_key = await has_captcha.get_attribute("data-sitekey")

        if not is_whale:
            raise CaptchaUnavailableError("captcha_non_whale", waf_type="captcha")

        if not site_key:
            raise CaptchaUnavailableError("captcha_no_sitekey", waf_type="captcha")

        # Whale path: attempt solve
        log.info("stealth_browser: whale CAPTCHA on %s, attempting solve", url)
        token = await _solve_captcha_2captcha(site_key, url)

        # Inject solution
        await page.evaluate(f"""
            (function() {{
                var el = document.getElementById('g-recaptcha-response');
                if (el) el.value = '{token}';
                var hel = document.querySelector('[name="h-captcha-response"]');
                if (hel) hel.value = '{token}';
                if (typeof ___grecaptcha_cfg !== 'undefined') {{
                    Object.keys(___grecaptcha_cfg.clients).forEach(function(key) {{
                        var client = ___grecaptcha_cfg.clients[key];
                        if (client && client.M && client.M.callback) {{
                            client.M.callback('{token}');
                        }}
                    }});
                }}
            }})();
        """)
        await asyncio.sleep(3)

    # ── Main API: extract_spa ────────────────────────────────────────────

    async def extract_spa(
        self,
        base_url: str,
        is_whale: bool = False,
        timeout: int = 30_000,
        max_paths: int = 8,
    ) -> tuple[list[dict], str, list[str]]:
        """
        ACTIVE SPA extraction — the primary Playwright vector.

        1. Opens the dealer's homepage in the stealth browser
        2. If challenge detected → solve (whale) or raise CaptchaUnavailableError
        3. Listens on page.on('response') for XHR calls matching _VEHICLE_API_RE
        4. If homepage yields nothing, tries inventory paths one by one
        5. The INSTANT we get usable JSON, we grab it and close the page

        Returns:
            (intercepted_json_list, final_html, iframe_srcs)

        Raises:
            CaptchaUnavailableError — if CAPTCHA blocks us and we can't solve it
        """
        await self._ensure_fresh_context()
        base = base_url.rstrip("/")
        all_intercepted: list[dict] = []
        final_html = ""
        all_iframes: list[str] = []

        # Build URL list: homepage + inventory paths
        urls_to_try = [base]
        for path in _SPA_INVENTORY_PATHS:
            candidate = base + path
            if candidate != base and candidate not in urls_to_try:
                urls_to_try.append(candidate)

        for url in urls_to_try[:max_paths]:
            page = await self._context.new_page()
            page_intercepted: list[dict] = []

            async def _on_response(response: PWResponse) -> None:
                try:
                    if response.status != 200:
                        return
                    ct = response.headers.get("content-type", "")
                    if "json" not in ct:
                        return
                    if not _VEHICLE_API_RE.search(response.url):
                        return
                    body = await response.body()
                    if len(body) < 512:
                        return
                    data = json.loads(body)
                    page_intercepted.append(data)
                    log.debug("stealth_browser: XHR intercepted %s (%d bytes)",
                              response.url, len(body))
                except Exception:
                    pass

            page.on("response", _on_response)

            try:
                await page.goto(url, wait_until="networkidle", timeout=timeout)

                # CAPTCHA gate — raises CaptchaUnavailableError if blocked
                await self._handle_captcha_if_present(page, url, is_whale)

                # If we solved a CAPTCHA, re-navigate to get real content
                if page_intercepted:
                    # Already got data during initial load + captcha solve
                    pass
                else:
                    # Scroll to trigger lazy-loading XHR calls
                    await _simulate_human_scroll(page)
                    # Give SPA time to fire its API calls after scroll
                    await asyncio.sleep(1.5)

                html = await page.content()

                # Grab iframes
                iframe_els = await page.query_selector_all("iframe[src]")
                for iframe_el in iframe_els:
                    src = await iframe_el.get_attribute("src")
                    if src:
                        all_iframes.append(src)

                if page_intercepted:
                    all_intercepted.extend(page_intercepted)
                    final_html = html
                    log.info("stealth_browser: captured %d API responses from %s",
                             len(page_intercepted), url)
                    await page.close()
                    break  # got data, stop trying paths

                # No XHR caught — check if rendered HTML has useful content
                # (some SPAs inject JSON-LD after client-side render)
                if not final_html:
                    final_html = html

            except CaptchaUnavailableError:
                await page.close()
                raise  # propagate to spider
            except Exception as exc:
                log.debug("stealth_browser: page %s failed: %s", url, exc)
            finally:
                if not page.is_closed():
                    await page.close()

        return all_intercepted, final_html, all_iframes

    # ── Legacy extract (kept for backward compat) ────────────────────────

    async def extract(
        self,
        url: str,
        timeout: int = 30_000,
    ) -> tuple[str, list[dict], list[str]]:
        """
        Legacy passive extraction — navigate, intercept everything, return.
        Prefer extract_spa() for SPA dealers.
        """
        return await self._intercept_page(url, timeout)
