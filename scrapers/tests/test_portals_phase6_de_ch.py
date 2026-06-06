"""
Phase-6 DE/CH portal scraper tests — autoboerse.de, carvago.com.

Each portal is exercised against a fake duck-typed session (no curl_cffi):
partition_params grid, subdivide_segment termination, _build_url request
shaping, _extract parsing + dedup, fetch_segment retry / status handling.
Registry and domain_map wiring are also asserted to catch drift.

Coroutines run synchronously via asyncio.run() (engine convention).
fetch_segment tests stub _retry_backoff to no-op so the suite never sleeps.
"""
from __future__ import annotations

import asyncio
import json as _json
from typing import Any

import pytest

from scrapers.engine.router.domain_map import Tier, WAF
from scrapers.engine.router.domain_map import get as domain_get
from scrapers.portals import get_scraper
from scrapers.portals.base import BasePortalScraper


def _run(coro: Any) -> Any:
    return asyncio.run(coro)


# --------------------------------------------------------------------------- #
# fakes — duck-typed session matching the Phase-2 contract
# --------------------------------------------------------------------------- #
class _Resp:
    """Minimal duck-typed HTTP response (curl_cffi shape: .status_code, .text)."""

    def __init__(self, status_code: int, text: str = "") -> None:
        self.status_code = status_code
        self.text = text


class _Session:
    """Fake AsyncSession yielding queued responses (or raising queued exceptions)."""

    def __init__(self, responses: list[Any]) -> None:
        self._responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    @property
    def urls(self) -> list[str]:
        return [c["url"] for c in self.calls]

    def _next(self) -> _Resp:
        item = self._responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    async def get(self, url: str, timeout: int | None = None) -> _Resp:
        self.calls.append({"method": "GET", "url": url})
        return self._next()


def _no_backoff(scraper: BasePortalScraper) -> None:
    """Stub exponential backoff so retry tests run instantly."""

    async def _noop(attempt: int, factor: float = 1.0) -> None:
        return None

    scraper._retry_backoff = _noop  # type: ignore[method-assign]


# =========================================================================== #
# autoboerse.de — migrado al sitemap de listings (multi-strategy 2026-06)
# =========================================================================== #
from scrapers.portals.autoboerse_de import AutoboerseDEScraper
from scrapers.portals.sitemap_listing_base import SitemapListingScraper


@pytest.mark.unit
def test_autoboerse_is_sitemap_based() -> None:
    s = AutoboerseDEScraper()
    assert isinstance(s, SitemapListingScraper)
    assert s.SITEMAP_URL == "https://www.autoboerse.de/sitemap.xml"
    # detail = /fahrzeugsuche/{slug}/{id}; the 1-segment search page is excluded
    assert s.DETAIL_RE.search("/fahrzeugsuche/citroen-c3-benzin-sachsen-anhalt/rYP87WWOxJEo")
    assert not s.DETAIL_RE.search("/fahrzeugsuche/audi/")
    s._validate()


# -- wiring --------------------------------------------------------------------
@pytest.mark.unit
def test_autoboerse_registry_resolves() -> None:
    scraper = get_scraper("autoboerse.de")
    assert isinstance(scraper, AutoboerseDEScraper)
    assert scraper.DOMAIN == "autoboerse.de"


@pytest.mark.unit
def test_autoboerse_domain_map_baseline() -> None:
    spec = domain_get("autoboerse.de")
    assert spec is not None, "autoboerse.de missing from REGISTRY"
    assert spec.tier is Tier.T1
    assert spec.waf is WAF.NONE
    assert "DE" in spec.countries


# =========================================================================== #
# carvago.com — Next.js CSR, pan-European marketplace (T1)
# =========================================================================== #
from scrapers.portals.carvago_com import CarvagoCOMScraper

# SSR HTML stub with buildId in __NEXT_DATA__
_CARVAGO_HTML = '<script id="__NEXT_DATA__" type="application/json">{"buildId":"cBuild42xyz","props":{}}</script>'

# Data route JSON stub — dehydrated state pattern (React Query)
_CARVAGO_DATA_DEHYDRATED = _json.dumps({
    "pageProps": {
        "dehydratedState": {
            "queries": [{
                "state": {
                    "data": {
                        "listings": {
                            "edges": [
                                {"node": {"id": "car-001", "slug": "skoda-octavia-2020", "url": "/cars/skoda/octavia/car-001"}},
                                {"node": {"id": "car-002", "slug": "skoda-fabia-2019", "url": "/cars/skoda/fabia/car-002"}},
                                {"node": {"id": "car-001", "slug": "skoda-octavia-2020", "url": "/cars/skoda/octavia/car-001"}},  # dup
                            ]
                        }
                    }
                }
            }]
        }
    }
})

