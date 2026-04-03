"""
DMS Platform Detector — fingerprints a dealer website to determine which
Dealer Management System (DMS) or inventory platform they use.

Returns one of:
    "autobiz"          — Autobiz SaaS (FR/BE/ES, ~40k dealers)
    "autentia"         — Autentia/Izmo (ES, ~15k dealers)
    "incadea"          — Incadea/CDK Global (DE/AT/CH/NL)
    "motormanager"     — Motormanager (NL/BE)
    "wp_car_manager"   — WordPress + WP Car Manager plugin
    "dealer_inspire"   — Dealer Inspire / Cars.com dealer sites
    "automanager"      — AutoManager WebManager (US/EU)
    "generic_feed"     — Site exposes /api/stock.json or /vehicles.xml
    "schema_org"       — Site uses JSON-LD schema.org/Car markup
    "generic_html"     — Fallback: parse HTML listing pages
    None               — Cannot determine / no inventory found
"""
from __future__ import annotations

import re
from typing import Optional
from urllib.parse import urljoin, urlparse

# ── Fingerprint signatures ─────────────────────────────────────────────────────

# (pattern_in_html, platform_id)
_HTML_SIGNATURES: list[tuple[re.Pattern, str]] = [
    # Autobiz — widely used in FR, BE, ES
    (re.compile(r"autobiz\.com|autobiz-group\.com|autobizinterface", re.I), "autobiz"),
    (re.compile(r"ab-data\.autobiz|api\.autobiz", re.I), "autobiz"),
    # Autentia / Izmo — dominant in ES
    (re.compile(r"autentia\.com|izmostock|izmo\.com", re.I), "autentia"),
    (re.compile(r"autentia-motors|motorstock\.autentia", re.I), "autentia"),
    # Incadea / CDK Global — DE, AT, CH, NL
    (re.compile(r"incadea\.com|cdkglobal\.com|incadea-group", re.I), "incadea"),
    (re.compile(r"cdkdrive\.com|driveone\.cdkglobal", re.I), "incadea"),
    # Motormanager — NL/BE
    (re.compile(r"motormanager\.nl|motormanager\.eu|mminterface", re.I), "motormanager"),
    # WP Car Manager (WordPress plugin)
    (re.compile(r"wp-car-manager|wpcm|class=['\"]wpcm-listing", re.I), "wp_car_manager"),
    (re.compile(r"/wp-content/plugins/wp-car-manager", re.I), "wp_car_manager"),
    # Dealer Inspire / Cars.com
    (re.compile(r"dealerinspire\.com|dealersite\.cars\.com", re.I), "dealer_inspire"),
    # AutoManager WebManager
    (re.compile(r"automanager\.biz|webmanagerusa|amdealer", re.I), "automanager"),
    # DealerSocket / VinSolutions
    (re.compile(r"dealersocket\.com|vinsolutions\.com", re.I), "dealersocket"),
    # JSON-LD schema.org/Car
    (re.compile(r'"@type"\s*:\s*"Car"', re.I), "schema_org"),
    (re.compile(r'"@type"\s*:\s*"Vehicle"', re.I), "schema_org"),
]

# Known JSON feed paths to probe
_FEED_PATHS = [
    "/api/stock.json",
    "/api/vehicles.json",
    "/api/inventory.json",
    "/inventory.json",
    "/stock.json",
    "/vehicles.json",
    "/coches.json",
    "/fahrzeuge.json",
    "/voitures.json",
    "/api/cars.json",
    "/wp-json/wp/v2/car",           # WP Car Manager REST API
    "/api/v1/vehicles",
    "/api/v2/vehicles",
    "/feed/vehicles",
    "/vehicle-feed.xml",
    "/sitemap-vehicles.xml",
    "/sitemap_vehicles.xml",
    "/inventory.xml",
]

# Known inventory URL path patterns (regex against full URL)
_INVENTORY_PATH_PATTERNS = [
    re.compile(r"/(stock|inventory|coches|fahrzeuge|voitures|occasion|gebrauchtwagen|tweedehands|usados|coches-ocasion|angebote)", re.I),
    re.compile(r"/(cars|autos|vehicles|fleet|katalog)", re.I),
]


class DMSDetector:
    """
    Given a dealer's homepage HTML and base URL, returns the DMS platform string.
    Also probes for JSON/XML feed paths via HEAD requests.
    """

    def __init__(self, http_client):
        self.http = http_client

    async def detect(self, base_url: str, html: str) -> tuple[str, Optional[str]]:
        """
        Returns (platform, feed_url_or_None).
        feed_url is set when a JSON/XML feed is directly accessible.
        """
        # 1. HTML fingerprint
        for pattern, platform in _HTML_SIGNATURES:
            if pattern.search(html):
                return platform, None

        # 2. Probe known feed paths
        base = base_url.rstrip("/")
        for path in _FEED_PATHS:
            feed_url = base + path
            try:
                ok = await self.http.head_ok(feed_url)
                if ok:
                    return "generic_feed", feed_url
            except Exception:
                continue

        # 3. Detect inventory page links in HTML
        for pattern in _INVENTORY_PATH_PATTERNS:
            if pattern.search(html):
                return "generic_html", None

        # 4. Check for JSON-LD in page (may not have fired in regex if whitespace)
        if "schema.org" in html and ("Car" in html or "Vehicle" in html):
            return "schema_org", None

        return "generic_html", None

    @staticmethod
    def find_inventory_links(base_url: str, html: str) -> list[str]:
        """Extract candidate inventory page URLs from dealer homepage."""
        domain = urlparse(base_url).netloc
        found = []

        # Find all hrefs
        for m in re.finditer(r'href=["\']([^"\']+)["\']', html, re.I):
            href = m.group(1)
            if not href.startswith("http"):
                href = urljoin(base_url, href)
            # Only same-domain links
            if urlparse(href).netloc != domain:
                continue
            path = urlparse(href).path.lower()
            for pat in _INVENTORY_PATH_PATTERNS:
                if pat.search(path):
                    found.append(href)
                    break

        return list(dict.fromkeys(found))  # deduplicate preserving order
