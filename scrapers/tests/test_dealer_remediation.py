"""
Dealer auto-remediation — drift detection + the re-detect → regenerate → revalidate loop.

Fakes for the seam/purger and in-memory fetchers (no I/O). Covers: the drift floor
decision, a static-recovery loop, a static→E07 strategy migration with a version bump,
and an honest escalation when the dealer truly yields nothing.
"""
from __future__ import annotations

import asyncio

import pytest

from scrapers.dealer_scraping import remediation as rem
from scrapers.dealer_scraping.remediation import needs_remediation, remediate
from scrapers.pipeline.generic_extractor import FetchResult
from scrapers.portals import config as cfgmod
from scrapers.portals.config import DriftBaseline, Endpoints, ExtractionConfig


class MapFetcher:
    def __init__(self, pages: dict[str, tuple[int, bytes]]):
        self._pages = pages

    async def __call__(self, url: str) -> FetchResult:
        if url in self._pages:
            status, body = self._pages[url]
            return FetchResult(url=url, status_code=status, body=body)
        return FetchResult(url=url, status_code=404, body=b"")


def _b(t: str) -> bytes:
    return t.encode("utf-8")


def _run(coro):
    return asyncio.run(coro)


_PAD = "<div class='spec'><span></span></div>" * 600


def _jsonld() -> bytes:
    return _b(
        "<html><head><script type=\"application/ld+json\">"
        '{"@context":"https://schema.org","@type":"Car","brand":{"name":"BMW"},'
        '"model":"320d","vehicleModelDate":"2019","image":["https://cdn.d.example/1.jpg"],'
        '"offers":{"price":"24900","priceCurrency":"EUR"}}'
        "</script></head><body>" + _PAD + "</body></html>"
    )


_SPA_SHELL = _b('<html><head></head><body><div id="__next"></div></body></html>')
_META_DETAIL = _b(
    "<html><head>"
    '<meta property="og:title" content="SKODA Kamiq 1.5 TSI gebraucht für CHF 29\'500">'
    '<meta name="description" content="SKODA Kamiq - Benzin, Kilometer: 10\'600 km, '
    "Preis: CHF 29'500, Erstzulassung: 01.09.2025\">"
    '<meta property="og:image" content="https://cdn.x.ch/1.jpg"></head><body>' + _PAD + "</body></html>"
)


def _sitemap(detail: bytes) -> dict[str, tuple[int, bytes]]:
    sm = "<urlset><url><loc>https://dealer.example/vehicles/bmw-320d-1</loc></url></urlset>"
    return {
        "https://dealer.example/robots.txt": (200, _b("Sitemap: https://dealer.example/sitemap.xml")),
        "https://dealer.example/sitemap.xml": (200, _b(sm)),
        "https://dealer.example/vehicles/bmw-320d-1": (200, detail),
    }


@pytest.fixture()
def isolated_stores(tmp_path, monkeypatch):
    portal_dir = tmp_path / "portals"
    dealer_dir = tmp_path / "dealers"
    portal_dir.mkdir()
    dealer_dir.mkdir()
    monkeypatch.setattr(cfgmod, "_CONFIG_DIR", portal_dir)
    monkeypatch.setattr(cfgmod, "_DEALER_DIR", dealer_dir)
    return portal_dir, dealer_dir


def _seam(persisted):
    async def run(domain, country, urls, is_e07):
        return persisted
    return run


async def _purge(urls):
    return len(urls)


# ── drift floor decision ──────────────────────────────────────────────────────────
@pytest.mark.unit
def test_needs_remediation_floor():
    cfg = ExtractionConfig(
        source_key="d.de", country="DE", strategy="sitemap_listing",
        drift_baseline=DriftBaseline(expected_min_volume=100),
    )
    assert needs_remediation(cfg, current_volume=5) is True
    assert needs_remediation(cfg, current_volume=150) is False


# ── recovery loop ──────────────────────────────────────────────────────────────────
@pytest.mark.unit
def test_remediate_recovers_static_dealer(isolated_stores):
    # An existing v2 config; the site re-detects cleanly and revalidates.
    cfgmod.save(ExtractionConfig(
        source_key="dealer.example", country="DE", strategy="sitemap_listing", version=2,
        endpoints=Endpoints(host="www.dealer.example"),
        drift_baseline=DriftBaseline(expected_min_volume=50),
    ), kind="dealer")
    static = MapFetcher(_sitemap(_jsonld()))
    r = _run(remediate("dealer.example", "DE", static_fetcher=static, e07_fetcher=None,
                       seam_runner=_seam(1), purger=_purge))
    assert r.recovered is True and r.persisted == 1
    assert r.version == 3                         # bumped from 2
    assert r.new_strategy == "sitemap_listing"
    assert cfgmod.load("dealer.example").version == 3


@pytest.mark.unit
def test_remediate_migrates_static_to_e07(isolated_stores):
    # Site migrated to a SPA: static now empty, render yields → strategy changes.
    cfgmod.save(ExtractionConfig(
        source_key="dealer.example", country="CH", strategy="sitemap_listing", version=1,
        drift_baseline=DriftBaseline(expected_min_volume=20),
    ), kind="dealer")
    static = MapFetcher(_sitemap(_SPA_SHELL))
    e07 = MapFetcher({"https://dealer.example/vehicles/bmw-320d-1": (200, _META_DETAIL)})
    r = _run(remediate("dealer.example", "CH", static_fetcher=static, e07_fetcher=e07,
                       seam_runner=_seam(1), purger=_purge))
    assert r.strategy_changed is True
    assert r.old_strategy == "sitemap_listing" and r.new_strategy == "playwright_meta"
    assert r.recovered is True and r.version == 2


@pytest.mark.unit
def test_remediate_escalates_when_truly_dead(isolated_stores):
    static = MapFetcher({"https://dead.de": (200, _b("<html><body>nothing</body></html>"))})
    r = _run(remediate("dead.de", "DE", static_fetcher=static, e07_fetcher=None,
                       seam_runner=_seam(0), purger=_purge))
    # Escalated, not silently retried: no recovery, no new recipe, a reason recorded.
    assert r.recovered is False and r.new_strategy is None and r.persisted == 0
    assert r.notes  # an honest escalation reason (e.g. no_listing_urls / still_no_inventory)
