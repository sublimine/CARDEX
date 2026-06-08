"""
Generic dealer extractor — the T3 long-tail path that works on ANY dealer site.

Where portal scrapers (portals/base.py) know one marketplace's URL scheme, this
module knows none: given only a dealer's base URL and an injected async fetcher,
it discovers listing detail URLs and turns each into a canonical VehicleRecord by
running the already-verified per-page cascade:

    discover  →  fetch  →  parse_listing  →  to_record  →  evaluate

Discovery has two independent, verified strategies that union together:

  * SITEMAP    robots.txt `Sitemap:` directives + standard fallback paths,
               recursively expanding <sitemapindex>/<urlset>, filtered to the
               verified vehicle-path tokens (INTEL.md §E03). Works for any CMS.
  * WP-REST    `/wp-json/wp/v2/types` → vehicle custom-post-types → paginated
               item `link`s. Covers WordPress dealers (~40% of EU) that ship no
               vehicle sitemap.

Nothing here is portal-specific or invented: extraction reuses pipeline.parse
(schema.org / Open Graph / verified heuristics) and the canonical
pipeline.normalize + pipeline.quality contract. The network transport is
injected (`Fetcher`) so the orchestration is pure and unit-testable against
in-memory fixtures — no curl_cffi, httpx, Postgres or Meili in the hot path.
"""
from __future__ import annotations

import gzip
import json
import logging
from dataclasses import dataclass
from html import unescape
from typing import Any, Awaitable, Callable
import re
from urllib.parse import urljoin, urlparse

from scrapers.common.net_guard import is_safe_public_url
from scrapers.pipeline.delta import is_deep_link
from scrapers.pipeline.normalize import to_record
from scrapers.pipeline.parse import parse_jsonld, parse_listing, parse_og_meta
from scrapers.pipeline.quality import evaluate
from scrapers.pipeline.schema import VehicleRecord

log = logging.getLogger(__name__)


# ── injected transport ────────────────────────────────────────────────────────
@dataclass(frozen=True)
class FetchResult:
    """One HTTP response. `url` is the final URL after redirects; `body` raw bytes."""

    url: str
    status_code: int
    body: bytes

    @property
    def text(self) -> str:
        """UTF-8 decode of the body, replacing undecodable bytes (never raises)."""
        return self.body.decode("utf-8", errors="replace")


# A Fetcher takes an absolute URL and resolves to a FetchResult. Implementations
# wrap curl_cffi / httpx / Camoufox; tests pass an in-memory map. It must not
# raise for ordinary HTTP errors (return the status) — only for transport faults.
Fetcher = Callable[[str], Awaitable[FetchResult]]


# ── verified discovery constants ──────────────────────────────────────────────
# Vehicle path tokens — INTEL.md §E03 (vehicle/auto/voiture/coche/fahrzeug/
# gebrauchtwagen/annonce/occasion) plus the WP-REST CPT slugs already used by
# discovery/wp_rest_harvester.py. No token is invented; every one is present in
# the repo's verified extraction intel.
_VEHICLE_PATH_TOKENS: tuple[str, ...] = (
    "vehicles", "vehicle", "voitures", "voiture", "coches", "coche",
    "autos", "auto", "fahrzeuge", "fahrzeug", "gebrauchtwagen",
    "annonces", "annonce", "occasions", "occasion", "anuncios", "anuncio",
    "vehicules", "vehicule", "cars", "car", "stock", "inventory",
)
# Match a token as a whole path segment boundary: /vehicles/…, /auto-…, …/coche.
_VEHICLE_PATH_RE = re.compile(
    r"/(?:" + "|".join(_VEHICLE_PATH_TOKENS) + r")(?:[/_-]|$)",
    re.IGNORECASE,
)

# Standard sitemap locations — sitemap_resolver fallbacks + INTEL.md §E03 vehicle
# sitemap names. Probed after robots.txt; non-existent ones simply fail to expand.
_SITEMAP_FALLBACKS: tuple[str, ...] = (
    "/sitemap.xml",
    "/sitemap_index.xml",
    "/sitemap-index.xml",
    "/sitemap-vehicles.xml",
    "/sitemap-cars.xml",
    "/sitemap-inventory.xml",
    "/sitemap.xml.gz",
)

# WordPress vehicle custom-post-type slug hints (verbatim from wp_rest_harvester).
_WP_CPT_HINTS: tuple[str, ...] = (
    "vehicle", "vehicles", "voiture", "voitures", "coche", "coches",
    "auto", "autos", "car", "cars", "fahrzeug", "fahrzeuge",
    "occasion", "occasions", "listing", "stock", "inventory",
    "vehicule", "vehicules", "annonce", "annonces", "anuncio", "anuncios",
)

