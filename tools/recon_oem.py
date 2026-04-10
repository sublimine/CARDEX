"""
OEM API Reconnaissance — passive XHR interception via Playwright.

Single-use script: opens OEM used-car search pages in a stealth browser,
simulates a search, and captures all XHR/Fetch responses that contain
vehicle data. Outputs the full request structure (URL, headers, params, body).

Usage:
    python -m scrapers.dealer_spider.recon_oem bmw
    python -m scrapers.dealer_spider.recon_oem mercedes
    python -m scrapers.dealer_spider.recon_oem vw
"""
from __future__ import annotations

import asyncio
import json
import sys
from urllib.parse import urlparse, parse_qs

from playwright.async_api import async_playwright, Response as PWResponse


# ── Target URLs per OEM ──────────────────────────────────────────────────────

_OEM_TARGETS = {
    "bmw": [
        "https://www.bmw.de/de/topics/kaufen-leasen/bmw-gebrauchtwagen.html",
        "https://www.bmw.de/de/topics/kaufen-leasen/bmw-gebrauchtwagen/gebrauchtwagen-suche.html",
        "https://gebrauchte.bmw.de/",
        "https://www.bmw.de/gebrauchtwagen",
    ],
    "mercedes": [
        "https://www.mercedes-benz.de/passengercars/buy/used-car-search.html",
        "https://www.mercedes-benz.de/passengercars/mercedes-benz-certified/search.html",
    ],
    "vw": [
        "https://www.volkswagen.de/de/modelle-und-konfigurator/gebrauchtwagen.html",
        "https://www.volkswagen.de/de/kaufen-und-mieten/gebrauchtwagen.html",
    ],
    "audi": [
        "https://www.audi.de/de/web/de/models/layer/gebrauchtwagen.html",
        "https://plus.audi.de/de/search",
    ],
    "stellantis": [
        "https://www.spoticar.de/gebrauchtwagen",
        "https://www.spoticar.fr/voitures-occasion",
        "https://www.spoticar.es/coches-segunda-mano",
    ],
    "renault": [
        "https://www.renault.de/gebrauchtwagen.html",
        "https://occasion.renault.fr/",
    ],
}

# Skip these in XHR capture
_SKIP_DOMAINS = {
    "google-analytics", "googletagmanager", "facebook", "doubleclick",
    "hotjar", "segment", "mixpanel", "sentry", "datadog", "newrelic",
    "cookiebot", "onetrust", "consent", "cdn.optimizely", "bat.bing",
    "demdex", "omtrdc", "adobe", "tealium", "tags.", "gtm.",
}


