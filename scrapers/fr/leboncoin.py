"""
leboncoin.fr â€” Playwright + XHR. CF Turnstile + Next.js SPA.
Playwright executes JS to pass CF challenge. Intercepts API responses.
Segmented by dÃ©partement (96 mainland + 5 DOM) for full coverage.
Listing URL: /voitures/{id}.htm
"""
from __future__ import annotations
import asyncio, json, re, time
from scrapers.common.indexer import run_portal, make_pg, make_redis, ensure_schema, delta
from scrapers.common.pw_base import make_stealth_browser, make_stealth_page


import logging
log = logging.getLogger(__name__)

_SOURCE, _COUNTRY, _DOMAIN = "leboncoin", "FR", "www.leboncoin.fr"
_BASE = "https://www.leboncoin.fr"
_API_RE = re.compile(r'leboncoin\.fr/(?:api|_next/data|recherche)', re.I)
_LISTING_RE = re.compile(r'"(/voitures/\d+\.htm)"')

_DEPTS = [
    "01","02","03","04","05","06","07","08","09","10",
    "11","12","13","14","15","16","17","18","19","21",
    "22","23","24","25","26","27","28","29","2A","2B",
    "30","31","32","33","34","35","36","37","38","39",
    "40","41","42","43","44","45","46","47","48","49",
    "50","51","52","53","54","55","56","57","58","59",
    "60","61","62","63","64","65","66","67","68","69",
    "70","71","72","73","74","75","76","77","78","79",
    "80","81","82","83","84","85","86","87","88","89",
    "90","91","92","93","94","95","971","972","973","974",
]


def _extract(body: str, url: str) -> list[str]:
    urls: set[str] = set()
    try:
        raw = json.dumps(json.loads(body))
        for m in _LISTING_RE.finditer(raw):
            urls.add(_BASE + m.group(1))
    except Exception:
        pass
    for m in _LISTING_RE.finditer(body):
        urls.add(_BASE + m.group(1))
    return list(urls)


async def _collect() -> list[str]:
    collected: set[str] = set()
    pw, browser = None, None
    try:
        from playwright.async_api import async_playwright
        pw = await async_playwright().start()
        from scrapers.common.pw_base import _STEALTH_JS, _UA
        browser = await pw.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled","--no-sandbox","--disable-dev-shm-usage"],
        )
        context = await browser.new_context(
            user_agent=_UA, locale="fr-FR", viewport={"width": 1280, "height": 900},
            extra_http_headers={"Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8"},
        )
        await context.add_init_script(_STEALTH_JS)
        page = await context.new_page()

        captured: list[str] = []

        async def on_response(resp):
            try:
                if _API_RE.search(resp.url):
                    body = await resp.text()
                    captured.extend(_extract(body, resp.url))
            except Exception:
                pass

        page.on("response", on_response)

        for dept in _DEPTS:
            for pg in range(1, 50):  # max 50 pages per dept
                captured.clear()
                url = f"{_BASE}/recherche?category=2&locations={dept}&page={pg}"
                try:
                    await page.goto(url, wait_until="domcontentloaded", timeout=30_000)
                    await page.wait_for_timeout(2500)
                except Exception:
                    break

                dom = await page.content()
                page_urls = set(captured) | set(_BASE + m.group(1) for m in _LISTING_RE.finditer(dom))
                if not page_urls:
                    break
                prev = len(collected)
                collected.update(page_urls)
                if len(collected) == prev:
                    break

            log.debug("leboncoin dept=%s total=%d", dept, len(collected))
    finally:
        if browser: await browser.close()
        if pw: await pw.stop()

    log.info("leboncoin/FR total_urls=%d", len(collected))
    return list(collected)


async def run(): await run_portal(source=_SOURCE, country=_COUNTRY, domain=_DOMAIN, fetch_all_urls=_collect)
if __name__ == "__main__": asyncio.run(run())

