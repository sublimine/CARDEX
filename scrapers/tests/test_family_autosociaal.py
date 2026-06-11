"""autosociaal (Dealertemplates) family — offline tests against REAL captures.

Fixtures in ``fixtures/autosociaal/`` (captured 2026-06-11, 3 polite GETs, then
trimmed with byte-parity asserts on everything the parser reads):
  * jvd_occasions_p1.html      — real janvandijk.nl/occasions page 1 (15 cards,
                                 wire:snapshot count=27, perPage=15, site nav).
  * jvd_occasions_p2_full.html — real ?page=2: CUMULATIVE full set, 27/27 cards.
  * gvt_occasions_404.html     — real garagevantreuren.nl/occasions 404 body
                                 (its slug differs → candidate-fallback path).
  * jvd_sitemap_SYNTHETIC.xml  — flat urlset built from the 27 REAL PDP URLs
                                 (live sitemap not captured; format per
                                 lieutenant live verification 2026-06-10).
  * jvd_zero_stock_DERIVED.html— real p1 with count edited 27→0, cards removed
                                 (real 0-stock page not capturable in budget).

No network anywhere: the harvester takes an injected MapFetcher.
"""
from __future__ import annotations

import asyncio
import re
from pathlib import Path

import pytest

from scrapers.dealer_scraping.family_autosociaal import (
    CANDIDATE_SLUGS,
    discover_slug_from_nav,
    discover_slug_from_sitemap,
    harvest_autosociaal,
    is_catalog_page,
    parse_listing_cards,
    parse_occasions_count,
    parse_per_page,
)
from scrapers.pipeline.generic_extractor import FetchResult
from scrapers.portals import config as cfgmod

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "autosociaal"
BASE = "https://janvandijk.nl"


