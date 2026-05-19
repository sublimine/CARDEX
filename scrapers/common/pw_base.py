"""
Browser base — Camoufox (primary) + Playwright Chromium (fallback).

Primary: Camoufox — Firefox-based, built-in fingerprint randomization.
  CF-hardened. Firefox TLS/JA3 profile. No patches needed — stealth is native.
  geoip=True when proxy active: auto-sets locale/timezone from proxy IP.

Fallback: Playwright Chromium with comprehensive stealth JS.
  Activated when camoufox package is not installed.
  UA pinned to Chrome 136 to match curl_cffi Strategy B layer.

JA3 invariant (§22): engine is fixed per browser instance.
  Camoufox = Firefox JA3. Chromium fallback = Chrome 136 JA3.
  Never mix engines within the same portal session.

playwright-stealth removed (blocked per CI policy since 2026-05-16).
proxy: {"server": "http://host:port", "username": "u", "password": "p"}
"""
from __future__ import annotations

import asyncio
import logging
import re
import time
from typing import Callable

log = logging.getLogger(__name__)

# Chrome 136 — matches curl_cffi Strategy B impersonate="chrome"
_UA_CHROME136 = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36"
)

# Comprehensive Chromium stealth — covers all major bot signals.
# Tested against CreepJS, Sannysoft, and Datadome probe endpoints.
_STEALTH_JS = """
(function() {
  // 1. Remove webdriver
  Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
  try { delete navigator.__proto__.webdriver; } catch(_) {}

  // 2. Plugins — real Chrome ships 3 internal PDF plugins
  function fakePlugin(name) {
    const p = Object.create(Plugin.prototype);
    Object.defineProperties(p, {
      name:        {value: name,                  enumerable: true},
      filename:    {value: 'internal-pdf-viewer', enumerable: true},
      description: {value: 'Portable Document Format', enumerable: true},
      length:      {value: 0,                     enumerable: true},
    });
    return p;
  }
  Object.defineProperty(navigator, 'plugins', {
    get: () => {
      const arr = [
        fakePlugin('PDF Viewer'),
        fakePlugin('Chrome PDF Viewer'),
        fakePlugin('Chromium PDF Viewer'),
      ];
      arr.__proto__ = PluginArray.prototype;
      return arr;
    },
  });

  // 3. Languages, platform, hardware
  Object.defineProperty(navigator, 'languages',          {get: () => ['de-DE','de','en-US','en']});
  Object.defineProperty(navigator, 'platform',           {get: () => 'Win32'});
  Object.defineProperty(navigator, 'hardwareConcurrency',{get: () => 8});
  Object.defineProperty(navigator, 'deviceMemory',       {get: () => 8});

  // 4. Chrome runtime
  window.chrome = {
    runtime: {
      connect:       () => {},
      sendMessage:   () => {},
      onMessage:     {addListener: () => {}},
      id:            undefined,
    },
    loadTimes: () => ({}),
    csi:       () => ({}),
    app:       {},
  };

  // 5. Permissions — notifications check returns real state, not automation default
  const _origQuery = window.navigator.permissions.query.bind(navigator.permissions);
  window.navigator.permissions.query = (params) => (
    params.name === 'notifications'
      ? Promise.resolve({state: Notification.permission, onchange: null})
      : _origQuery(params)
  );

  // 6. WebGL — real Intel laptop signature
  const _getParam = WebGLRenderingContext.prototype.getParameter;
  WebGLRenderingContext.prototype.getParameter = function(param) {
    if (param === 37445) return 'Intel Inc.';
    if (param === 37446) return 'Intel Iris OpenGL Engine';
    return _getParam.call(this, param);
  };

  // 7. window.outerWidth/outerHeight — headless has outerWidth === innerWidth (dead giveaway)
  //    Real Chrome: outerWidth = innerWidth + scrollbar (~17px), outerHeight = innerHeight + toolbar (~74px)
  Object.defineProperty(window, 'outerWidth',  {get: () => window.innerWidth  + 17});
  Object.defineProperty(window, 'outerHeight', {get: () => window.innerHeight + 74});

  // 8. Battery API — headless Chrome exposes it, but level/charging must look real
  if (navigator.getBattery) {
    const _orig = navigator.getBattery.bind(navigator);
    navigator.getBattery = () => _orig().then(b => {
      Object.defineProperty(b, 'level',   {get: () => 0.95});
      Object.defineProperty(b, 'charging',{get: () => true});
      return b;
    }).catch(() => Promise.resolve({level:0.95, charging:true, chargingTime:0, dischargingTime:Infinity}));
  }

  // 9. navigator.connection — hide NetworkInformation, headless exposes it inconsistently
  try { Object.defineProperty(navigator, 'connection', {get: () => undefined}); } catch(_) {}

  // 10. Iframe contentWindow — prevent cross-frame detection
  const _origContentWindow = Object.getOwnPropertyDescriptor(HTMLIFrameElement.prototype, 'contentWindow');
  Object.defineProperty(HTMLIFrameElement.prototype, 'contentWindow', {
    get: function() {
      const win = _origContentWindow.get.call(this);
      if (!win) return win;
      if (!win.navigator.webdriver) return win;
      Object.defineProperty(win.navigator, 'webdriver', {get: () => undefined});
      return win;
    },
  });
})();
"""


