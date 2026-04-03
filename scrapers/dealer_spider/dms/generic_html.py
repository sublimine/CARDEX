"""
Generic HTML fallback extractor — last resort when no DMS adapter or structured
feed is available. Uses heuristic scraping of the dealer's inventory listing page.

Strategy (in order of confidence):
  1. Meta tags: og:title, og:description, og:price:amount
  2. Microdata (itemscope/itemtype=Vehicle|Car) — schema.org in HTML attributes
  3. Pattern matching on page text: price patterns, mileage patterns
  4. Common CSS class patterns used by generic CMS car plugins

This adapter intentionally has lower precision than structured adapters;
it's intended as a coverage layer, not a primary data source.

Requires: beautifulsoup4 (bs4) — installed in scraper container.
"""
from __future__ import annotations

import re
from typing import AsyncGenerator

from scrapers.common.models import RawListing
from scrapers.dealer_spider.dms.generic_feed import _parse_price, _parse_km

# Patterns for price extraction from page text
_PRICE_PATTERN = re.compile(
    r'(?:€|EUR|CHF|£|GBP)\s*([0-9][0-9.,\s]{2,9})'
    r'|([0-9][0-9.,\s]{2,9})\s*(?:€|EUR|CHF|£)',
    re.IGNORECASE,
)
_MILEAGE_PATTERN = re.compile(
    r'([0-9][0-9.,\s]{1,8})\s*km\b',
    re.IGNORECASE,
)
_YEAR_PATTERN = re.compile(r'\b(19[5-9]\d|20[0-2]\d)\b')

# Common CSS class / HTML ID patterns used by car CMS plugins
_PRICE_SELECTORS = [
    ".car-price", ".vehicle-price", ".listing-price", ".price",
    "[class*='price']", "[itemprop='price']", "[data-price]",
    ".coch-price", ".auto-price", ".fahrzeug-preis",
]
_TITLE_SELECTORS = [
    "h1", ".car-title", ".vehicle-title", ".listing-title",
    "[itemprop='name']", ".car-name", ".auto-title", "title",
]
_MILEAGE_SELECTORS = [
    ".mileage", ".km", ".kilometers", "[itemprop='mileageFromOdometer']",
    "[class*='mileage']", "[class*='kilomet']", ".laufleistung", ".kilómetros",
]
_IMAGE_SELECTORS = [
    "[itemprop='image']", ".car-image img", ".vehicle-image img",
    ".listing-image img", ".car-photo img", ".gallery img",
    "meta[property='og:image']",
]

# Inventory listing page paths
_INVENTORY_PATHS = [
    "/stock", "/inventory", "/vehicles", "/cars", "/used-cars",
    "/coches", "/fahrzeuge", "/voitures", "/occasion", "/gebrauchtwagen",
    "/tweedehands", "/occasions", "/usato", "/ocasion",
]


def _try_import_bs4():
    try:
        from bs4 import BeautifulSoup
        return BeautifulSoup
    except ImportError:
        return None


def _extract_text(soup, selectors: list[str]) -> str | None:
    """Try each selector, return first non-empty text."""
    for sel in selectors:
        try:
            el = soup.select_one(sel)
            if el:
                # For meta tags return content attribute
                content = el.get("content") or el.get_text(separator=" ", strip=True)
                if content and len(content.strip()) > 1:
                    return content.strip()
        except Exception:
            continue
    return None


def _extract_og_meta(soup) -> dict:
    """Extract Open Graph meta tags."""
    meta = {}
    for tag in soup.find_all("meta", attrs={"property": True}):
        prop = tag.get("property", "")
        content = tag.get("content", "")
        if prop.startswith("og:") and content:
            meta[prop[3:]] = content  # strip "og:" prefix
    return meta


def _extract_microdata_vehicles(soup, dealer_id: str, dealer_name: str, base_url: str, country: str) -> list[RawListing]:
    """Extract schema.org microdata (itemscope/itemtype) from HTML."""
    listings = []
    vehicle_types = {"vehicle", "car", "automobile", "product"}

    items = soup.find_all(attrs={"itemscope": True})
    for item in items:
        itype = (item.get("itemtype") or "").lower()
        if not any(v in itype for v in vehicle_types):
            continue

        def _itemprop(name: str) -> str | None:
            el = item.find(attrs={"itemprop": name})
            if el is None:
                return None
            return el.get("content") or el.get("value") or el.get_text(strip=True) or None

        vid = _itemprop("productID") or _itemprop("sku") or _itemprop("vehicleIdentificationNumber")
        if not vid:
            url_el = item.find("a")
            if url_el:
                vid = url_el.get("href", "").split("/")[-1]
        if not vid:
            continue

        name = _itemprop("name") or ""
        # Try to split name into make/model: "BMW 3 Series" → "BMW", "3 Series"
        parts = name.split(None, 1)
        make = parts[0] if parts else ""
        model = parts[1] if len(parts) > 1 else ""

        price = _parse_price(_itemprop("price"), country)
        mileage = _extract_mileage_from_text(_itemprop("mileageFromOdometer") or "")
        year_s = _itemprop("vehicleModelDate") or _itemprop("dateVehicleFirstRegistered") or ""
        year = int(year_s[:4]) if year_s[:4].isdigit() else None
        vin = _itemprop("vehicleIdentificationNumber")

        img_el = item.find(attrs={"itemprop": "image"})
        thumb = None
        if img_el:
            thumb = img_el.get("src") or img_el.get("content") or img_el.get("href")

        source_url = base_url
        a = item.find("a")
        if a and a.get("href", "").startswith("http"):
            source_url = a["href"]
        elif a and a.get("href", "").startswith("/"):
            source_url = base_url.rstrip("/") + a["href"]

        try:
            listing = RawListing(
                source_platform=f"dealer_web:{dealer_id}",
                source_country=country,
                source_listing_id=f"html:{dealer_id}:{vid}",
                source_url=source_url,
                make=make, model=model, year=year,
                price_raw=price, mileage_km=mileage,
                vin=vin, thumbnail_url=thumb,
                seller_name=dealer_name,
                seller_type="DEALER",
            )
            listings.append(listing)
        except Exception:
            continue

    return listings


