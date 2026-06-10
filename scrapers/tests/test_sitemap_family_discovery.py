"""
Recipe-pinned sitemap discovery — the family-multiplier's last link (frente C).

A sitemap-strategy family recipe (e.g. datamotive) declares ``/sitemap.xml`` which
is a <sitemapindex> pointing at flat vehicle shards whose detail paths carry NO
vehicle token (``/p/<slug>-<id>``) — so the generic cascade's token-filtered
sitemap layer enumerates 0 and degrades to a handful of catalog links. These tests
prove ``discover_dealer_urls`` now walks the DECLARED sitemap recursively, filters
by the recipe ``detail_url_re``, falls back to the generic cascade when the walk
yields nothing, and leaves every non-sitemap / no-regex recipe IDENTICAL to before.

All in memory (map fetchers), AAA, repo convention — no network, no stores.
"""
from __future__ import annotations

import asyncio
import gzip
import json
from pathlib import Path

import pytest

from scrapers.dealer_scraping import harvester as hv
from scrapers.dealer_scraping.discovery import walk_sitemap
from scrapers.pipeline.generic_extractor import FetchResult
from scrapers.portals.config import Endpoints, ExtractionConfig, family_from_dict, instantiate_family

_REPO_ROOT = Path(__file__).resolve().parents[2]
_DATAMOTIVE_FAMILY = _REPO_ROOT / "configs" / "families" / "datamotive.json"


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


def _urlset(*locs: str) -> bytes:
    body = "".join(f"<url><loc>{u}</loc></url>" for u in locs)
    return _b(f"<urlset>{body}</urlset>")


def _index(*locs: str) -> bytes:
    body = "".join(f"<sitemap><loc>{u}</loc></sitemap>" for u in locs)
    return _b(f"<sitemapindex>{body}</sitemapindex>")


def _datamotive_cfg(host: str = "dealer.example") -> ExtractionConfig:
    """The REAL family file instantiated for a test host — covers the production regex."""
    recipe = family_from_dict(json.loads(_DATAMOTIVE_FAMILY.read_text(encoding="utf-8")))
    return instantiate_family(recipe, host, country="NL")


_P1 = "https://dealer.example/p/seat-arona-1-0-tsi-110pk-12345"
_P2 = "https://dealer.example/p/bmw-320d-touring-67890"
_P3 = "https://dealer.example/volkswagen/occasions/p/golf-8-1-5-tsi-99887"
_P4 = "https://dealer.example/p/audi-a4-2-0-tdi-54321"


def _datamotive_site() -> dict[str, tuple[int, bytes]]:
    """sitemapindex → 2 vehicle shards (one gzipped) + a pages shard + noise."""
    return {
        "https://dealer.example/sitemap.xml": (200, _index(
            "https://dealer.example/sitemaps/vehicle-1.xml",
            "https://dealer.example/sitemaps/vehicle-2.xml",
            "https://dealer.example/sitemaps/pages-1.xml",
        )),
        "https://dealer.example/sitemaps/vehicle-1.xml": (200, _urlset(
            _P1, _P2, _P3,
            "https://evil.example/p/off-site-decoy-666",   # same-site guard must drop it
        )),
        "https://dealer.example/sitemaps/vehicle-2.xml": (200, gzip.compress(_urlset(_P4))),
        "https://dealer.example/sitemaps/pages-1.xml": (200, _urlset(
            "https://dealer.example/pages/over-ons",
            "https://dealer.example/contact",
        )),
    }


def _recording_generic(details: list[str], method: str = "catalog_follow"):
    """Stand-in for the generic cascade — records calls, returns a fixed result."""
    calls: list[str] = []

    async def fake(domain, *, static_fetcher, e07_fetcher=None, cap=150):
        calls.append(domain)
        return list(details), method, "", ""

    fake.calls = calls
    return fake


# ── walk_sitemap (the recursive walker itself) ────────────────────────────────────
@pytest.mark.unit
def test_walk_sitemap_recurses_index_gunzips_and_dedups():
    # Arrange: index → 2 shards (one gzipped), a duplicate loc, and a self-cycle.
    pages = {
        "https://d.example/sitemap.xml": (200, _index(
            "https://d.example/sm/a.xml",
            "https://d.example/sm/b.xml.gz",
            "https://d.example/sitemap.xml",            # cycle — must not loop
        )),
        "https://d.example/sm/a.xml": (200, _urlset(
            "https://d.example/p/one-11", "https://d.example/p/two-22",
            "https://d.example/p/one-11",               # duplicate — emitted once
        )),
        "https://d.example/sm/b.xml.gz": (200, gzip.compress(_urlset("https://d.example/p/three-33"))),
    }
    fetcher = MapFetcher(pages)

    # Act
    urls = _run(walk_sitemap(fetcher, "https://d.example/sitemap.xml", cap=100))

    # Assert: every loc exactly once, both levels walked, gzip shard decoded.
    assert urls == [
        "https://d.example/p/one-11",
        "https://d.example/p/two-22",
        "https://d.example/p/three-33",
    ]