_ROBOTS_SITEMAP_RE = re.compile(r"(?im)^\s*sitemap\s*:\s*(\S+)\s*$")
_LOC_RE = re.compile(r"<loc>\s*(.*?)\s*</loc>", re.IGNORECASE | re.DOTALL)
_SITEMAPINDEX_RE = re.compile(r"<sitemapindex", re.IGNORECASE)
_URLSET_RE = re.compile(r"<urlset", re.IGNORECASE)

# Bounds — keep one dealer's crawl finite even on a misconfigured giant sitemap.
_MAX_SITEMAPS = 100
_MAX_URLS = 5_000
_WP_PER_PAGE = 100
_WP_MAX_PAGES = 50


# ── pure helpers (no I/O) ──────────────────────────────────────────────────────
def _origin(url: str) -> str:
    """Scheme://host[:port] for a URL, defaulting to https when scheme is absent."""
    parsed = urlparse(url if "://" in url else f"https://{url}")
    scheme = parsed.scheme or "https"
    return f"{scheme}://{parsed.netloc}"


def _host(url: str) -> str:
    """Bare hostname without a leading www., lowercased — the source_domain."""
    netloc = urlparse(url if "://" in url else f"https://{url}").netloc.lower()
    host = netloc.split("@")[-1].split(":")[0]
    return host[4:] if host.startswith("www.") else host


def _same_site(url: str, base_host: str) -> bool:
    """True when `url`'s host equals or is a subdomain of the dealer's base host."""
    host = _host(url)
    return host == base_host or host.endswith("." + base_host)


def looks_like_listing(url: str) -> bool:
    """True when the URL path carries a verified vehicle token (§E03)."""
    return bool(_VEHICLE_PATH_RE.search(urlparse(url).path))


def parse_sitemap_locs(xml: str) -> list[str]:
    """Every <loc> value in a sitemap/sitemapindex, XML-unescaped, order-preserved."""
    return [unescape(m.group(1).strip()) for m in _LOC_RE.finditer(xml) if m.group(1).strip()]


def is_sitemap_index(xml: str) -> bool:
    """True when the document root is <sitemapindex> (children are more sitemaps)."""
    return bool(_SITEMAPINDEX_RE.search(xml))


def looks_like_sitemap(xml: str) -> bool:
    """True when the document is a urlset or sitemapindex (cheap validity gate)."""
    return bool(_URLSET_RE.search(xml) or _SITEMAPINDEX_RE.search(xml))


def decode_sitemap(result: FetchResult) -> str:
    """Decode a sitemap body, transparently gunzipping .gz or gzip-magic payloads."""
    body = result.body
    if result.url.endswith(".gz") or body[:2] == b"\x1f\x8b":
        try:
            body = gzip.decompress(body)
        except (OSError, EOFError):
            pass
    return body.decode("utf-8", errors="replace")


# ── discovery (async, injected fetcher) ────────────────────────────────────────
async def _safe_fetch(fetcher: Fetcher, url: str) -> FetchResult | None:
    """Fetch one URL, swallowing transport faults (returns None) — never raises."""
    try:
        return await fetcher(url)
    except Exception as exc:  # transport faults only; HTTP errors carry a status
        log.debug("fetch failed %s: %s", url, type(exc).__name__)
        return None


async def _fetch_json(fetcher: Fetcher, url: str) -> Any | None:
    """GET a URL and parse JSON; None on transport fault, non-200, or invalid JSON."""
    result = await _safe_fetch(fetcher, url)
    if result is None or result.status_code != 200:
        return None
    try:
        return json.loads(result.text)
    except (ValueError, json.JSONDecodeError):
        return None


async def discover_sitemap_candidates(base_url: str, fetcher: Fetcher) -> list[str]:
    """robots.txt `Sitemap:` directives first, then the standard fallback paths."""
    origin = _origin(base_url)
    seen: set[str] = set()
    candidates: list[str] = []

    robots = await _safe_fetch(fetcher, urljoin(origin + "/", "robots.txt"))
    if robots is not None and robots.status_code == 200:
        for match in _ROBOTS_SITEMAP_RE.finditer(robots.text):
            url = match.group(1).strip()
            # SSRF guard: a hostile dealer's robots.txt can declare a Sitemap on
            # an internal host / metadata IP. Only follow public http(s) targets.
            if url and url not in seen and is_safe_public_url(url):
                seen.add(url)
                candidates.append(url)

    for path in _SITEMAP_FALLBACKS:
        url = urljoin(origin, path)
        if url not in seen:
            seen.add(url)
            candidates.append(url)
    return candidates