def _extract_mileage_from_text(text: str) -> int | None:
    if not text:
        return None
    m = _MILEAGE_PATTERN.search(text)
    if m:
        return _parse_km(m.group(1))
    return _parse_km(text)


def _extract_listing_links(soup, base_url: str) -> list[str]:
    """Find links on a listing-overview page that look like individual car detail pages."""
    links = []
    seen = set()
    vehicle_path_re = re.compile(
        r'/(stock|inventory|vehicle|car|auto|fahrzeug|voiture|coche|'
        r'occasion|gebrauchtwagen|tweedehands|used)/[^"\'?\s]+',
        re.IGNORECASE,
    )
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if vehicle_path_re.search(href):
            if href.startswith("http"):
                url = href
            elif href.startswith("/"):
                url = base_url.rstrip("/") + href
            else:
                continue
            if url not in seen:
                seen.add(url)
                links.append(url)
    return links[:100]  # cap


async def extract(
    http,
    dealer_id: str,
    dealer_name: str,
    base_url: str,
    country: str,
) -> AsyncGenerator[RawListing, None]:
    """
    HTML fallback extractor. Attempts microdata extraction on the inventory
    listing page, then falls back to individual detail pages.
    """
    BS4 = _try_import_bs4()
    if BS4 is None:
        return  # bs4 not installed — skip silently

    base = base_url.rstrip("/")
    seen_ids: set[str] = set()

    async def _process_html(html: str, page_url: str) -> list[RawListing]:
        soup = BS4(html, "html.parser")
        listings = []

        # Try microdata first (most reliable)
        listings.extend(_extract_microdata_vehicles(soup, dealer_id, dealer_name, page_url, country))
        if listings:
            return listings

        # Try OG meta for a single listing detail page
        og = _extract_og_meta(soup)
        og_title = og.get("title", "")
        og_price = og.get("price:amount") or og.get("product:price:amount")
        og_image = og.get("image")

        if og_price and og_title:
            parts = og_title.split(None, 1)
            make = parts[0] if parts else ""
            model = parts[1] if len(parts) > 1 else ""

            # Extract year from title
            year_m = _YEAR_PATTERN.search(og_title)
            year = int(year_m.group(1)) if year_m else None

            # Extract mileage from page text
            page_text = soup.get_text(separator=" ", limit=5000)
            km_m = _MILEAGE_PATTERN.search(page_text)
            mileage = _parse_km(km_m.group(1)) if km_m else None

            price = _parse_price(og_price, country)
            vid = page_url.split("/")[-1] or og_title[:20].replace(" ", "-").lower()

            try:
                listings.append(RawListing(
                    source_platform=f"dealer_web:{dealer_id}",
                    source_country=country,
                    source_listing_id=f"html:{dealer_id}:{vid}",
                    source_url=page_url,
                    make=make, model=model, year=year,
                    price_raw=price, mileage_km=mileage,
                    thumbnail_url=og_image if (og_image and og_image.startswith("http")) else None,
                    seller_name=dealer_name,
                    seller_type="DEALER",
                ))
            except Exception:
                pass

        return listings

    # 1. Probe inventory listing pages
    inventory_html = None
    inventory_url = base
    for path in _INVENTORY_PATHS:
        try:
            html = await http.get_text(base + path)
            listings = await _process_html(html, base + path)
            if listings:
                for l in listings:
                    if l.source_listing_id not in seen_ids:
                        seen_ids.add(l.source_listing_id)
                        yield l
                return
            # No direct listings, but save HTML to crawl detail links
            if not inventory_html:
                inventory_html = html
                inventory_url = base + path
        except Exception:
            continue

    # 2. Follow individual detail page links from the inventory page
    if inventory_html:
        try:
            soup = BS4(inventory_html, "html.parser")
            detail_links = _extract_listing_links(soup, base)
            found = 0
            for url in detail_links:
                try:
                    html = await http.get_text(url)
                    listings = await _process_html(html, url)
                    for l in listings:
                        if l.source_listing_id not in seen_ids:
                            seen_ids.add(l.source_listing_id)
                            found += 1
                            yield l
                except Exception:
                    continue
            if found > 0:
                return
        except Exception:
            pass

    # 3. Last resort: try homepage
    try:
        html = await http.get_text(base)
        listings = await _process_html(html, base)
        for l in listings:
            if l.source_listing_id not in seen_ids:
                seen_ids.add(l.source_listing_id)
                yield l
    except Exception:
        pass