@pytest.mark.unit
def test_walk_sitemap_cap_counts_kept_urls_not_raw():
    # Arrange: the NOISE shard comes first — a raw-URL cap would exhaust on it.
    pages = {
        "https://d.example/sitemap.xml": (200, _index(
            "https://d.example/sm/pages.xml", "https://d.example/sm/vehicles.xml",
        )),
        "https://d.example/sm/pages.xml": (200, _urlset(
            *(f"https://d.example/pages/noise-{i}" for i in range(10)),
        )),
        "https://d.example/sm/vehicles.xml": (200, _urlset(
            "https://d.example/p/one-11", "https://d.example/p/two-22", "https://d.example/p/three-33",
        )),
    }
    fetcher = MapFetcher(pages)

    # Act: keep only /p/ detail urls, cap at 2 KEPT.
    urls = _run(walk_sitemap(
        fetcher, "https://d.example/sitemap.xml", cap=2, keep=lambda u: "/p/" in u,
    ))

    # Assert: the cap budget was not consumed by the noise shard.
    assert urls == ["https://d.example/p/one-11", "https://d.example/p/two-22"]


@pytest.mark.unit
def test_walk_sitemap_bounded_by_max_sitemaps():
    # Arrange: an index fanning out to many shards; only the first N may be fetched.
    shards = [f"https://d.example/sm/s{i}.xml" for i in range(10)]
    pages = {"https://d.example/sitemap.xml": (200, _index(*shards))}
    for i, s in enumerate(shards):
        pages[s] = (200, _urlset(f"https://d.example/p/car-{i}-{i}0"))
    fetcher = MapFetcher(pages)

    # Act: max_sitemaps=3 → the index + 2 shards.
    urls = _run(walk_sitemap(fetcher, "https://d.example/sitemap.xml", cap=100, max_sitemaps=3))

    # Assert
    assert urls == ["https://d.example/p/car-0-00", "https://d.example/p/car-1-10"]
    assert len(fetcher.requested) == 3


# ── discover_dealer_urls: the recipe-sitemap branch ───────────────────────────────
@pytest.mark.unit
def test_discover_recipe_sitemap_walks_index_and_filters(monkeypatch):
    # Arrange: REAL datamotive family recipe instantiated for the host; the generic
    # cascade is a tripwire that must NOT be touched when the walk succeeds.
    cfg = _datamotive_cfg()
    assert cfg.strategy == "sitemap_listing" and cfg.endpoints.sitemap_url
    fetcher = MapFetcher(_datamotive_site())
    generic = _recording_generic(["https://dealer.example/aanbod"])
    monkeypatch.setattr(hv, "discover_detail_urls", generic)

    # Act
    urls = _run(hv.discover_dealer_urls("dealer.example", cfg, static_fetcher=fetcher))

    # Assert: ONLY the /p/<slug>-<id> vehicle pages (incl. the brand-prefixed form),
    # recursed through the index, gzip shard included, off-site decoy + /pages dropped.
    assert urls == [_P1, _P2, _P3, _P4]
    assert generic.calls == []                      # generic cascade never invoked
    assert "https://dealer.example/sitemap.xml" in fetcher.requested
    assert "https://dealer.example/sitemaps/vehicle-2.xml" in fetcher.requested


@pytest.mark.unit
def test_discover_recipe_sitemap_respects_cap():
    # Arrange
    cfg = _datamotive_cfg()
    fetcher = MapFetcher(_datamotive_site())

    # Act
    urls = _run(hv.discover_dealer_urls("dealer.example", cfg, static_fetcher=fetcher, cap=2))

    # Assert
    assert urls == [_P1, _P2]