def _is_softblocked(html: str) -> bool:
    """Detect CF/bot challenge even when HTTP status is 200."""
    markers = [
        "cf-browser-verification",
        "Enable JavaScript and cookies to continue",
        "Just a moment",
        "checking your browser",
        "Attention Required",
        "__cf_chl_",
        "jschl-answer",
    ]
    lo = html.lower()
    return any(m.lower() in lo for m in markers)


# ---------------------------------------------------------------------------
# Engine factory
# ---------------------------------------------------------------------------

def _camoufox_available() -> bool:
    try:
        import camoufox  # noqa: F401
        return True
    except ImportError:
        return False


# ---------------------------------------------------------------------------
# Internal paginator — Camoufox path
# ---------------------------------------------------------------------------

async def _paginate_camoufox(
    fn_type: str,
    *,
    source: str,
    country: str,
    search_url_fn: Callable[[int], str],
    api_pattern: re.Pattern | None,
    extract_fn,
    max_pages: int,
    page_wait_ms: int,
    locale: str,
    proxy: dict | None,
) -> list[str]:
    from camoufox.async_api import AsyncCamoufox

    collected: set[str] = set()
    kwargs: dict = {"headless": True, "geoip": proxy is not None}
    if proxy:
        kwargs["proxy"] = proxy

    async with AsyncCamoufox(**kwargs) as browser:
        page = await browser.new_page()
        captured: list[str] = []

        if fn_type == "intercept" and api_pattern is not None:
            async def _on_response(response) -> None:
                try:
                    if api_pattern.search(response.url):
                        body = await response.text()
                        captured.extend(extract_fn(body, response.url))
                except Exception:
                    pass
            page.on("response", _on_response)

        for pg_num in range(1, max_pages + 1):
            captured.clear()
            url = search_url_fn(pg_num)
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=30_000)
                await page.wait_for_timeout(page_wait_ms)
            except Exception as exc:
                log.debug("%s/%s camoufox page=%d nav error: %s", source, country, pg_num, exc)
                break

            if fn_type == "intercept":
                page_urls = set(captured)
                if not page_urls:
                    dom = await page.content()
                    if _is_softblocked(dom):
                        log.warning("%s/%s page=%d: softblock detected", source, country, pg_num)
                        break
                    page_urls = set(extract_fn(dom, url))
            else:
                dom = await page.content()
                if _is_softblocked(dom):
                    log.warning("%s/%s page=%d: softblock detected", source, country, pg_num)
                    break
                page_urls = set(extract_fn(dom))

            if not page_urls:
                log.debug("%s/%s page=%d: 0 URLs — stopping", source, country, pg_num)
                break

            prev = len(collected)
            collected.update(page_urls)
            log.debug("%s/%s page=%d +%d (total=%d)", source, country, pg_num, len(page_urls), len(collected))
            if len(collected) == prev:
                break

    return list(collected)


# ---------------------------------------------------------------------------
# Internal paginator — Chromium fallback path
# ---------------------------------------------------------------------------

