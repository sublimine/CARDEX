"""
Dealer harvester — orchestration control flow against in-memory fakes.

The seam (Redis+Postgres) and the network are injected (``seam_runner`` / ``purger``
/ map fetchers), so detect → discover → sample → persist → measure → purge runs
synchronously with no I/O, the repo convention. Covers: a yielding static dealer
end-to-end, a dead dealer, fault isolation (a raising seam never aborts the batch),
purge on/off, config resolve-vs-detect, and the report aggregation.
"""
from __future__ import annotations

import asyncio

import pytest

from scrapers.dealer_scraping import harvester as hv
from scrapers.dealer_scraping.harvester import (
    DealerHarvestResult,
    aggregate,
    harvest_dealer,
    resolve_or_detect_config,
)
from scrapers.pipeline.generic_extractor import FetchResult
from scrapers.portals import config as cfgmod


class MapFetcher:
    def __init__(self, pages: dict[str, tuple[int, bytes]]):
        self._pages = pages
        self.requested: list[str] = []

    async def __call__(self, url: str) -> FetchResult:
        self.requested.append(url)
        if url in self._pages:
            status, body = self._pages[url]
            return FetchResult(url=url, status_code=status, body=body)
        return FetchResult(url=url, status_code=404, body=b"")


def _b(t: str) -> bytes:
    return t.encode("utf-8")


def _run(coro):
    return asyncio.run(coro)


_PAD = "<div class='spec'><span></span></div>" * 600


def _jsonld(make="BMW", model="320d", price="24900") -> bytes:
    return _b(
        "<html><head><script type=\"application/ld+json\">"
        '{"@context":"https://schema.org","@type":"Car",'
        f'"brand":{{"name":"{make}"}},"model":"{model}","vehicleModelDate":"2019",'
        '"mileageFromOdometer":{"value":"85000"},"image":["https://cdn.d.example/1.jpg"],'
        f'"offers":{{"price":"{price}","priceCurrency":"EUR"}}}}'
        "</script></head><body>" + _PAD + "</body></html>"
    )


def _sitemap_dealer() -> dict[str, tuple[int, bytes]]:
    sm = (
        "<urlset>"
        "<url><loc>https://dealer.example/vehicles/bmw-320d-1</loc></url>"
        "<url><loc>https://dealer.example/vehicles/audi-a4-2</loc></url>"
        "</urlset>"
    )
    return {
        "https://dealer.example/robots.txt": (200, _b("Sitemap: https://dealer.example/sitemap.xml")),
        "https://dealer.example/sitemap.xml": (200, _b(sm)),
        "https://dealer.example/vehicles/bmw-320d-1": (200, _jsonld()),
        "https://dealer.example/vehicles/audi-a4-2": (200, _jsonld(make="Audi", model="A4")),
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


def _recording_seam(persist_per_url=1):
    calls = []

    async def seam(domain, country, urls, is_e07):
        calls.append((domain, country, tuple(urls), is_e07))
        return min(len(urls), len(urls) * persist_per_url)

    seam.calls = calls
    return seam


def _recording_purger():
    purged = []

    async def purge(urls):
        purged.append(tuple(urls))
        return len(urls)

    purge.purged = purged
    return purge


# ── config resolution ────────────────────────────────────────────────────────────
@pytest.mark.unit
def test_resolve_detects_and_saves_dealer_config(isolated_stores):
    _, dealer_dir = isolated_stores
    static = MapFetcher(_sitemap_dealer())
    cfg, detection, newly = _run(
        resolve_or_detect_config("dealer.example", "DE", static_fetcher=static)
    )
    assert newly is True and cfg is not None
    assert cfg.strategy == "sitemap_listing"
    assert (dealer_dir / "dealer.example.json").exists()   # persisted to dealer store
    # A second resolve loads the saved recipe — no re-probe.
    cfg2, det2, newly2 = _run(resolve_or_detect_config("dealer.example", "DE", static_fetcher=static))
    assert newly2 is False and det2 is None and cfg2.strategy == "sitemap_listing"


# ── per-dealer harvest ────────────────────────────────────────────────────────────
@pytest.mark.unit
def test_harvest_static_dealer_yields_and_purges(isolated_stores):
    static = MapFetcher(_sitemap_dealer())
    seam = _recording_seam()
    purger = _recording_purger()
    r = _run(harvest_dealer(
        "dealer.example", "de", static_fetcher=static, e07_fetcher=None,
        seam_runner=seam, purger=purger, limit=12,
    ))
    assert r.web_type == "sitemap_listing"
    assert r.discovered == 2 and r.attempted == 2 and r.persisted == 2
    assert r.yields_inventory and r.success_rate == 1.0
    assert r.newly_detected and r.purged and r.drift_ok
    assert seam.calls and seam.calls[0][0] == "dealer.example" and seam.calls[0][3] is False
    assert purger.purged == [(
        "https://dealer.example/vehicles/bmw-320d-1",
        "https://dealer.example/vehicles/audi-a4-2",
    )]


@pytest.mark.unit
def test_harvest_dead_dealer_records_none(isolated_stores):
    static = MapFetcher({"https://dead.de": (200, _b("<html><body>hi</body></html>"))})
    r = _run(harvest_dealer(
        "dead.de", "de", static_fetcher=static, e07_fetcher=None,
        seam_runner=_recording_seam(), purger=_recording_purger(),
    ))
    assert r.web_type == "none" and r.persisted == 0 and not r.yields_inventory


@pytest.mark.unit
def test_harvest_purge_disabled_keeps_rows(isolated_stores):
    static = MapFetcher(_sitemap_dealer())
    purger = _recording_purger()
    r = _run(harvest_dealer(
        "dealer.example", "de", static_fetcher=static, e07_fetcher=None,
        seam_runner=_recording_seam(), purger=purger, purge=False,
    ))
    assert r.persisted == 2 and r.purged is False and purger.purged == []


@pytest.mark.unit
def test_harvest_seam_fault_is_isolated(isolated_stores):
    static = MapFetcher(_sitemap_dealer())

    async def boom(domain, country, urls, is_e07):
        raise RuntimeError("redis down")

    r = _run(harvest_dealer(
        "dealer.example", "de", static_fetcher=static, e07_fetcher=None,
        seam_runner=boom, purger=_recording_purger(),
    ))
    assert r.web_type == "error" and r.error and "redis down" in r.error
    assert r.persisted == 0  # batch can continue


# ── aggregation ───────────────────────────────────────────────────────────────────
@pytest.mark.unit
def test_aggregate_rolls_up_by_type_and_country():
    results = [
        DealerHarvestResult("a.de", "DE", "sitemap_listing", "sitemap", 10, 10, 10, True, 1.0),
        DealerHarvestResult("b.fr", "FR", "playwright_meta", "sitemap", 5, 5, 3, True, 0.6),
        DealerHarvestResult("c.nl", "NL", "none", "none", 0, 0, 0, False, 0.0),
    ]
    agg = aggregate(results)
    assert agg["dealers"] == 3 and agg["yielding_dealers"] == 2
    assert agg["total_inventory"] == 13
    assert agg["by_web_type"]["sitemap_listing"]["inventory"] == 10
    assert agg["by_web_type"]["playwright_meta"]["yielding"] == 1
    assert agg["by_country"]["DE"]["inventory"] == 10


@pytest.mark.unit
def test_make_dealer_fetcher_is_callable_with_aclose():
    f = hv.make_dealer_fetcher()
    assert callable(f) and hasattr(f, "aclose")
