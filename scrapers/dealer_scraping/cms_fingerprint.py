"""
CMS / web-platform fingerprint — pure HTML+headers → family verdict, no network.

Dealers built on the same platform share page structure, so one extraction recipe
closes a whole family at once. This module classifies WHICH platform a dealer site
is built on from public markers in its raw HTML (and response headers), so the seam
can route the matching recipe. Deterministic, I/O-free, unit-testable.

It REUSES the proven leaf helpers instead of duplicating their logic:
``detect_embedded_dms`` (src/data-src host scan over ``_DMS_PROVIDERS``) provides the
host-based signal for the DMS-backed families, and ``detect_spa_markers`` provides the
Next/Nuxt framework signals.

Priority order (the FIRST family with at least one fired signal wins; specific
platforms are evaluated BEFORE the generic ``wordpress``/``symfony`` stacks, because a
WordPress shell that embeds e.g. an izmocars or Modix widget must route to the
widget's recipe, not the shell's):

  1.  izmocars     'izmostatic' | 'data-izmo' | 'cdn.izmocars' in the HTML
  2.  dealer_com   'static.dealer.com' host (via detect_embedded_dms or literal) |
                   'data-dealer-com' attribute | 'ddc-'-prefixed CSS class
  3.  dealerk      'dealerk' in src/host (via detect_embedded_dms or literal) |
                   '/dk-' endpoint path
  4.  modix        'modix' | 'gw-trends' host (via detect_embedded_dms or literal)
  5.  planetvo     'planetvo' | 'autralis' host (via detect_embedded_dms or literal)
  6.  incadea      'incadea' host (via detect_embedded_dms or literal; covers
                   'dms.incadea' — a subset token is not independent evidence)
  7.  next_dealer  Next.js marker (via detect_spa_markers) AND a vehicle signal
                   (JSON-LD Car/Vehicle, or 'vehicle' in the detail sample)
  8.  nuxt_dealer  Nuxt marker (via detect_spa_markers)
  9.  wordpress    '/wp-content/' | '/wp-json/' | <meta name="generator" WordPress>
  10. symfony      'X-Debug-Token*' response header | 'sf-' cookie (headers only)

Confidence: 'high' when the winning family fired >=2 DISTINCT signals, 'medium' on
exactly 1, and ('unknown', cms='unknown') when no family fired at all.
"""
from __future__ import annotations

import re

from dataclasses import dataclass

from scrapers.dealer_scraping.detector_helpers import (
    detect_embedded_dms,
    detect_spa_markers,
)

__all__ = ["CmsVerdict", "fingerprint_cms"]

# 'ddc-'-prefixed class inside a class attribute (Dealer.com widget convention).
_DDC_CLASS_RE = re.compile(r'class\s*=\s*["\'][^"\']*\bddc-', re.I)
# <meta name="generator" content="WordPress ..."> in either attribute order.
_WP_GENERATOR_RE = re.compile(
    r"<meta\b(?=[^>]*\bname\s*=\s*[\"']generator[\"'])(?=[^>]*wordpress)[^>]*>", re.I
)
# JSON-LD vehicle entity ("@type": "Car" / "Vehicle") — the strong vehicle signal.
_JSONLD_VEHICLE_RE = re.compile(r'"@type"\s*:\s*"(?:Car|Vehicle)"', re.I)

_CONFIDENCE_HIGH_MIN_SIGNALS = 2


@dataclass(frozen=True)
class CmsVerdict:
    """The platform family a dealer site is built on, with its evidence."""

    cms: str                    # family name from the priority table, or "unknown"
    confidence: str             # 'high' | 'medium' | 'unknown'
    signals: tuple[str, ...]    # which concrete markers fired (deduped, ordered)


def _vehicle_signal(home_html: str, sample_detail_html: str) -> str | None:
    """Vehicle evidence for the SPA families: JSON-LD entity, else detail token."""
    if _JSONLD_VEHICLE_RE.search(sample_detail_html) or _JSONLD_VEHICLE_RE.search(home_html):
        return "jsonld-car"
    if "vehicle" in sample_detail_html.lower():
        return "vehicle-token"
    return None


def _confidence(signals: tuple[str, ...]) -> str:
    return "high" if len(signals) >= _CONFIDENCE_HIGH_MIN_SIGNALS else "medium"


def fingerprint_cms(
    home_html: str,
    headers: dict[str, str] | None = None,
    sample_detail_html: str = "",
) -> CmsVerdict:
    """
    Classify the web platform / CMS a dealer site is built on. Pure, no I/O.

    ``home_html`` and ``sample_detail_html`` are scanned together for markers (a
    platform widget can live on either page); ``headers`` (case-insensitive names)
    only feed the symfony probes. See the module docstring for the priority order
    and the confidence rule.
    """
    html = home_html if not sample_detail_html else f"{home_html}\n{sample_detail_html}"
    low = html.lower()
    norm_headers = {k.lower(): v for k, v in (headers or {}).items()}

    dms = detect_embedded_dms(html)          # reused host-based DMS signal
    spa = detect_spa_markers(html)           # reused SPA framework signal
    vehicle = _vehicle_signal(home_html, sample_detail_html)
    cookie_blob = norm_headers.get("set-cookie", "") + norm_headers.get("cookie", "")

    # Each family probe merges the reused helper verdict with the literal token so
    # one real-world marker never double-counts into a fake 'high'.
    families: tuple[tuple[str, tuple[tuple[str, bool], ...]], ...] = (
        ("izmocars", (
            ("izmostatic", "izmostatic" in low),
            ("data-izmo", "data-izmo" in low),
            ("cdn.izmocars", "cdn.izmocars" in low),
        )),
        ("dealer_com", (
            ("dealer.com-host", dms == "dealer.com" or "static.dealer.com" in low),
            ("data-dealer-com", "data-dealer-com" in low),
            ("ddc-class", bool(_DDC_CLASS_RE.search(html))),
        )),
        ("dealerk", (
            ("dealerk-host", dms == "dealerk" or "dealerk" in low),
            ("dk-endpoint", "/dk-" in low),
        )),
        ("modix", (
            ("modix-host", dms == "modix" or "modix" in low),
            ("gw-trends-host", dms == "gw-trends" or "gw-trends" in low),
        )),
        ("planetvo", (
            ("planetvo-host", dms == "planetvo" or "planetvo" in low),
            ("autralis-host", dms == "autralis" or "autralis" in low),
        )),
        ("incadea", (
            ("incadea-host", dms == "incadea" or "incadea" in low),
        )),
        ("next_dealer", (
            ("spa:next", "next" in spa and vehicle is not None),
            (f"vehicle:{vehicle}", "next" in spa and vehicle is not None),
        )),
        ("nuxt_dealer", (
            ("spa:nuxt", "nuxt" in spa),
        )),
        ("wordpress", (
            ("wp-content", "/wp-content/" in low),
            ("wp-json", "/wp-json/" in low),
            ("meta-generator-wordpress", bool(_WP_GENERATOR_RE.search(html))),
        )),
        ("symfony", (
            ("header:x-debug-token", any(k.startswith("x-debug-token") for k in norm_headers)),
            ("cookie:sf-", "sf-" in cookie_blob.lower()),
        )),
    )

    for family, probes in families:
        fired = tuple(name for name, hit in probes if hit)
        if fired:
            return CmsVerdict(cms=family, confidence=_confidence(fired), signals=fired)
    return CmsVerdict(cms="unknown", confidence="unknown", signals=())