@pytest.mark.unit
def test_discover_empty_sitemap_falls_back_to_generic(monkeypatch):
    # Arrange: the declared sitemap exists but lists only non-vehicle pages → the
    # walk keeps 0 and the generic cascade must take over (never zero a dealer).
    cfg = _datamotive_cfg()
    fetcher = MapFetcher({
        "https://dealer.example/sitemap.xml": (200, _urlset(
            "https://dealer.example/pages/over-ons", "https://dealer.example/contact",
        )),
    })
    fallback = ["https://dealer.example/aanbod"]
    generic = _recording_generic(fallback)
    monkeypatch.setattr(hv, "discover_detail_urls", generic)

    # Act
    urls = _run(hv.discover_dealer_urls("dealer.example", cfg, static_fetcher=fetcher))

    # Assert: fell through to the cascade; its result survives the fail-loud
    # regex filter (matched 0 → keep unfiltered) so the dealer is not zeroed.
    assert generic.calls == ["dealer.example"]
    assert urls == fallback


@pytest.mark.unit
def test_discover_unreachable_sitemap_falls_back_to_generic(monkeypatch):
    # Arrange: the declared sitemap 404s outright.
    cfg = _datamotive_cfg()
    fetcher = MapFetcher({})                        # everything 404s
    fallback = ["https://dealer.example/aanbod"]
    generic = _recording_generic(fallback)
    monkeypatch.setattr(hv, "discover_detail_urls", generic)

    # Act
    urls = _run(hv.discover_dealer_urls("dealer.example", cfg, static_fetcher=fetcher))

    # Assert
    assert generic.calls == ["dealer.example"] and urls == fallback


# ── discover_dealer_urls: non-sitemap / no-regex recipes stay IDENTICAL ──────────
@pytest.mark.unit
def test_discover_non_sitemap_recipe_never_walks(monkeypatch):
    # Arrange: a jsonld_detail recipe that even carries a sitemap_url + detail_url_re
    # — the strategy gate alone must keep it on the generic cascade.
    cfg = ExtractionConfig(
        source_key="dealer.example", country="NL", strategy="jsonld_detail",
        endpoints=Endpoints(
            host="www.dealer.example",
            sitemap_url="https://dealer.example/sitemap.xml",
            detail_url_re=r"/vehicles/.+-\d+$",
        ),
    )
    fetcher = MapFetcher(_datamotive_site())
    generic = _recording_generic([
        "https://dealer.example/vehicles/bmw-320d-1", "https://dealer.example/aanbod",
    ])
    monkeypatch.setattr(hv, "discover_detail_urls", generic)

    # Act
    urls = _run(hv.discover_dealer_urls("dealer.example", cfg, static_fetcher=fetcher))

    # Assert: generic path + regex filter, exactly the pre-fix behavior; the
    # declared sitemap was never fetched.
    assert generic.calls == ["dealer.example"]
    assert urls == ["https://dealer.example/vehicles/bmw-320d-1"]
    assert fetcher.requested == []


@pytest.mark.unit
def test_discover_sitemap_strategy_without_detail_re_never_walks(monkeypatch):
    # Arrange: the detector-built per-dealer shape — sitemap_listing + sitemap_url
    # but NO detail_url_re (``build_config`` never sets one). Must stay generic.
    cfg = ExtractionConfig(
        source_key="dealer.example", country="NL", strategy="sitemap_listing",
        endpoints=Endpoints(
            host="www.dealer.example",
            sitemap_url="https://dealer.example/sitemap.xml",
        ),
    )
    fetcher = MapFetcher(_datamotive_site())
    expected = ["https://dealer.example/vehicles/bmw-320d-1"]
    generic = _recording_generic(expected, method="sitemap")
    monkeypatch.setattr(hv, "discover_detail_urls", generic)

    # Act
    urls = _run(hv.discover_dealer_urls("dealer.example", cfg, static_fetcher=fetcher))

    # Assert: unfiltered generic result, no sitemap fetch — identical to before.
    assert generic.calls == ["dealer.example"] and urls == expected
    assert fetcher.requested == []


@pytest.mark.unit
def test_recipe_sitemap_url_built_from_host_when_only_a_hint():
    # Arrange: a bare path (hint-shaped) instead of an absolute sitemap_url.
    cfg = ExtractionConfig(
        source_key="dealer.example", country="NL", strategy="sitemap_listing",
        endpoints=Endpoints(host="www.dealer.example", sitemap_url="/sitemap.xml"),
    )

    # Act / Assert
    assert hv._recipe_sitemap_url("dealer.example", cfg) == "https://dealer.example/sitemap.xml"
    abs_cfg = _datamotive_cfg()
    assert hv._recipe_sitemap_url("dealer.example", abs_cfg) == abs_cfg.endpoints.sitemap_url
