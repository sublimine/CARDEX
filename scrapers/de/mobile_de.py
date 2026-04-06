"""
mobile.de Germany — EXHAUSTIVE scraper.

Query decomposition: make × year
  Iterates ALL pages per (make, year) until platform returns empty page.
  No artificial page cap.

Uses Playwright for initial page loads to bypass Cloudflare JS challenge.
After the first successful render, the cf_clearance cookie is extracted
and reused via the HTTP client for faster subsequent requests.

Falls back to Playwright rendering if the HTTP client gets blocked again.
"""
from __future__ import annotations

import json
import re
from typing import AsyncGenerator

import structlog

from ..common.base_scraper import BaseScraper
from ..common.models import RawListing
from ..common.normalizer import (
    normalize_fuel,
    normalize_transmission,
    parse_co2,
    parse_mileage,
    parse_power_kw,
    parse_price,
)

log = structlog.get_logger()

_PAGE_SIZE = 50
_SEARCH_URL = (
    "https://suchen.mobile.de/fahrzeuge/search.html"
    "?isSearchRequest=true"
    "&sortOption.sortBy=creationTime"
    "&sortOption.sortOrder=DESCENDING"
    "&pageNumber={page}"
    "&pageSize={page_size}"
    "&minFirstRegistrationDate={year}-01-01"
    "&maxFirstRegistrationDate={year}-12-31"
    "&makeModelVariant1.makeId={make_id}"
    "&damageUnrepaired=WITHOUT_DAMAGE_UNREPAIRED"
)

# mobile.de numeric make IDs (subset — full list fetched dynamically at startup)
# These are the static IDs for common makes. The scraper fetches the full map.
_STATIC_MAKE_IDS: dict[str, str] = {
    "Abarth": "25200", "Alfa Romeo": "1900", "Audi": "1900",
    "BMW": "3500", "Chevrolet": "3600", "Chrysler": "3700",
    "Citroën": "3800", "Cupra": "25100", "Dacia": "4000",
    "DS": "25000", "Fiat": "5200", "Ford": "5400",
    "Honda": "6200", "Hyundai": "6400", "Infiniti": "6500",
    "Jaguar": "7000", "Jeep": "7100", "Kia": "7300",
    "Lada": "7500", "Land Rover": "7700", "Lexus": "7900",
    "Maserati": "8400", "Mazda": "8500", "Mercedes-Benz": "8600",
    "MG": "23600", "MINI": "15900", "Mitsubishi": "9000",
    "Nissan": "9400", "Opel": "9600", "Peugeot": "10000",
    "Porsche": "10300", "Renault": "10400", "Saab": "10600",
    "SEAT": "10700", "Skoda": "10900", "Smart": "11000",
    "SsangYong": "11100", "Subaru": "11200", "Suzuki": "11300",
    "Tesla": "24100", "Toyota": "11600", "Volkswagen": "12300",
    "Volvo": "12500", "BYD": "25300", "Polestar": "25500",
}