async def discover_sitemap_listings(
    base_url: str,
    fetcher: Fetcher,
    *,
    max_sitemaps: int = _MAX_SITEMAPS,
    max_urls: int = _MAX_URLS,
) -> list[str]:
    """
    Expand the dealer's sitemaps into vehicle detail URLs.

    Breadth-first over sitemap candidates, recursing through <sitemapindex>
    children and collecting <urlset> entries that (a) carry a verified vehicle
    path token, (b) are deep links, and (c) stay on the dealer's own host. Bounded
    by max_sitemaps / max_urls so a pathological sitemap can never run unbounded.
    """
    base_host = _host(base_url)
    queue = await discover_sitemap_candidates(base_url, fetcher)
    visited: set[str] = set()
    listings: list[str] = []
    listing_seen: set[str] = set()
    expanded = 0

    while queue and expanded < max_sitemaps and len(listings) < max_urls:
        sitemap_url = queue.pop(0)
        if sitemap_url in visited:
            continue
        visited.add(sitemap_url)

        result = await _safe_fetch(fetcher, sitemap_url)
        if result is None or result.status_code != 200:
            continue
        xml = decode_sitemap(result)
        if not looks_like_sitemap(xml):
            continue
        expanded += 1

        locs = parse_sitemap_locs(xml)
        if is_sitemap_index(xml):
            for loc in locs:
                # SSRF guard: sitemapindex children are attacker-controlled and may
                # point off-host at internal infrastructure — validate before queueing.
                if loc not in visited and is_safe_public_url(loc):
                    queue.append(loc)
            continue

        for loc in locs:
            if (
                looks_like_listing(loc)
                and is_deep_link(loc)
                and _same_site(loc, base_host)
                and loc not in listing_seen
            ):
                listing_seen.add(loc)
                listings.append(loc)
                if len(listings) >= max_urls:
                    break
    return listings


async def discover_wp_listings(
    base_url: str,
    fetcher: Fetcher,
    *,
    per_page: int = _WP_PER_PAGE,
    max_pages: int = _WP_MAX_PAGES,
    max_urls: int = _MAX_URLS,
) -> list[str]:
    """
    Enumerate vehicle detail `link`s from a WordPress REST API, or [] if not WP.

    Probes /wp-json/, reads /wp-json/wp/v2/types, keeps post types whose slug
    matches a vehicle CPT hint, then paginates each CPT collecting item links.
    Returns URLs only — extraction stays on the single parse_listing path.
    """
    origin = _origin(base_url)
    base_host = _host(base_url)

    if await _fetch_json(fetcher, urljoin(origin + "/", "wp-json/")) is None:
        return []

    types = await _fetch_json(fetcher, urljoin(origin + "/", "wp-json/wp/v2/types"))
    if not isinstance(types, dict):
        return []
    cpts = [slug for slug in types if any(h in slug.lower() for h in _WP_CPT_HINTS)]

    urls: list[str] = []
    seen: set[str] = set()
    for cpt in cpts:
        for page in range(1, max_pages + 1):
            endpoint = urljoin(origin + "/", f"wp-json/wp/v2/{cpt}?per_page={per_page}&page={page}")
            items = await _fetch_json(fetcher, endpoint)
            if not isinstance(items, list) or not items:
                break
            for item in items:
                link = item.get("link") if isinstance(item, dict) else None
                if (
                    isinstance(link, str)
                    and is_deep_link(link)
                    and _same_site(link, base_host)
                    and link not in seen
                ):
                    seen.add(link)
                    urls.append(link)
                    if len(urls) >= max_urls:
                        return urls
            if len(items) < per_page:
                break
    return urls


async def discover_listing_urls(
    base_url: str,
    fetcher: Fetcher,
    *,
    max_urls: int = _MAX_URLS,
) -> list[str]:
    """
    Union both discovery strategies: sitemap first, WP-REST to fill the gap.

    WordPress enumeration only runs when the sitemap yielded nothing, so a dealer
    with a proper vehicle sitemap costs zero wasted /wp-json probes.
    """
    urls = await discover_sitemap_listings(base_url, fetcher, max_urls=max_urls)
    if urls:
        return urls
    return await discover_wp_listings(base_url, fetcher, max_urls=max_urls)


# ── extraction orchestration ───────────────────────────────────────────────────
@dataclass(frozen=True)
class DealerExtraction:
    """Outcome of extracting one dealer site — records plus per-URL reject reasons."""

    base_url: str
    country: str
    discovered: int
    attempted: int
    records: tuple[VehicleRecord, ...]
    rejected: tuple[tuple[str, str], ...]

    @property
    def extracted(self) -> int:
        return len(self.records)

    @property
    def success_rate(self) -> float:
        """Fraction of attempted detail pages that yielded an ingestible record."""
        return self.extracted / self.attempted if self.attempted else 0.0