_CARVAGO_DEHYDRATED_EXPECTED = [
    "https://carvago.com/cars/skoda/octavia/car-001",
    "https://carvago.com/cars/skoda/fabia/car-002",
]

# Data route JSON stub — flat props pattern
_CARVAGO_DATA_FLAT = _json.dumps({
    "pageProps": {
        "searchResults": {
            "items": [
                {"id": "v-100", "detailUrl": "/de/autos/volkswagen/golf/v-100"},
                {"id": "v-200", "detailUrl": "/de/autos/bmw/3er/v-200"},
            ]
        }
    }
})

_CARVAGO_FLAT_EXPECTED = [
    "https://carvago.com/de/autos/volkswagen/golf/v-100",
    "https://carvago.com/de/autos/bmw/3er/v-200",
]


# -- partition_params ----------------------------------------------------------
@pytest.mark.unit
def test_carvago_partition_shape() -> None:
    scraper = CarvagoCOMScraper()
    segments = scraper.partition_params()
    assert len(segments) == len(scraper.MAKES)
    makes = [s["make"] for s in segments]
    assert len(set(makes)) == len(makes), "duplicates in make partition"
    assert "MAKE_VOLKSWAGEN" in makes
    assert "MAKE_BMW" in makes
    assert not any("_fine" in s for s in segments)


# -- subdivide_segment --------------------------------------------------------
@pytest.mark.unit
def test_carvago_subdivide_then_stops() -> None:
    scraper = CarvagoCOMScraper()
    subs = scraper.subdivide_segment({"make": "MAKE_SKODA"})
    assert subs
    assert len(subs) == len(scraper.PRICE_BANDS)
    for s in subs:
        assert s["make"] == "MAKE_SKODA"
        assert s["_fine"] is True
    assert scraper.subdivide_segment(subs[0]) == []


# -- _build_data_url -----------------------------------------------------------
@pytest.mark.unit
def test_carvago_build_data_url_basic() -> None:
    scraper = CarvagoCOMScraper()
    scraper._build_id = "cBuild42xyz"
    url = scraper._build_data_url({"make": "MAKE_AUDI"}, 1)
    assert "/_next/data/cBuild42xyz/de/autos.json" in url
    assert "make[]=MAKE_AUDI" in url
    assert "page=1" in url
    assert "limit=20" in url


@pytest.mark.unit
def test_carvago_build_data_url_with_price() -> None:
    scraper = CarvagoCOMScraper()
    scraper._build_id = "testBuild"
    params = {"make": "MAKE_BMW", "price_min": 10_000, "price_max": 20_000, "_fine": True}
    url = scraper._build_data_url(params, 5)
    assert "price-from=10000" in url
    assert "price-to=20000" in url
    assert "page=5" in url


@pytest.mark.unit
def test_carvago_build_data_url_open_price_band() -> None:
    scraper = CarvagoCOMScraper()
    scraper._build_id = "testBuild"
    params = {"make": "MAKE_PORSCHE", "price_min": 50_000, "price_max": None, "_fine": True}
    url = scraper._build_data_url(params, 1)
    assert "price-from=50000" in url
    assert "price-to" not in url


# -- _extract (dehydrated state pattern) --------------------------------------
@pytest.mark.unit
def test_carvago_extract_dehydrated() -> None:
    urls = CarvagoCOMScraper()._extract(_CARVAGO_DATA_DEHYDRATED)
    assert urls == _CARVAGO_DEHYDRATED_EXPECTED


# -- _extract (flat props pattern) --------------------------------------------
@pytest.mark.unit
def test_carvago_extract_flat_props() -> None:
    urls = CarvagoCOMScraper()._extract(_CARVAGO_DATA_FLAT)
    assert urls == _CARVAGO_FLAT_EXPECTED


# -- _extract (URL scan fallback) ---------------------------------------------
@pytest.mark.unit
def test_carvago_extract_url_scan() -> None:
    """When structured extraction fails, regex finds URLs in raw JSON."""
    raw = _json.dumps({
        "pageProps": {
            "unknownShape": "data",
            "html": '<a href="/cars/ford/focus/abc-123">Ford</a> <a href="/de/autos/audi/a3/xyz-456">Audi</a>'
        }
    })
    urls = CarvagoCOMScraper()._extract(raw)
    assert len(urls) == 2
    assert any("ford/focus/abc-123" in u for u in urls)
    assert any("audi/a3/xyz-456" in u for u in urls)


# -- _extract empty / garbage -------------------------------------------------
@pytest.mark.unit
def test_carvago_extract_returns_empty_on_garbage() -> None:
    assert CarvagoCOMScraper()._extract("") == []
    assert CarvagoCOMScraper()._extract("not json") == []
    assert CarvagoCOMScraper()._extract('{"pageProps": {}}') == []
    assert CarvagoCOMScraper()._extract('{"other": "data"}') == []


