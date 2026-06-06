"""
Phase-9 portal scraper tests — gowago.ch, gueudet.fr, distinxion.fr.

All three were migrated to the listing-level sitemap (multi-strategy 2026-06); the
harvest/gzip/index-recursion mechanics are covered centrally in
test_sitemap_listing.py. Here we pin per-portal wiring (portal registry +
domain_map tier) and the sitemap config (entry, child filter, detail matcher).
"""
from __future__ import annotations

import pytest

from scrapers.engine.router.domain_map import Tier, WAF
from scrapers.engine.router.domain_map import get as domain_get
from scrapers.portals import get_scraper
from scrapers.portals.distinxion_fr import DistinxionFRScraper
from scrapers.portals.gowago_ch import GowagoCHScraper
from scrapers.portals.gueudet_fr import GueudetFRScraper
from scrapers.portals.sitemap_listing_base import SitemapListingScraper


@pytest.mark.unit
def test_gowago_wiring_and_sitemap_config() -> None:
    s = get_scraper("gowago.ch")
    assert isinstance(s, GowagoCHScraper)
    assert isinstance(s, SitemapListingScraper)
    assert s.DOMAIN == "gowago.ch" and s.COUNTRY == "CH"
    spec = domain_get("gowago.ch")
    assert spec.tier is Tier.T1 and spec.waf is WAF.NONE
    assert s.SITEMAP_URL == "https://gowago.ch/sitemap/sitemap-index.xml"
    assert s.CHILD_RE.search("/sitemap/products-sitemap-0.xml")
    assert not s.CHILD_RE.search("/sitemap/sitemap-0.xml")  # static pages skipped
    assert s.DETAIL_RE.search("/en/listing/ford-puma/8EAA4E82")
    assert not s.DETAIL_RE.search("/de/listing/vw-golf/42A2AD2D")  # one locale only
    s._validate()


@pytest.mark.unit
def test_gueudet_wiring_and_sitemap_config() -> None:
    s = get_scraper("gueudet.fr")
    assert isinstance(s, GueudetFRScraper)
    assert isinstance(s, SitemapListingScraper)
    assert s.DOMAIN == "gueudet.fr" and s.COUNTRY == "FR"
    spec = domain_get("gueudet.fr")
    assert spec.tier is Tier.T1 and spec.waf is WAF.NONE
    assert s.SITEMAP_URL == "https://www.gueudet.fr/storage/sitemap.xml"
    assert s.CHILD_RE.search("/storage/sitemap-vehicles.xml")
    assert not s.CHILD_RE.search("/storage/sitemap-pages.xml")
    assert s.DETAIL_RE.search("/voiture/demonstration/bmw/serie-1/116-122-ch/105520")
    s._validate()


@pytest.mark.unit
def test_distinxion_wiring_and_sitemap_config() -> None:
    s = get_scraper("distinxion.fr")
    assert isinstance(s, DistinxionFRScraper)
    assert isinstance(s, SitemapListingScraper)
    assert s.DOMAIN == "distinxion.fr" and s.COUNTRY == "FR"
    spec = domain_get("distinxion.fr")
    assert spec.tier is Tier.T1 and spec.waf is WAF.NONE
    assert s.SITEMAP_URL == "https://www.distinxion.fr/sitemap.xml"
    assert s.CHILD_RE.search("/sitemap.catalog.xml")
    # detail = /voitures/{brand}/{model}/{numeric_id}; category pages excluded
    assert s.DETAIL_RE.search("/voitures/nissan/juke/765244")
    assert not s.DETAIL_RE.search("/voitures/nissan")
    s._validate()


@pytest.mark.unit
class TestPhase9RegistryCompleteness:
    """All Phase 9 portals must be in both portal registry and domain_map."""

    PHASE9_DOMAINS = ("gowago.ch", "gueudet.fr", "distinxion.fr")

    def test_all_in_portal_registry(self) -> None:
        for domain in self.PHASE9_DOMAINS:
            s = get_scraper(domain)
            assert s is not None, f"{domain} missing from PORTAL_REGISTRY"
            assert s.DOMAIN == domain

    def test_all_in_domain_map(self) -> None:
        for domain in self.PHASE9_DOMAINS:
            spec = domain_get(domain)
            assert spec is not None, f"{domain} missing from domain_map REGISTRY"
            assert spec.tier in (Tier.T0, Tier.T1)