async def _recon_oem(brand: str) -> None:
    urls = _OEM_TARGETS.get(brand)
    if not urls:
        print(f"Unknown brand: {brand}. Available: {', '.join(_OEM_TARGETS.keys())}")
        return

    print(f"\n{'='*80}")
    print(f"  OEM RECON: {brand.upper()}")
    print(f"{'='*80}\n")

    captured: list[dict] = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage",
                  "--disable-blink-features=AutomationControlled"],
        )
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            viewport={"width": 1920, "height": 1080},
            locale="de-DE",
            timezone_id="Europe/Berlin",
        )

        # Stealth patches
        await context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
            Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});
            if (!window.chrome) { window.chrome = {}; }
            if (!window.chrome.runtime) { window.chrome.runtime = {}; }
        """)

        page = await context.new_page()

        # Block non-essential resources
        await page.route("**/*", lambda route, request: (
            route.abort() if request.resource_type in ("image", "media", "font", "stylesheet")
            else route.continue_()
        ))

        async def _on_response(response: PWResponse) -> None:
            try:
                url = response.url
                ct = response.headers.get("content-type", "")

                # Skip tracking/analytics
                if any(skip in url.lower() for skip in _SKIP_DOMAINS):
                    return

                # Only JSON/JS responses
                if "json" not in ct and "javascript" not in ct:
                    return

                status = response.status
                if status != 200:
                    return

                body = await response.body()
                if len(body) < 500:
                    return

                # Try to parse as JSON
                try:
                    data = json.loads(body)
                except (json.JSONDecodeError, UnicodeDecodeError):
                    return

                # Check if this looks like vehicle data
                data_str = json.dumps(data)[:2000].lower()
                vehicle_signals = [
                    "vehicle", "car", "fahrzeug", "voiture", "model", "mileage",
                    "price", "preis", "kilomet", "brand", "make", "dealer",
                    "gebrauchtwagen", "occasion", "used", "listing", "offer",
                ]
                signal_count = sum(1 for s in vehicle_signals if s in data_str)
                if signal_count < 2:
                    return

                # Get request details
                request = response.request
                parsed = urlparse(url)
                query_params = parse_qs(parsed.query)

                entry = {
                    "url": url,
                    "method": request.method,
                    "status": status,
                    "content_type": ct,
                    "body_size": len(body),
                    "query_params": query_params,
                    "request_headers": dict(request.headers),
                    "response_headers": dict(response.headers),
                }

                # Try to get POST body
                try:
                    post_data = request.post_data
                    if post_data:
                        try:
                            entry["post_body"] = json.loads(post_data)
                        except (json.JSONDecodeError, TypeError):
                            entry["post_body_raw"] = post_data[:500]
                except Exception:
                    pass

                # Analyze JSON structure
                if isinstance(data, dict):
                    entry["response_top_keys"] = list(data.keys())[:20]
                    # Count items in array-like values
                    for k, v in data.items():
                        if isinstance(v, list) and len(v) > 0:
                            entry[f"array_key_{k}"] = len(v)
                            if isinstance(v[0], dict):
                                entry[f"item_keys_{k}"] = list(v[0].keys())[:15]
                    # Check nested data
                    if "data" in data and isinstance(data["data"], dict):
                        for k, v in data["data"].items():
                            if isinstance(v, list) and len(v) > 0:
                                entry[f"data.array_{k}"] = len(v)
                                if isinstance(v[0], dict):
                                    entry[f"data.item_keys_{k}"] = list(v[0].keys())[:15]
                elif isinstance(data, list):
                    entry["response_type"] = f"array[{len(data)}]"
                    if data and isinstance(data[0], dict):
                        entry["item_keys"] = list(data[0].keys())[:15]

                # Sample first item
                sample = None
                if isinstance(data, list) and data:
                    sample = data[0]
                elif isinstance(data, dict):
                    for k in ("results", "vehicles", "items", "data", "hits", "offers",
                              "searchResults", "content", "records"):
                        v = data.get(k)
                        if isinstance(v, list) and v and isinstance(v[0], dict):
                            sample = v[0]
                            break
                        if isinstance(v, dict):
                            for sk in ("results", "vehicles", "items"):
                                sv = v.get(sk)
                                if isinstance(sv, list) and sv and isinstance(sv[0], dict):
                                    sample = sv[0]
                                    break
                            if sample:
                                break

                if sample:
                    # Truncate long values for display
                    clean_sample = {}
                    for k, v in sample.items():
                        if isinstance(v, str) and len(v) > 100:
                            clean_sample[k] = v[:100] + "..."
                        elif isinstance(v, list) and len(v) > 3:
                            clean_sample[k] = v[:3]
                        elif isinstance(v, dict):
                            clean_sample[k] = {sk: sv for sk, sv in list(v.items())[:5]}
                        else:
                            clean_sample[k] = v
                    entry["sample_item"] = clean_sample

                captured.append(entry)

                print(f"\n  [CAPTURED] {request.method} {url[:120]}")
                print(f"  Content-Type: {ct}")
                print(f"  Body: {len(body)} bytes, signal_count={signal_count}")

            except Exception as exc:
                pass  # silent — we're passive observing

        page.on("response", _on_response)

        for url in urls:
            print(f"\n--- Navigating: {url}")
            try:
                await page.goto(url, wait_until="networkidle", timeout=30000)
                await asyncio.sleep(2)

                # Scroll to trigger lazy loading
                for _ in range(3):
                    await page.evaluate("window.scrollBy(0, 800)")
                    await asyncio.sleep(1.5)

                # Try clicking search/filter buttons to trigger API calls
                for selector in [
                    "button[type='submit']",
                    "[data-testid*='search']",
                    "[class*='search']",
                    "[class*='filter']",
                    "a[href*='search']",
                    "a[href*='suche']",
                    "button:has-text('Suchen')",
                    "button:has-text('Rechercher')",
                    "button:has-text('Buscar')",
                    "button:has-text('Fahrzeuge')",
                ]:
                    try:
                        el = await page.query_selector(selector)
                        if el and await el.is_visible():
                            await el.click()
                            await asyncio.sleep(3)
                            break
                    except Exception:
                        continue

                # Final scroll
                await page.evaluate("window.scrollBy(0, 2000)")
                await asyncio.sleep(2)

                # Check for iframes that might contain search
                iframes = await page.query_selector_all("iframe[src]")
                for iframe in iframes[:3]:
                    src = await iframe.get_attribute("src")
                    if src and any(kw in src.lower() for kw in ("search", "vehicle", "gebraucht", "occasion")):
                        print(f"  [IFRAME] {src}")

            except Exception as exc:
                print(f"  Navigation failed: {exc}")

        await browser.close()

    # ── Output Report ────────────────────────────────────────────────────
    print(f"\n\n{'='*80}")
    print(f"  RECON REPORT: {brand.upper()} — {len(captured)} API endpoints captured")
    print(f"{'='*80}\n")

    if not captured:
        print("  NO VEHICLE API ENDPOINTS DETECTED.")
        print("  The OEM likely uses:")
        print("  - Server-side rendering (no client-side XHR)")
        print("  - WebSocket/GraphQL subscriptions")
        print("  - Heavily obfuscated API with rotating tokens")
        print("  - Iframe-based third-party inventory widget")
        return

    for i, entry in enumerate(captured, 1):
        print(f"\n--- Endpoint #{i} ---")
        print(f"  URL:    {entry['url']}")
        print(f"  Method: {entry['method']}")
        print(f"  Status: {entry['status']}")
        print(f"  Size:   {entry['body_size']} bytes")

        if entry.get("query_params"):
            print(f"  Query Params:")
            for k, v in entry["query_params"].items():
                print(f"    {k} = {v}")

        if entry.get("post_body"):
            print(f"  POST Body:")
            print(f"    {json.dumps(entry['post_body'], indent=4)[:500]}")
        elif entry.get("post_body_raw"):
            print(f"  POST Body (raw): {entry['post_body_raw']}")

        # Key request headers (excluding standard browser ones)
        interesting_headers = {
            k: v for k, v in entry.get("request_headers", {}).items()
            if k.lower() in ("authorization", "x-api-key", "x-csrf-token",
                              "x-request-id", "x-client-id", "api-key",
                              "x-app-key", "x-auth-token", "cookie")
            or k.lower().startswith("x-")
        }
        if interesting_headers:
            print(f"  Auth/Custom Headers:")
            for k, v in interesting_headers.items():
                # Truncate cookie
                display_v = v[:80] + "..." if len(v) > 80 else v
                print(f"    {k}: {display_v}")

        if entry.get("response_top_keys"):
            print(f"  Response Keys: {entry['response_top_keys']}")

        for k, v in entry.items():
            if k.startswith("array_key_"):
                array_name = k.replace("array_key_", "")
                print(f"  Array '{array_name}': {v} items")
            if k.startswith("item_keys_"):
                array_name = k.replace("item_keys_", "")
                print(f"  Item fields in '{array_name}': {v}")
            if k.startswith("data.array_"):
                array_name = k.replace("data.array_", "")
                print(f"  data.{array_name}: {v} items")
            if k.startswith("data.item_keys_"):
                array_name = k.replace("data.item_keys_", "")
                print(f"  Item fields in data.{array_name}: {v}")

        if entry.get("sample_item"):
            print(f"  Sample Item:")
            print(f"    {json.dumps(entry['sample_item'], indent=4, ensure_ascii=False)[:1000]}")

    print(f"\n{'='*80}")
    print(f"  END RECON: {brand.upper()}")
    print(f"{'='*80}\n")


if __name__ == "__main__":
    brand = sys.argv[1] if len(sys.argv) > 1 else "bmw"
    asyncio.run(_recon_oem(brand))
