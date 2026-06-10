"""
Dealer web-type detector (frente C, point 1) — domain → versioned ExtractionConfig.

Given only a dealer domain, PROBE how the site exposes its inventory and where the
catalog/stock lives, then emit the recipe the seam executes. The probe is bounded and
RAM-safe: it reuses ``discovery.discover_detail_urls`` (sitemap → wp → catalog → catalog-
follow → render-follow) to reach REAL vehicle detail URLs, then decides whether those
details extract STATICALLY or need a browser render.

Decision (cheapest signal first; the first detail that yields a real vehicle wins):

  1. discover detail URLs (catalog-aware)                         (static, then render)
  2. STATIC extraction of a sample detail  → sitemap/wp/jsonld    (config: static)
  3. RENDER extraction of a sample detail  → playwright_meta      (config: E07)

The strategy stored is the EXTRACTION verdict (static vs rendered). URL discovery is
adaptive and re-run by the harvester via the same ``discover_detail_urls``, so a config
is a recipe, not a frozen URL list. No new dependencies — every probe reuses the
verified ``generic_extractor`` / ``playwright_extractor`` primitives.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

from scrapers.common.net_guard import is_safe_public_url
from scrapers.dealer_scraping.cms_fingerprint import fingerprint_cms
from scrapers.dealer_scraping.detector_helpers import (  # re-exported for callers/tests
    classify_non_yield,
    detect_embedded_dms,
    detect_spa_markers,
    extract_listing_links,
    find_catalog_url,
)
from scrapers.dealer_scraping.discovery import discover_detail_urls
from scrapers.pipeline.generic_extractor import Fetcher, extract_listing
from scrapers.pipeline.playwright_extractor import extract_listing_rendered
from scrapers.pipeline.schema import VehicleRecord
from scrapers.portals.config import (
    DriftBaseline,
    Endpoints,
    Extraction,
    ExtractionConfig,
    Pagination,
)

__all__ = [
    "DetectionResult", "detect_web_type", "build_config",
    "detect_spa_markers", "extract_listing_links", "find_catalog_url",
]

log = logging.getLogger(__name__)

DEFAULT_SAMPLE_N = 3        # detail pages probed for an extraction verdict
DEFAULT_MAX_DISCOVER = 40   # listing URLs collected during detection (not a harvest)


@dataclass(frozen=True)
class DetectionResult:
    """What the probe learned about one dealer domain."""

    domain: str
    country: str
    strategy: str                       # config.STRATEGIES value, or "none"
    yields_inventory: bool              # a real VehicleRecord was extracted in the probe
    discovery: str                      # sitemap | wp_rest | catalog | catalog_follow | render_follow | none
    discovered: int                     # detail URLs found during detection (bounded)
    sitemap_url: str = ""
    catalog_url: str = ""
    spa_markers: tuple[str, ...] = ()
    sample_urls: tuple[str, ...] = ()
    proof: dict | None = None           # extracted sample fields, evidence it yields
    notes: tuple[str, ...] = field(default_factory=tuple)
    classification: str = ""            # strategy when ok, else by-cause label (report)
    # CMS-multiplier signal (additive): the platform family fingerprinted from the
    # SAME homepage fetch the probe already does. Appended LAST with "" defaults so
    # every existing positional/keyword constructor keeps working unchanged.
    cms: str = ""                       # cms_fingerprint family key ("" = none fired)
    cms_confidence: str = ""            # 'high' | 'medium' ("" when cms is empty)

    @property
    def ok(self) -> bool:
        return self.yields_inventory and self.strategy != "none"


def _record_proof(rec: VehicleRecord) -> dict:
    """A compact, JSON-safe evidence dict from an extracted record."""
    return {
        "make": rec.make, "model": rec.model, "year": rec.year,
        "price": str(rec.price) if rec.price is not None else None,
        "currency": rec.currency, "images": len(rec.images),
    }


def _strategy_for_static(discovery: str) -> str:
    return {
        "sitemap": "sitemap_listing",
        "wp_rest": "wp_rest",
        "catalog": "jsonld_detail",
        "catalog_follow": "jsonld_detail",
        "render_follow": "jsonld_detail",
    }.get(discovery, "jsonld_detail")


def build_config(result: DetectionResult) -> ExtractionConfig | None:
    """
    Turn a positive detection into a versioned ExtractionConfig, or None.

    Returns None when the dealer yielded no inventory in the probe (recorded as a
    non-yielding domain, not a config) so the store only ever holds recipes proven to
    extract a real vehicle. ``expected_min_volume`` is seeded conservatively from what
    detection discovered; the harvester refines it after a full discovery.
    """
    if not result.ok:
        return None
    is_e07 = result.strategy in ("playwright_meta", "playwright_xhr")
    return ExtractionConfig(
        source_key=result.domain,
        country=result.country.upper()[:2],
        strategy=result.strategy,
        version=1,
        endpoints=Endpoints(
            host=f"www.{result.domain}",
            sitemap_url=result.sitemap_url,
            listing_url_template=result.catalog_url,
        ),
        pagination=Pagination(),
        extraction=Extraction(method="og" if is_e07 else "jsonld"),
        drift_baseline=DriftBaseline(
            extraction_method="og" if is_e07 else "jsonld",
            expected_min_volume=max(1, result.discovered),
            required_fields=("make", "model", "year", "price"),
            min_nonnull_ratio=0.6,
        ),
    )


async def detect_web_type(
    domain: str,
    *,
    country: str,
    static_fetcher: Fetcher,
    e07_fetcher: Fetcher | None = None,
    sample_n: int = DEFAULT_SAMPLE_N,
    max_discover: int = DEFAULT_MAX_DISCOVER,
) -> DetectionResult:
    """
    Probe one dealer domain and decide its extraction strategy.

    Discovery is catalog-aware (follows ``/fahrzeuge``-style indexes to real details,
    statically then via render). The first sample detail that yields a real
    ``VehicleRecord`` fixes the verdict: STATIC → sitemap/wp/jsonld, else RENDER →
    playwright_meta (only attempted when ``e07_fetcher`` is supplied).
    """
    base_url = f"https://{domain}"
    notes: list[str] = []
    if not is_safe_public_url(base_url):
        return DetectionResult(domain, country, "none", False, "none", 0, notes=("ssrf_blocked",))

    detail_urls, method, home_html, catalog_url = await discover_detail_urls(
        domain, static_fetcher=static_fetcher, e07_fetcher=e07_fetcher, cap=max_discover
    )
    spa = detect_spa_markers(home_html)
    probe_urls = detail_urls[:sample_n]

    # CMS-multiplier signal (additive, pure, zero extra I/O): fingerprint the platform
    # family from the homepage HTML already in hand. 'unknown' maps to "" so the new
    # fields stay falsy unless a real family fired. The detection verdict below is
    # NOT influenced by this — the signal only rides along on the result.
    verdict = fingerprint_cms(home_html) if home_html else None
    cms = verdict.cms if verdict is not None and verdict.cms != "unknown" else ""
    cms_confidence = verdict.confidence if cms and verdict is not None else ""

    # STATIC extraction verdict
    for u in probe_urls:
        rec, reason = await extract_listing(u, static_fetcher, country=country, source_domain=domain)
        if rec is not None:
            return DetectionResult(
                domain=domain, country=country, strategy=_strategy_for_static(method),
                yields_inventory=True, discovery=method, discovered=len(detail_urls),
                catalog_url=catalog_url, spa_markers=spa, sample_urls=tuple(probe_urls),
                proof=_record_proof(rec), notes=tuple(notes),
                classification=_strategy_for_static(method),
                cms=cms, cms_confidence=cms_confidence,
            )
        notes.append(f"static:{reason}")

    # RENDER extraction verdict (only with a browser)
    if e07_fetcher is not None and probe_urls:
        for u in probe_urls[:sample_n]:
            rec, reason = await extract_listing_rendered(
                u, e07_fetcher, country=country, source_domain=domain
            )
            if rec is not None:
                return DetectionResult(
                    domain=domain, country=country, strategy="playwright_meta",
                    yields_inventory=True, discovery=method, discovered=len(detail_urls),
                    catalog_url=catalog_url, spa_markers=spa, sample_urls=tuple(probe_urls),
                    proof=_record_proof(rec), notes=tuple(notes),
                    classification="playwright_meta",
                    cms=cms, cms_confidence=cms_confidence,
                )
            notes.append(f"e07:{reason}")

    return DetectionResult(
        domain=domain, country=country, strategy="none", yields_inventory=False,
        discovery=method, discovered=len(detail_urls), catalog_url=catalog_url,
        spa_markers=spa, sample_urls=tuple(probe_urls), proof=None,
        notes=tuple(notes) or ("no_listing_urls",),
        classification=classify_non_yield(home_html, detail_urls, spa),
        cms=cms, cms_confidence=cms_confidence,
    )