class MobileDe(BaseScraper):
    platform = "mobile_de"
    country = "DE"
    domain = "suchen.mobile.de"
    use_playwright = True
    _make_id_map: dict[str, str] = {}
    _cf_cookie_injected: bool = False

    def __init__(self) -> None:
        super().__init__()
        # Playwright renders are ~3-5s each; keep rate conservative to avoid
        # triggering Cloudflare rate-based blocks on top of the JS challenge.
        self.http.rate_limiter.rps = 0.15

    # ------------------------------------------------------------------
    # Cloudflare bypass helpers
    # ------------------------------------------------------------------

    async def _inject_cf_cookie(self) -> bool:
        """
        Extract cf_clearance cookie from Playwright browser context and
        inject it into the HTTP client for faster subsequent requests.
        Returns True if a cookie was found and injected.
        """
        if not self.playwright:
            return False
        try:
            cf_cookie = await self.playwright.get_cookie("cf_clearance")
            if cf_cookie and self.http._client:
                self.http._client.cookies.set(
                    cf_cookie["name"],
                    cf_cookie["value"],
                    domain=cf_cookie.get("domain", ".mobile.de"),
                )
                self._cf_cookie_injected = True
                self.log.info("mobile_de.cf_cookie_injected", domain=cf_cookie.get("domain"))
                return True
        except Exception as e:
            self.log.debug("mobile_de.cf_cookie_extract_failed", error=str(e))
        return False

    async def _fetch_with_playwright(self, url: str) -> str | None:
        """
        Render a page via Playwright. Returns raw HTML or None on failure.
        After first successful render, injects cf_clearance into HTTP client.
        """
        if not self.playwright:
            return None
        try:
            html = await self.playwright.get_page_content(
                url,
                wait_for=".result-item, .cBox-body--resultitem, .cBox-body--eyeCatcher, script#__NEXT_DATA__",
                timeout=45_000,
            )
            # Inject cf_clearance cookie into HTTP client after first success
            if not self._cf_cookie_injected:
                await self._inject_cf_cookie()
            return html
        except Exception as e:
            self.log.warning("mobile_de.playwright_error", url=url, error=str(e))
            return None

    async def _fetch_with_http(self, url: str) -> dict | None:
        """
        Try fetching JSON via plain HTTP (fast path, works once cf_clearance is set).
        Returns parsed JSON dict or None if blocked.
        """
        try:
            data = await self.http.get_json(
                url,
                headers={
                    "Accept": "application/json",
                    "Accept-Language": "de-DE,de;q=0.9",
                    "Referer": "https://suchen.mobile.de/",
                },
            )
            return data
        except Exception as e:
            err_str = str(e).lower()
            if "403" in err_str or "cloudflare" in err_str or "blocked" in err_str:
                self.log.debug("mobile_de.http_blocked", url=url)
                self._cf_cookie_injected = False  # cookie expired, reset
            else:
                self.log.warning("mobile_de.http_error", url=url, error=str(e))
            return None

    # ------------------------------------------------------------------
    # HTML parsing (for Playwright-rendered pages)
    # ------------------------------------------------------------------

    def _extract_items_from_html(self, html: str) -> list[dict]:
        """
        Parse vehicle listings from rendered HTML.
        Tries __NEXT_DATA__ JSON first, falls back to embedded JSON-LD / DOM parsing.
        """
        # Strategy 1: __NEXT_DATA__ JSON blob (Next.js SSR)
        next_data_match = re.search(
            r'<script\s+id="__NEXT_DATA__"\s+type="application/json">(.*?)</script>',
            html,
            re.DOTALL,
        )
        if next_data_match:
            try:
                nd = json.loads(next_data_match.group(1))
                props = nd.get("props", {}).get("pageProps", {})
                items = (
                    props.get("items")
                    or props.get("results")
                    or props.get("searchResult", {}).get("items")
                    or props.get("searchResult", {}).get("results")
                    or []
                )
                if items:
                    return items
            except (json.JSONDecodeError, KeyError):
                pass

        # Strategy 2: Inline JSON search result object
        # mobile.de sometimes embeds search data in a <script> tag
        json_match = re.search(
            r'"searchResult"\s*:\s*(\{.*?"items"\s*:\s*\[.*?\]\s*\})',
            html,
            re.DOTALL,
        )
        if json_match:
            try:
                sr = json.loads(json_match.group(1))
                items = sr.get("items") or sr.get("results") or []
                if items:
                    return items
            except (json.JSONDecodeError, KeyError):
                pass

        # Strategy 3: window.__INITIAL_STATE__ or similar
        init_match = re.search(
            r'window\.__INITIAL_STATE__\s*=\s*({.*?});?\s*</script>',
            html,
            re.DOTALL,
        )
        if init_match:
            try:
                state = json.loads(init_match.group(1))
                # Navigate nested structures to find items
                for key in ("search", "searchResult", "listing", "results"):
                    if key in state:
                        candidate = state[key]
                        if isinstance(candidate, dict):
                            items = candidate.get("items") or candidate.get("results") or []
                            if items:
                                return items
                        elif isinstance(candidate, list):
                            return candidate
            except (json.JSONDecodeError, KeyError):
                pass

        return []

    def _extract_total_pages_from_html(self, html: str) -> int:
        """Extract total page count from rendered HTML."""
        # From __NEXT_DATA__
        next_data_match = re.search(
            r'<script\s+id="__NEXT_DATA__"\s+type="application/json">(.*?)</script>',
            html,
            re.DOTALL,
        )
        if next_data_match:
            try:
                nd = json.loads(next_data_match.group(1))
                props = nd.get("props", {}).get("pageProps", {})
                tp = (
                    props.get("totalPages")
                    or props.get("pagination", {}).get("totalPages")
                    or props.get("searchResult", {}).get("totalPages")
                    or (props.get("searchResult", {}).get("pagination") or {}).get("totalPages")
                )
                if tp:
                    return int(tp)
            except (json.JSONDecodeError, KeyError, TypeError):
                pass
        # Fallback: look for pagination element with max page number
        page_nums = re.findall(r'pageNumber=(\d+)', html)
        if page_nums:
            return max(int(p) for p in page_nums)
        return 1

    # ------------------------------------------------------------------
    # Make ID resolution
    # ------------------------------------------------------------------

    async def _ensure_make_ids(self) -> None:
        """Fetch complete make list from mobile.de (runs once at startup)."""
        if self._make_id_map:
            return
        # Start with static map; try dynamic fetch for full coverage
        self._make_id_map = dict(_STATIC_MAKE_IDS)
        try:
            data = await self._fetch_with_http(
                "https://suchen.mobile.de/fahrzeuge/search.html"
                "?isSearchRequest=true&makeModelVariant1.makeId="
            )
            if data:
                for make_entry in (data.get("makes") or []):
                    make_id = str(make_entry.get("id") or make_entry.get("makeId", ""))
                    make_name = make_entry.get("name") or make_entry.get("makeName", "")
                    if make_id and make_name:
                        self._make_id_map[make_name] = make_id
        except Exception:
            pass  # use static map

    # ------------------------------------------------------------------
    # Main crawl loop
    # ------------------------------------------------------------------

    async def crawl_shard(self, make: str, year: int) -> AsyncGenerator[RawListing, None]:
        await self._ensure_make_ids()
        make_id = self._make_id_map.get(make)
        if not make_id:
            return

        cursor = await self.get_shard_cursor(make, year)
        new_cursor: str | None = None
        page = 1

        while True:
            url = _SEARCH_URL.format(
                page=page,
                page_size=_PAGE_SIZE,
                year=year,
                make_id=make_id,
            )

            items: list[dict] = []
            total_pages: int = 1

            # Fast path: try HTTP with cf_clearance cookie
            if self._cf_cookie_injected:
                data = await self._fetch_with_http(url)
                if data:
                    items = data.get("items") or data.get("results") or []
                    total_pages = (
                        data.get("totalPages")
                        or (data.get("pagination") or {}).get("totalPages", 1)
                    )

            # Slow path: Playwright rendering (first request or after cookie expiry)
            if not items:
                html = await self._fetch_with_playwright(url)
                if html is None:
                    # Playwright failed entirely — mark shard as failed, move on
                    self.log.warning(
                        "mobile_de.shard_fetch_failed",
                        make=make, year=year, page=page,
                    )
                    break

                items = self._extract_items_from_html(html)
                total_pages = self._extract_total_pages_from_html(html)

                if not items:
                    # Page rendered but no items found — end of results
                    break

            cursor_hit = False
            for item in items:
                listing = self._map(item)
                if not listing:
                    continue
                lid = listing.source_listing_id
                if new_cursor is None:
                    new_cursor = lid
                if cursor and lid == cursor:
                    cursor_hit = True
                    break
                yield listing

            if cursor_hit:
                break

            if page >= total_pages or len(items) < _PAGE_SIZE:
                break
            page += 1

        if new_cursor:
            await self.save_shard_cursor(make, year, new_cursor)

    def _map(self, item: dict) -> RawListing | None:
        try:
            listing_id = str(item.get("id", ""))
            if not listing_id:
                return None

            url = item.get("relativeUrl") or item.get("url") or ""
            if not url.startswith("http"):
                url = f"https://suchen.mobile.de{url}"

            attrs = item.get("attributes") or {}
            price_info = item.get("price") or {}
            raw_price = price_info.get("amountInEuro") or price_info.get("grossAmount")
            if raw_price is None:
                raw_price = parse_price(str(price_info.get("displayPrice", "")))

            images = item.get("images") or []
            photos = [img.get("uri") or img.get("url", "") for img in images if (img.get("uri") or img.get("url"))]
            location = item.get("location") or (item.get("seller") or {}).get("address") or {}

            return RawListing(
                source_platform=self.platform,
                source_country=self.country,
                source_url=url,
                source_listing_id=listing_id,
                make=item.get("make") or attrs.get("make"),
                model=item.get("model") or attrs.get("model"),
                variant=item.get("modelDescription") or attrs.get("modelDescription"),
                year=item.get("firstRegistrationYear") or attrs.get("firstRegistrationYear"),
                mileage_km=attrs.get("mileageInKm") or parse_mileage(str(attrs.get("mileage", ""))),
                fuel_type=normalize_fuel(attrs.get("fuelType") or attrs.get("fuelTypeText")),
                transmission=normalize_transmission(attrs.get("transmission") or attrs.get("transmissionText")),
                color=attrs.get("color") or attrs.get("colorText"),
                power_kw=parse_power_kw(attrs.get("power")),
                co2_gkm=parse_co2(attrs.get("co2Emission")),
                price_raw=float(raw_price) if raw_price else None,
                currency_raw="EUR",
                city=location.get("city") or location.get("locality"),
                region=location.get("region"),
                country="DE",
                seller_type="DEALER" if (item.get("sellerType") or "").upper() == "DEALER" else "PRIVATE",
                seller_name=(item.get("seller") or {}).get("name"),
                photo_urls=photos[:20],
                thumbnail_url=photos[0] if photos else None,
                listing_status="ACTIVE",
                description_snippet=(item.get("description") or "")[:300],
            )
        except Exception as e:
            self.log.warning("mobile_de.map_error", error=str(e), item_id=item.get("id"))
            return None


async def run() -> None:
    await MobileDe().run()