async def extract_listing(
    url: str,
    fetcher: Fetcher,
    *,
    country: str,
    source_domain: str | None = None,
) -> tuple[VehicleRecord | None, str]:
    """
    Fetch one detail page and run it through the full pipeline.

    Returns (record, "ok") on success, or (None, reason) naming the failure stage
    so the caller can record DLQ telemetry. A page is rejected when it lacks the
    critical fields (make/model/year/price/url/image) or fails a quality gate.
    """
    result = await _safe_fetch(fetcher, url)
    if result is None:
        return None, "fetch_error"
    if result.status_code != 200:
        return None, f"http_{result.status_code}"

    html = result.text
    raw = parse_listing(html)
    if not raw:
        return None, "no_fields"

    final_url = result.url or url
    domain = source_domain or _host(final_url)
    record = to_record(raw, source_url=final_url, source_domain=domain, country=country)
    if not record.has_critical_fields():
        # Second chance — SEO meta. Many dealers ship NO JSON-LD/microdata but DO
        # carry the full vehicle in og:title (make/model head) + og:description
        # ("Prix: …", "Reserve it for €…", km/year labels) — the same authoritative
        # signal E07 reads from a render, present in the STATIC HTML too. Gap-fill
        # ONLY the still-missing fields (cascade JSON-LD/OG values always win), so a
        # page that already passed is byte-for-byte unchanged; only a currently
        # failing page gets a second chance. Lazy import avoids a module cycle.
        from scrapers.pipeline.playwright_extractor import parse_rendered_meta

        meta = parse_rendered_meta(html)
        filled = dict(raw)
        for key, value in meta.items():
            if value not in (None, "", [], (), {}) and filled.get(key) in (None, "", [], (), {}):
                filled[key] = value
        # Provenance guard on price. We are here because the cascade could not even
        # surface make/model — a page that weak. On such a page the stage-3 heuristic
        # (first "<number> €" anywhere in the full HTML) routinely grabs a financing /
        # option / deposit / warranty figure, NOT the car price (observed: a €1,000
        # "acompte" passed for a BMW X4). Keep the price only when a RELIABLE source
        # confirms it — schema.org offer, product:price meta, or the scoped SEO
        # title/description — else drop it and let the minimum-vehicle gate reject the
        # row. Better no row than a fabricated price.
        jsonld = parse_jsonld(html)
        og = parse_og_meta(html)
        reliable_price = jsonld.get("price") or og.get("price") or meta.get("price")
        if not reliable_price:
            filled.pop("price", None)
            filled.pop("currency", None)
        # Same provenance guard for the year: the full-HTML heuristic grabs the first
        # 19xx/20xx token anywhere — a copyright "©2000", a phone, an address — not the
        # registration year (observed: a whole dealer's stock stamped year=2000). Keep
        # the year only from a reliable source (schema.org modelDate, or the scoped SEO
        # title/description label); else drop it so the row is honestly year-less.
        reliable_year = jsonld.get("year") or meta.get("year")
        if not reliable_year:
            filled.pop("year", None)
        if filled != raw:
            record = to_record(filled, source_url=final_url, source_domain=domain, country=country)
        if not record.has_critical_fields():
            return None, "missing_critical:" + ",".join(record.missing_critical())

    verdict = evaluate(record, html=html)
    if not verdict.ok:
        return None, verdict.reason
    return record, "ok"


async def extract_dealer(
    base_url: str,
    fetcher: Fetcher,
    *,
    country: str,
    max_urls: int = 2_000,
    urls: list[str] | None = None,
) -> DealerExtraction:
    """
    End-to-end: discover this dealer's listing URLs and extract every one.

    Pass `urls` to skip discovery (e.g. when a sitemap/WP enumeration already ran
    upstream). Each URL is fetched, parsed and quality-gated independently; one
    bad page never aborts the rest. The result carries both the canonical records
    and a (url, reason) entry for every rejection.
    """
    domain = _host(base_url)
    listing_urls = (
        urls if urls is not None
        else await discover_listing_urls(base_url, fetcher, max_urls=max_urls)
    )

    records: list[VehicleRecord] = []
    rejected: list[tuple[str, str]] = []
    attempted = 0

    for url in listing_urls[:max_urls]:
        attempted += 1
        record, reason = await extract_listing(
            url, fetcher, country=country, source_domain=domain
        )
        if record is not None:
            records.append(record)
        else:
            rejected.append((url, reason))

    log.info(
        "dealer %s: discovered=%d attempted=%d extracted=%d rejected=%d",
        domain, len(listing_urls), attempted, len(records), len(rejected),
    )
    return DealerExtraction(
        base_url=base_url,
        country=country.upper(),
        discovered=len(listing_urls),
        attempted=attempted,
        records=tuple(records),
        rejected=tuple(rejected),
    )