def _fx(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def _fx_b(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


def _run(coro):
    return asyncio.run(coro)


# ── in-memory transport (repo convention, mirrors test_dealer_harvester) ────────
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


class Always404Fetcher:
    """Serves the REAL platform 404 body for every URL (gvt wrong-slug capture)."""

    def __init__(self, body: bytes):
        self._body = body
        self.requested: list[str] = []

    async def __call__(self, url: str) -> FetchResult:
        self.requested.append(url)
        return FetchResult(url=url, status_code=404, body=self._body)


# ── availability count (wire:snapshot first, visible heading as fallback) ───────
@pytest.mark.unit
def test_parse_count_and_per_page_from_real_snapshot():
    # Arrange
    html = _fx("jvd_occasions_p1.html")

    # Act / Assert — snapshot count == lieutenant-verified availability truth
    assert parse_occasions_count(html) == 27
    assert parse_per_page(html) == 15
    assert is_catalog_page(html) is True


@pytest.mark.unit
def test_count_falls_back_to_visible_heading():
    # Arrange — no wire:snapshot at all, only the visible h2
    html = "<html><body><h2>Er zijn 5 voertuigen gevonden</h2></body></html>"

    # Act / Assert
    assert parse_occasions_count(html) == 5
    assert parse_occasions_count("<html><body>geen grid</body></html>") is None


# ── cards: the cumulative ?page=last IS the whole live set ──────────────────────
@pytest.mark.unit
def test_full_cumulative_page_parses_exactly_count_cards():
    # Arrange
    html = _fx("jvd_occasions_p2_full.html")
    total = parse_occasions_count(html)

    # Act
    listings = parse_listing_cards(html, BASE)

    # Assert — N cards == filteredOccasionsCount, unique deep links, cage shape
    assert total == 27
    assert len(listings) == total
    urls = [li["url"] for li in listings]
    assert len(set(urls)) == len(urls)
    rx = re.compile(cfgmod.load_family("autosociaal").endpoints.detail_url_re)
    for li in listings:
        assert set(li.keys()) == {"url", "title", "price", "year", "km"}
        assert rx.match(li["url"]), li["url"]
        assert li["title"] and li["price"]


@pytest.mark.unit
def test_page1_is_a_prefix_not_the_full_set():
    # Arrange — page 1 carries perPage cards while the count says more exist
    html = _fx("jvd_occasions_p1.html")

    # Act
    listings = parse_listing_cards(html, BASE)

    # Assert — this is WHY the harvester must GET ?page=ceil(total/15)
    assert len(listings) == 15
    assert parse_occasions_count(html) == 27


@pytest.mark.unit
def test_real_card_fields_make_model_price_year_km():
    # Arrange — the Honda HR-V card (wire:key 7378626) from the real capture
    listings = parse_listing_cards(_fx("jvd_occasions_p2_full.html"), BASE)

    # Act
    card = next(li for li in listings
                if li["url"] == "https://janvandijk.nl/occasions/honda/hr-v/7378626")

    # Assert — values read live 2026-06-11: € 29.250,- · 2022 · 34.061 km
    assert card["title"] == "Honda HR-V"
    assert card["price"] == 29250
    assert card["year"] == 2022
    assert card["km"] == 34061


# ── slug discovery: sitemap PDP prefix → home nav → candidates ──────────────────
@pytest.mark.unit
def test_discover_slug_from_sitemap_pdp_prefix():
    # Arrange — flat urlset with the 27 real PDP URLs + real static pages
    xml = _fx("jvd_sitemap_SYNTHETIC.xml")

    # Act / Assert — only PDP-shaped paths vote, static pages never pollute
    assert discover_slug_from_sitemap(xml) == "occasions"
    assert discover_slug_from_sitemap("<urlset></urlset>") is None


@pytest.mark.unit
def test_discover_slug_from_real_nav():
    # Arrange — the real page nav carries the one-segment catalog link
    html = _fx("jvd_occasions_p1.html")

    # Act / Assert
    assert discover_slug_from_nav(html) == "occasions"
    assert discover_slug_from_nav("<nav><a href='/contact'>x</a></nav>") is None


# ── harvest: end-to-end against fixtures, no network ────────────────────────────
@pytest.mark.unit
def test_harvest_end_to_end_one_cumulative_page_request():
    # Arrange
    fetcher = MapFetcher({
        f"{BASE}/sitemap.xml": (200, _fx_b("jvd_sitemap_SYNTHETIC.xml")),
        f"{BASE}/occasions": (200, _fx_b("jvd_occasions_p1.html")),
        f"{BASE}/occasions?page=2": (200, _fx_b("jvd_occasions_p2_full.html")),
    })

    # Act
    result = _run(harvest_autosociaal("janvandijk.nl", fetcher))

    # Assert — availability-first: count 27 == 27 listings, ONE ?page GET (the last)
    assert result["ok"] is True and result["complete"] is True
    assert result["slug"] == "occasions" and result["total"] == 27
    assert len(result["listings"]) == 27
    page_gets = [u for u in fetcher.requested if "?page=" in u]
    assert page_gets == [f"{BASE}/occasions?page=2"]
    assert not any("/honda/" in u for u in fetcher.requested)  # zero PDP fetches


@pytest.mark.unit
def test_harvest_discovers_slug_via_home_nav_when_sitemap_missing():
    # Arrange — no sitemap; the home document carries the real nav
    fetcher = MapFetcher({
        f"{BASE}/": (200, _fx_b("jvd_occasions_p1.html")),
        f"{BASE}/occasions": (200, _fx_b("jvd_occasions_p1.html")),
        f"{BASE}/occasions?page=2": (200, _fx_b("jvd_occasions_p2_full.html")),
    })

    # Act
    result = _run(harvest_autosociaal("janvandijk.nl", fetcher))

    # Assert — sitemap miss → home nav → catalog, same complete harvest
    assert result["ok"] is True and len(result["listings"]) == 27
    assert fetcher.requested[:3] == [f"{BASE}/sitemap.xml", f"{BASE}/", f"{BASE}/occasions"]


@pytest.mark.unit
def test_harvest_tolerates_zero_stock_dealer():
    # Arrange — same Livewire page shape with filteredOccasionsCount=0 (derived
    # from the real p1 capture; see fixture header for provenance)
    fetcher = MapFetcher({
        "https://dealer-zero.nl/occasions": (200, _fx_b("jvd_zero_stock_DERIVED.html")),
    })

    # Act
    result = _run(harvest_autosociaal("dealer-zero.nl", fetcher))

    # Assert — 0 stock is a VALID availability truth, never an error, no page walk
    assert result["ok"] is True and result["complete"] is True
    assert result["total"] == 0 and result["listings"] == []
    assert not any("?page=" in u for u in fetcher.requested)


@pytest.mark.unit
def test_harvest_wrong_slug_404s_fall_through_all_candidates():
    # Arrange — the REAL garagevantreuren 404 body for every URL (its catalog
    # slug is not /occasions; live capture 2026-06-11)
    fetcher = Always404Fetcher(_fx_b("gvt_occasions_404.html"))

    # Act
    result = _run(harvest_autosociaal("garagevantreuren.nl", fetcher))

    # Assert — clean miss, no exception, and every candidate slug was attempted
    assert result["ok"] is False and result["reason"] == "catalog_not_found"
    assert result["listings"] == [] and result["total"] is None
    for cand in CANDIDATE_SLUGS:
        assert f"https://garagevantreuren.nl/{cand}" in fetcher.requested


@pytest.mark.unit
def test_harvest_degrades_to_page1_when_last_page_fetch_fails():
    # Arrange — the cumulative last page is unreachable (transient 404)
    fetcher = MapFetcher({
        f"{BASE}/occasions": (200, _fx_b("jvd_occasions_p1.html")),
    })

    # Act
    result = _run(harvest_autosociaal("janvandijk.nl", fetcher))

    # Assert — page-1 cards survive, mismatch is REPORTED, never raised
    assert result["ok"] is True and result["complete"] is False
    assert result["reason"] == "count_mismatch"
    assert len(result["listings"]) == 15 and result["total"] == 27


# ── family recipe: loads, gates, and isolates PDPs ──────────────────────────────
@pytest.mark.unit
def test_autosociaal_recipe_loads_and_accepts_its_family():
    # Arrange / Act
    recipe = cfgmod.load_family("autosociaal")

    # Assert
    assert recipe is not None
    assert recipe.strategy == "html_listing"
    assert recipe.accepts("autosociaal", "medium")
    assert recipe.accepts("autosociaal", "high")
    assert not recipe.accepts("wordpress", "high")
    assert recipe.endpoints.catalog_path_tokens == ("occasions", "aanbod", "voorraad")
    assert recipe.provenance.verified_count == len(recipe.provenance.verified_on_dealers)


@pytest.mark.unit
def test_autosociaal_detail_re_isolates_pdps():
    # Arrange
    rx = re.compile(cfgmod.load_family("autosociaal").endpoints.detail_url_re)

    # Act / Assert — real PDP matches; roots, categories and CDN assets do not
    assert rx.match("https://janvandijk.nl/occasions/honda/hr-v/7378626")
    assert rx.match("https://janvandijk.nl/occasions/bmw/1-serie-f20/7369781")
    assert not rx.match("https://janvandijk.nl/occasions")
    assert not rx.match("https://janvandijk.nl/occasions/honda/hr-v")
    assert not rx.match("https://cdn.autosociaal.nl/dtweb/7378626/honda-hrv-0-abc_b400x300-1x.webp")