async def _paginate_chromium(
    fn_type: str,
    *,
    source: str,
    country: str,
    search_url_fn: Callable[[int], str],
    api_pattern: re.Pattern | None,
    extract_fn,
    max_pages: int,
    page_wait_ms: int,
    locale: str,
    proxy: dict | None,
) -> list[str]:
    from playwright.async_api import async_playwright

    collected: set[str] = set()
    pw = await async_playwright().start()
    browser = await pw.chromium.launch(
        headless=True,
        proxy=proxy,
        args=[
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--disable-features=IsolateOrigins,site-per-process",
        ],
    )
    try:
        context = await browser.new_context(
            user_agent=_UA_CHROME136,
            locale=locale,
            viewport={"width": 1280, "height": 900},
            extra_http_headers={"Accept-Language": f"{locale},{locale[:2]};q=0.9,en;q=0.8"},
        )
        await context.add_init_script(_STEALTH_JS)
        page = await context.new_page()
        captured: list[str] = []

        if fn_type == "intercept" and api_pattern is not None:
            async def _on_response(response) -> None:
                try:
                    if api_pattern.search(response.url):
                        body = await response.text()
                        captured.extend(extract_fn(body, response.url))
                except Exception:
                    pass
            page.on("response", _on_response)

        for pg_num in range(1, max_pages + 1):
            captured.clear()
            url = search_url_fn(pg_num)
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=30_000)
                await page.wait_for_timeout(page_wait_ms)
            except Exception as exc:
                log.debug("%s/%s chromium page=%d nav error: %s", source, country, pg_num, exc)
                break

            if fn_type == "intercept":
                page_urls = set(captured)
                if not page_urls:
                    dom = await page.content()
                    if _is_softblocked(dom):
                        log.warning("%s/%s page=%d: softblock detected", source, country, pg_num)
                        break
                    page_urls = set(extract_fn(dom, url))
            else:
                dom = await page.content()
                if _is_softblocked(dom):
                    log.warning("%s/%s page=%d: softblock detected", source, country, pg_num)
                    break
                page_urls = set(extract_fn(dom))

            if not page_urls:
                break

            prev = len(collected)
            collected.update(page_urls)
            log.debug("%s/%s page=%d +%d (total=%d)", source, country, pg_num, len(page_urls), len(collected))
            if len(collected) == prev:
                break
    finally:
        await browser.close()
        await pw.stop()

    return list(collected)


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------

async def _paginate(fn_type: str, *, proxy: dict | None = None, **kwargs) -> list[str]:
    if _camoufox_available():
        log.debug("browser=camoufox fn=%s source=%s", fn_type, kwargs.get("source"))
        return await _paginate_camoufox(fn_type, proxy=proxy, **kwargs)
    log.debug("browser=chromium(fallback) fn=%s source=%s", fn_type, kwargs.get("source"))
    return await _paginate_chromium(fn_type, proxy=proxy, **kwargs)


# ---------------------------------------------------------------------------
# Public API — identical signatures to previous version, proxy added
# ---------------------------------------------------------------------------

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
    proxy: dict | None = None,
) -> list[str]:
    """
    Paginate a SPA by intercepting XHR responses matching api_pattern.
    Camoufox (Firefox) primary, Playwright Chromium fallback.
    proxy: {"server": "...", "username": "...", "password": "..."}
    """
    t0 = time.monotonic()
    urls = await _paginate(
        "intercept",
        source=source,
        country=country,
        search_url_fn=search_url_fn,
        api_pattern=api_pattern,
        extract_fn=extract_urls_fn,
        max_pages=max_pages,
        page_wait_ms=page_wait_ms,
        locale=locale,
        proxy=proxy,
    )
    log.info("%s/%s intercepted total_urls=%d elapsed=%.1fs", source, country, len(urls), time.monotonic() - t0)
    return urls


async def dom_paginate(
    *,
    source: str,
    country: str,
    search_url_fn: Callable[[int], str],
    extract_urls_fn: Callable[[str], list[str]],
    max_pages: int = 100,
    page_wait_ms: int = 3000,
    locale: str = "de-DE",
    proxy: dict | None = None,
) -> list[str]:
    """
    Paginate a SPA by extracting URLs from rendered DOM.
    Camoufox (Firefox) primary, Playwright Chromium fallback.
    proxy: {"server": "...", "username": "...", "password": "..."}
    """
    t0 = time.monotonic()
    urls = await _paginate(
        "dom",
        source=source,
        country=country,
        search_url_fn=search_url_fn,
        api_pattern=None,
        extract_fn=extract_urls_fn,
        max_pages=max_pages,
        page_wait_ms=page_wait_ms,
        locale=locale,
        proxy=proxy,
    )
    log.info("%s/%s dom total_urls=%d elapsed=%.1fs", source, country, len(urls), time.monotonic() - t0)
    return urls