# -- fetch_segment behavioural matrix -----------------------------------------
@pytest.mark.unit
def test_carvago_fetch_segment_resolves_build_id_then_fetches() -> None:
    scraper = CarvagoCOMScraper()
    _no_backoff(scraper)
    session = _Session([
        _Resp(200, _CARVAGO_HTML),          # buildId resolution
        _Resp(200, _CARVAGO_DATA_DEHYDRATED),  # data fetch
    ])
    urls = _run(scraper.fetch_segment(session, {"make": "MAKE_SKODA"}, 1))
    assert urls == _CARVAGO_DEHYDRATED_EXPECTED
    assert len(session.calls) == 2
    assert "/de/autos" in session.urls[0]
    assert "/_next/data/cBuild42xyz/" in session.urls[1]


@pytest.mark.unit
def test_carvago_fetch_segment_caches_build_id() -> None:
    scraper = CarvagoCOMScraper()
    _no_backoff(scraper)
    session = _Session([
        _Resp(200, _CARVAGO_HTML),
        _Resp(200, _CARVAGO_DATA_DEHYDRATED),
        _Resp(200, _CARVAGO_DATA_DEHYDRATED),
    ])
    _run(scraper.fetch_segment(session, {"make": "MAKE_SKODA"}, 1))
    urls2 = _run(scraper.fetch_segment(session, {"make": "MAKE_BMW"}, 2))
    assert urls2 == _CARVAGO_DEHYDRATED_EXPECTED
    assert len(session.calls) == 3
    assert "/_next/data/" in session.urls[2]


@pytest.mark.unit
def test_carvago_fetch_segment_retries_block_then_gives_up() -> None:
    scraper = CarvagoCOMScraper()
    scraper._build_id = "cached"
    _no_backoff(scraper)
    session = _Session([_Resp(429), _Resp(503), _Resp(403)])
    assert _run(scraper.fetch_segment(session, {"make": "MAKE_AUDI"}, 1)) == []
    assert len(session.calls) == scraper.RETRY_ATTEMPTS


@pytest.mark.unit
def test_carvago_fetch_segment_recovers_after_block() -> None:
    scraper = CarvagoCOMScraper()
    scraper._build_id = "cached"
    _no_backoff(scraper)
    session = _Session([_Resp(503), _Resp(200, _CARVAGO_DATA_DEHYDRATED)])
    assert _run(scraper.fetch_segment(session, {"make": "MAKE_FORD"}, 1)) == _CARVAGO_DEHYDRATED_EXPECTED


@pytest.mark.unit
def test_carvago_fetch_segment_404_re_resolves_build_id() -> None:
    scraper = CarvagoCOMScraper()
    scraper._build_id = "stale"
    _no_backoff(scraper)
    session = _Session([
        _Resp(404),
        _Resp(200, _CARVAGO_HTML),
        _Resp(200, _CARVAGO_DATA_DEHYDRATED),
    ])
    urls = _run(scraper.fetch_segment(session, {"make": "MAKE_SKODA"}, 1))
    assert urls == _CARVAGO_DEHYDRATED_EXPECTED
    assert scraper._build_id == "cBuild42xyz"


@pytest.mark.unit
def test_carvago_fetch_segment_transport_error_retries() -> None:
    scraper = CarvagoCOMScraper()
    scraper._build_id = "cached"
    _no_backoff(scraper)
    session = _Session([ConnectionError("reset"), _Resp(200, _CARVAGO_DATA_DEHYDRATED)])
    assert _run(scraper.fetch_segment(session, {"make": "MAKE_KIA"}, 1)) == _CARVAGO_DEHYDRATED_EXPECTED


@pytest.mark.unit
def test_carvago_fetch_segment_non_retryable_status() -> None:
    scraper = CarvagoCOMScraper()
    scraper._build_id = "cached"
    session = _Session([_Resp(410)])
    assert _run(scraper.fetch_segment(session, {"make": "MAKE_OPEL"}, 1)) == []
    assert len(session.calls) == 1


# -- wiring --------------------------------------------------------------------
@pytest.mark.unit
def test_carvago_registry_resolves() -> None:
    scraper = get_scraper("carvago.com")
    assert isinstance(scraper, CarvagoCOMScraper)
    assert scraper.DOMAIN == "carvago.com"


@pytest.mark.unit
def test_carvago_domain_map_baseline() -> None:
    spec = domain_get("carvago.com")
    assert spec is not None, "carvago.com missing from REGISTRY"
    assert spec.tier is Tier.T1
    assert spec.waf is WAF.NONE
    assert "DE" in spec.countries or "EU" in spec.countries
