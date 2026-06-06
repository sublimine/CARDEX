"""
Tests for Phase 13 portal scrapers — truckscout24.com, classic-trader.com.

Both were migrated to the listing-level sitemap (multi-strategy 2026-06): their
detail-URL harvest, gzip and index-recursion behaviour is covered centrally in
test_sitemap_listing.py. Here we pin the per-portal contract: registry resolution
and the sitemap config (entry, child filter, detail matcher).
"""
from __future__ import annotations

import pytest

from scrapers.portals import get_scraper
from scrapers.portals.classic_trader_com import ClassicTraderDEScraper
from scrapers.portals.sitemap_listing_base import SitemapListingScraper
from scrapers.portals.truckscout24_com import TruckScout24DEScraper


@pytest.mark.unit
def test_truckscout24_is_sitemap_based() -> None:
    s = get_scraper("truckscout24.com")
    assert isinstance(s, TruckScout24DEScraper)
    assert isinstance(s, SitemapListingScraper)
    assert s.COUNTRY == "DE"
    assert s.SITEMAP_URL == "https://www.truckscout24.com/sitemap.xml"
    assert s.CHILD_RE.search("/data/sitemaps/b_ts_en_US/sitemap_listing_1.xml.gz")
    assert not s.CHILD_RE.search("/data/sitemaps/b_ts_en_US/sitemap_deleted-listing_1.xml.gz")
    assert s.DETAIL_RE.search("/tsp/ts-396-57-89")
    assert s.SITEMAP_FETCH_DELAY >= 5.0  # robots.txt Crawl-delay: 5
    s._validate()


@pytest.mark.unit
def test_classic_trader_is_sitemap_based() -> None:
    s = get_scraper("classic-trader.com")
    assert isinstance(s, ClassicTraderDEScraper)
    assert isinstance(s, SitemapListingScraper)
    assert s.COUNTRY == "DE"
    assert s.SITEMAP_URL == "https://cdn.classic-trader.com/I/sitemap/sitemap.xml"
    assert s.CHILD_RE.search("/I/sitemap/sitemap.de.car.listing_0.xml")
    assert not s.CHILD_RE.search("/I/sitemap/sitemap.de.motorbike.listing.xml")
    assert s.DETAIL_RE.search("/de/automobile/inserat/bentley/6-1-2-liter/6-1-2-liter/1931/2543")
    assert not s.DETAIL_RE.search("/de/automobile/angebote/old-broken-path")
    s._validate()
