"""
Phase-6 FR/BE portal scraper tests — autosphere.fr, auto-selection.com,
leparking.fr, annonces-automobile.com, starterre.fr, carizy.com,
cardoen.be, moniteurautomobile.be.

Cada portal se ejerce directamente contra una sesión fake duck-typed (sin curl_cffi):
partition_params grid, subdivide_segment terminación, _build_url/_build_body request
shaping, _extract parsing + dedup, fetch_segment retry / status handling. Dos capas
de wiring — portal registry (get_scraper) y domain→tier registry (domain_map).

Coroutines se ejecutan sincrónicamente vía asyncio.run() (convención del engine).
fetch_segment tests stub `_retry_backoff` a no-op para que la suite nunca duerma.
"""
from __future__ import annotations

import asyncio
import json
from typing import Any

import pytest

from scrapers.engine.router.domain_map import Tier, WAF
from scrapers.engine.router.domain_map import get as domain_get
from scrapers.portals import get_scraper
from scrapers.portals.base import BasePortalScraper


def _run(coro: Any) -> Any:
    return asyncio.run(coro)


# --------------------------------------------------------------------------- #
# fakes — sesión duck-typed que coincide con el contrato Phase-2
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

    async def post(
        self,
        url: str,
        data: str | None = None,
        headers: dict[str, str] | None = None,
        timeout: int | None = None,
    ) -> _Resp:
        self.calls.append({"method": "POST", "url": url, "data": data})
        return self._next()


def _no_backoff(scraper: BasePortalScraper) -> None:
    """Stub del exponential backoff para que los tests de retry corran al instante."""

    async def _noop(attempt: int, factor: float = 1.0) -> None:
        return None

    scraper._retry_backoff = _noop  # type: ignore[method-assign]


# =========================================================================== #
# autosphere.fr — API REST interne Next.js (T0)
# =========================================================================== #
from scrapers.portals.autosphere_fr import AutosphereFRScraper

_AUTOSPHERE_JSON = json.dumps({
    "results": [
        {"slug": "peugeot-308-occasion-12345", "id": 12345, "brand": "Peugeot"},
        {"slug": "renault-clio-occasion-67890", "id": 67890, "brand": "Renault"},
        {"slug": "peugeot-308-occasion-12345", "id": 12345, "brand": "Peugeot"},  # dup
    ],
    "total": 15600
})

_AUTOSPHERE_EXPECTED = [
    "https://www.autosphere.fr/recherche/peugeot-308-occasion-12345",
    "https://www.autosphere.fr/recherche/renault-clio-occasion-67890",
]


@pytest.mark.unit
def test_autosphere_partition_is_single_empty_segment() -> None:
    assert AutosphereFRScraper().partition_params() == [{}]


@pytest.mark.unit
def test_autosphere_subdivide_is_noop() -> None:
    assert AutosphereFRScraper().subdivide_segment({}) == []


@pytest.mark.unit
def test_autosphere_build_url_page1() -> None:
    scraper = AutosphereFRScraper()
    assert scraper._build_url(0) == (
        "https://www.autosphere.fr/api/stock/vehicles"
        "?voiture=occasion&sortField=popularity&sortDirection=asc"
        "&internal_type=vo,vd&size=100&from=0"
    )


@pytest.mark.unit
def test_autosphere_build_url_page3() -> None:
    scraper = AutosphereFRScraper()
    assert scraper._build_url(200) == (
        "https://www.autosphere.fr/api/stock/vehicles"
        "?voiture=occasion&sortField=popularity&sortDirection=asc"
        "&internal_type=vo,vd&size=100&from=200"
    )


@pytest.mark.unit
def test_autosphere_extract_pulls_slugs_and_dedups() -> None:
    assert AutosphereFRScraper()._extract(_AUTOSPHERE_JSON) == _AUTOSPHERE_EXPECTED


@pytest.mark.unit
def test_autosphere_extract_skips_items_without_slug() -> None:
    body = json.dumps({
        "results": [
            {"id": 1},
            {"slug": "", "id": 2},
            {"slug": "ok-item-999", "id": 3},
        ],
        "total": 3
    })
    assert AutosphereFRScraper()._extract(body) == [
        "https://www.autosphere.fr/recherche/ok-item-999",
    ]


@pytest.mark.unit
def test_autosphere_extract_returns_empty_on_garbage() -> None:
    assert AutosphereFRScraper()._extract("") == []
    assert AutosphereFRScraper()._extract("not json") == []
    assert AutosphereFRScraper()._extract('{"results": "not a list"}') == []
    assert AutosphereFRScraper()._extract('{"other": []}') == []


# -- fetch_segment behavioural matrix ------------------------------------------
@pytest.mark.unit
def test_autosphere_fetch_segment_extracts_on_200() -> None:
    scraper = AutosphereFRScraper()
    session = _Session([_Resp(200, _AUTOSPHERE_JSON)])
    assert _run(scraper.fetch_segment(session, {}, 1)) == _AUTOSPHERE_EXPECTED
    assert len(session.calls) == 1
    assert "from=0" in session.urls[0]


@pytest.mark.unit
def test_autosphere_fetch_segment_page2_offset() -> None:
    scraper = AutosphereFRScraper()
    session = _Session([_Resp(200, _AUTOSPHERE_JSON)])
    _run(scraper.fetch_segment(session, {}, 3))
    assert "from=200" in session.urls[0]


@pytest.mark.unit
def test_autosphere_fetch_segment_retries_block_then_gives_up() -> None:
    scraper = AutosphereFRScraper()
    _no_backoff(scraper)
    session = _Session([_Resp(429), _Resp(503), _Resp(403)])
    assert _run(scraper.fetch_segment(session, {}, 1)) == []
    assert len(session.calls) == scraper.RETRY_ATTEMPTS


@pytest.mark.unit
def test_autosphere_fetch_segment_recovers_after_block() -> None:
    scraper = AutosphereFRScraper()
    _no_backoff(scraper)
    session = _Session([_Resp(503), _Resp(200, _AUTOSPHERE_JSON)])
    assert _run(scraper.fetch_segment(session, {}, 1)) == _AUTOSPHERE_EXPECTED
    assert len(session.calls) == 2


@pytest.mark.unit
def test_autosphere_fetch_segment_non_retryable_status() -> None:
    scraper = AutosphereFRScraper()
    session = _Session([_Resp(404)])
    assert _run(scraper.fetch_segment(session, {}, 1)) == []
    assert len(session.calls) == 1


@pytest.mark.unit
def test_autosphere_fetch_segment_transport_error_retries() -> None:
    scraper = AutosphereFRScraper()
    _no_backoff(scraper)
    session = _Session([ConnectionError("reset"), _Resp(200, _AUTOSPHERE_JSON)])
    assert _run(scraper.fetch_segment(session, {}, 1)) == _AUTOSPHERE_EXPECTED
    assert len(session.calls) == 2


# -- wiring --------------------------------------------------------------------
@pytest.mark.unit
def test_autosphere_registry_resolves() -> None:
    scraper = get_scraper("autosphere.fr")
    assert isinstance(scraper, AutosphereFRScraper)
    assert scraper.DOMAIN == "autosphere.fr"


@pytest.mark.unit
def test_autosphere_domain_map_baseline() -> None:
    spec = domain_get("autosphere.fr")
    assert spec is not None, "autosphere.fr missing from REGISTRY"
    assert spec.tier is Tier.T0
    assert spec.waf is WAF.NONE
    assert "FR" in spec.countries


# =========================================================================== #
# auto-selection.com — Meilisearch API publique (T0)
# =========================================================================== #
from scrapers.portals.auto_selection_com import (
    AutoSelectionFRScraper,
    _BRANDS as _AUTOSEL_BRANDS,
    _PRICE_BANDS as _AUTOSEL_PRICE_BANDS,
)

_AUTOSEL_JSON = json.dumps({
    "results": [{
        "hits": [
            {"slug": "peugeot-208-style-123", "brand": "Peugeot", "model": "208"},
            {"slug": "renault-captur-456", "brand": "Renault", "model": "Captur"},
            {"slug": "peugeot-208-style-123", "brand": "Peugeot"},  # dup
        ],
        "totalHits": 950
    }]
})

_AUTOSEL_EXPECTED = [
    "https://www.auto-selection.com/acheter/peugeot-208-style-123",
    "https://www.auto-selection.com/acheter/renault-captur-456",
]


@pytest.mark.unit
def test_autosel_partition_shape() -> None:
    scraper = AutoSelectionFRScraper()
    segments = scraper.partition_params()
    assert len(segments) == len(_AUTOSEL_BRANDS)
    brands = [s["brand"] for s in segments]
    assert brands == list(_AUTOSEL_BRANDS)
    assert all("_fine" not in s for s in segments)


@pytest.mark.unit
def test_autosel_subdivide_creates_price_bands() -> None:
    scraper = AutoSelectionFRScraper()
    subs = scraper.subdivide_segment({"brand": "BMW"})
    assert len(subs) == len(_AUTOSEL_PRICE_BANDS)
    for s in subs:
        assert s["brand"] == "BMW"
        assert s["_fine"] is True
        assert "price_min" in s
        assert "price_max" in s


@pytest.mark.unit
def test_autosel_subdivide_stops_on_fine() -> None:
    scraper = AutoSelectionFRScraper()
    assert scraper.subdivide_segment({"brand": "BMW", "_fine": True}) == []


@pytest.mark.unit
def test_autosel_build_filter_brand_only() -> None:
    scraper = AutoSelectionFRScraper()
    assert scraper._build_filter({"brand": "BMW"}) == 'brand = "BMW"'


@pytest.mark.unit
def test_autosel_build_filter_brand_and_price() -> None:
    scraper = AutoSelectionFRScraper()
    filt = scraper._build_filter({"brand": "BMW", "price_min": 10000, "price_max": 20000})
    assert 'brand = "BMW"' in filt
    assert "price >= 10000" in filt
    assert "price < 20000" in filt
    assert " AND " in filt


@pytest.mark.unit
def test_autosel_build_filter_open_price_top() -> None:
    scraper = AutoSelectionFRScraper()
    filt = scraper._build_filter({"brand": "BMW", "price_min": 50000})
    assert "price >= 50000" in filt
    assert "price <" not in filt


@pytest.mark.unit
def test_autosel_build_body_shape() -> None:
    scraper = AutoSelectionFRScraper()
    raw = scraper._build_body({"brand": "Peugeot"}, 200)
    body = json.loads(raw)
    assert "queries" in body
    q = body["queries"][0]
    assert q["indexUid"] == "vehicles"
    assert q["offset"] == 200
    assert q["limit"] == 100
    assert 'brand = "Peugeot"' in q["filter"]


@pytest.mark.unit
def test_autosel_extract_pulls_slugs_and_dedups() -> None:
    assert AutoSelectionFRScraper()._extract(_AUTOSEL_JSON) == _AUTOSEL_EXPECTED


@pytest.mark.unit
def test_autosel_extract_skips_items_without_slug() -> None:
    body = json.dumps({
        "results": [{
            "hits": [
                {"id": 1},
                {"slug": "", "id": 2},
                {"slug": "ok-item-999", "id": 3},
            ],
            "totalHits": 3
        }]
    })
    assert AutoSelectionFRScraper()._extract(body) == [
        "https://www.auto-selection.com/acheter/ok-item-999",
    ]


@pytest.mark.unit
def test_autosel_extract_returns_empty_on_garbage() -> None:
    assert AutoSelectionFRScraper()._extract("") == []
    assert AutoSelectionFRScraper()._extract("not json") == []
    assert AutoSelectionFRScraper()._extract('{"results": "not a list"}') == []
    assert AutoSelectionFRScraper()._extract('{"results": []}') == []
    assert AutoSelectionFRScraper()._extract('{"results": [{"hits": "bad"}]}') == []


# -- fetch_segment behavioural matrix (POST-based) ----------------------------
@pytest.mark.unit
def test_autosel_fetch_segment_extracts_on_200() -> None:
    scraper = AutoSelectionFRScraper()
    session = _Session([_Resp(200, _AUTOSEL_JSON)])
    urls = _run(scraper.fetch_segment(session, {"brand": "BMW"}, 1))
    assert urls == _AUTOSEL_EXPECTED
    assert len(session.calls) == 1
    assert session.calls[0]["method"] == "POST"
    assert "multi-search" in session.urls[0]


@pytest.mark.unit
def test_autosel_fetch_segment_page2_offset() -> None:
    scraper = AutoSelectionFRScraper()
    session = _Session([_Resp(200, _AUTOSEL_JSON)])
    _run(scraper.fetch_segment(session, {"brand": "BMW"}, 3))
    body = json.loads(session.calls[0]["data"])
    assert body["queries"][0]["offset"] == 200  # (3-1)*100


@pytest.mark.unit
def test_autosel_fetch_segment_retries_block_then_gives_up() -> None:
    scraper = AutoSelectionFRScraper()
    _no_backoff(scraper)
    session = _Session([_Resp(429), _Resp(503), _Resp(403)])
    assert _run(scraper.fetch_segment(session, {"brand": "BMW"}, 1)) == []
    assert len(session.calls) == scraper.RETRY_ATTEMPTS


@pytest.mark.unit
def test_autosel_fetch_segment_recovers_after_block() -> None:
    scraper = AutoSelectionFRScraper()
    _no_backoff(scraper)
    session = _Session([_Resp(503), _Resp(200, _AUTOSEL_JSON)])
    assert _run(scraper.fetch_segment(session, {"brand": "BMW"}, 1)) == _AUTOSEL_EXPECTED
    assert len(session.calls) == 2


@pytest.mark.unit
def test_autosel_fetch_segment_non_retryable_status() -> None:
    scraper = AutoSelectionFRScraper()
    session = _Session([_Resp(404)])
    assert _run(scraper.fetch_segment(session, {"brand": "BMW"}, 1)) == []
    assert len(session.calls) == 1


@pytest.mark.unit
def test_autosel_fetch_segment_transport_error_retries() -> None:
    scraper = AutoSelectionFRScraper()
    _no_backoff(scraper)
    session = _Session([ConnectionError("reset"), _Resp(200, _AUTOSEL_JSON)])
    assert _run(scraper.fetch_segment(session, {"brand": "BMW"}, 1)) == _AUTOSEL_EXPECTED
    assert len(session.calls) == 2


# -- wiring --------------------------------------------------------------------
@pytest.mark.unit
def test_autosel_registry_resolves() -> None:
    scraper = get_scraper("auto-selection.com")
    assert isinstance(scraper, AutoSelectionFRScraper)
    assert scraper.DOMAIN == "auto-selection.com"


@pytest.mark.unit
def test_autosel_domain_map_baseline() -> None:
    spec = domain_get("auto-selection.com")
    assert spec is not None, "auto-selection.com missing from REGISTRY"
    assert spec.tier is Tier.T0
    assert spec.waf is WAF.NONE
    assert "FR" in spec.countries


# =========================================================================== #
# leparking.fr — SSR HTML méta-agrégateur (T1)
# =========================================================================== #
from scrapers.portals.leparking_fr import (
    LeParkingFRScraper,
    _BRANDS as _LEPARKING_BRANDS,
)

_LEPARKING_HTML = (
    '<div class="resultList">'
    '<a class="linkAd" href="/voiture-occasion/peugeot-308-hdi-12345.html">'
    '<span>Peugeot 308</span></a>'
    '<a href="/voiture-occasion/bmw-320i-67890.html" class="linkAd otherClass">'
    '<span>BMW 320i</span></a>'
    '<a class="linkAd" href="/voiture-occasion/peugeot-308-hdi-12345.html">'
    '<span>dup</span></a>'
    '</div>'
)

_LEPARKING_EXPECTED = [
    "https://www.leparking.fr/voiture-occasion/peugeot-308-hdi-12345.html",
    "https://www.leparking.fr/voiture-occasion/bmw-320i-67890.html",
]


@pytest.mark.unit
def test_leparking_partition_shape() -> None:
    scraper = LeParkingFRScraper()
    segments = scraper.partition_params()
    assert len(segments) == len(_LEPARKING_BRANDS)
    brands = [s["brand"] for s in segments]
    assert brands == list(_LEPARKING_BRANDS)


@pytest.mark.unit
def test_leparking_subdivide_is_noop() -> None:
    assert LeParkingFRScraper().subdivide_segment({"brand": "bmw"}) == []


@pytest.mark.unit
def test_leparking_build_url_with_brand() -> None:
    scraper = LeParkingFRScraper()
    assert scraper._build_url({"brand": "bmw"}, 3) == (
        "https://www.leparking.fr/voiture-occasion/bmw.html?p=3"
    )


@pytest.mark.unit
def test_leparking_build_url_without_brand() -> None:
    scraper = LeParkingFRScraper()
    assert scraper._build_url({}, 1) == (
        "https://www.leparking.fr/voiture-occasion.html?p=1"
    )


@pytest.mark.unit
def test_leparking_extract_pulls_linkAd_hrefs_and_dedups() -> None:
    assert LeParkingFRScraper()._extract(_LEPARKING_HTML) == _LEPARKING_EXPECTED


@pytest.mark.unit
def test_leparking_extract_fallback_to_detail_links() -> None:
    """Cuando no hay linkAd, usa el regex de fallback para links de detail."""
    html = (
        '<a href="/voiture-occasion/renault-clio-tce-abc123.html">Clio</a>'
        '<a href="/voiture-occasion/audi-a3-def-456.html">A3</a>'
    )
    urls = LeParkingFRScraper()._extract(html)
    assert len(urls) == 2
    assert "renault-clio-tce-abc123.html" in urls[0]
    assert "audi-a3-def-456.html" in urls[1]


@pytest.mark.unit
def test_leparking_extract_returns_empty_on_garbage() -> None:
    assert LeParkingFRScraper()._extract("") == []
    assert LeParkingFRScraper()._extract("<html></html>") == []
    assert LeParkingFRScraper()._extract("not html at all") == []


# -- fetch_segment behavioural matrix ------------------------------------------
@pytest.mark.unit
def test_leparking_fetch_segment_extracts_on_200() -> None:
    scraper = LeParkingFRScraper()
    session = _Session([_Resp(200, _LEPARKING_HTML)])
    urls = _run(scraper.fetch_segment(session, {"brand": "peugeot"}, 1))
    assert urls == _LEPARKING_EXPECTED
    assert len(session.calls) == 1
    assert "peugeot.html?p=1" in session.urls[0]


@pytest.mark.unit
def test_leparking_fetch_segment_retries_block_then_gives_up() -> None:
    scraper = LeParkingFRScraper()
    _no_backoff(scraper)
    session = _Session([_Resp(429), _Resp(503), _Resp(403)])
    assert _run(scraper.fetch_segment(session, {"brand": "bmw"}, 1)) == []
    assert len(session.calls) == scraper.RETRY_ATTEMPTS


@pytest.mark.unit
def test_leparking_fetch_segment_recovers_after_block() -> None:
    scraper = LeParkingFRScraper()
    _no_backoff(scraper)
    session = _Session([_Resp(503), _Resp(200, _LEPARKING_HTML)])
    assert _run(scraper.fetch_segment(session, {"brand": "bmw"}, 1)) == _LEPARKING_EXPECTED
    assert len(session.calls) == 2


@pytest.mark.unit
def test_leparking_fetch_segment_non_retryable_status() -> None:
    scraper = LeParkingFRScraper()
    session = _Session([_Resp(404)])
    assert _run(scraper.fetch_segment(session, {"brand": "bmw"}, 1)) == []
    assert len(session.calls) == 1


@pytest.mark.unit
def test_leparking_fetch_segment_transport_error_retries() -> None:
    scraper = LeParkingFRScraper()
    _no_backoff(scraper)
    session = _Session([ConnectionError("reset"), _Resp(200, _LEPARKING_HTML)])
    assert _run(scraper.fetch_segment(session, {"brand": "bmw"}, 1)) == _LEPARKING_EXPECTED
    assert len(session.calls) == 2


# -- wiring --------------------------------------------------------------------
@pytest.mark.unit
def test_leparking_registry_resolves() -> None:
    scraper = get_scraper("leparking.fr")
    assert isinstance(scraper, LeParkingFRScraper)
    assert scraper.DOMAIN == "leparking.fr"


@pytest.mark.unit
def test_leparking_domain_map_baseline() -> None:
    spec = domain_get("leparking.fr")
    assert spec is not None, "leparking.fr missing from REGISTRY"
    assert spec.tier is Tier.T1
    assert spec.waf is WAF.NONE
    assert "FR" in spec.countries


# =========================================================================== #
# annonces-automobile.com — SSR HTML portail premium (T1)
# =========================================================================== #
from scrapers.portals.annonces_automobile_com import AnnoncesAutomobileFRScraper

_ANNONCES_HTML = (
    '<div class="listing">'
    '<a href="https://www.annonces-automobile.com/acheter/bmw-serie-3-320d-12345">'
    '<span>BMW Série 3</span></a>'
    '<a href="https://www.annonces-automobile.com/acheter/audi-a4-avant-67890">'
    '<span>Audi A4</span></a>'
    '<a href="https://www.annonces-automobile.com/acheter/bmw-serie-3-320d-12345">'
    '<span>dup</span></a>'
    '<a href="https://www.annonces-automobile.com/acheter?pg=2">next page</a>'
    '</div>'
)

_ANNONCES_EXPECTED = [
    "https://www.annonces-automobile.com/acheter/bmw-serie-3-320d-12345",
    "https://www.annonces-automobile.com/acheter/audi-a4-avant-67890",
]


@pytest.mark.unit
def test_annonces_partition_is_single_occasion() -> None:
    segs = AnnoncesAutomobileFRScraper().partition_params()
    assert segs == [{"segment": "occasion"}]


@pytest.mark.unit
def test_annonces_subdivide_is_noop() -> None:
    assert AnnoncesAutomobileFRScraper().subdivide_segment({"segment": "occasion"}) == []


@pytest.mark.unit
def test_annonces_build_url() -> None:
    scraper = AnnoncesAutomobileFRScraper()
    assert scraper._build_url({"segment": "occasion"}, 5) == (
        "https://www.annonces-automobile.com/l-s/occasion?pg=5"
    )


@pytest.mark.unit
def test_annonces_extract_pulls_urls_and_dedups() -> None:
    urls = AnnoncesAutomobileFRScraper()._extract(_ANNONCES_HTML)
    assert urls == _ANNONCES_EXPECTED


@pytest.mark.unit
def test_annonces_extract_filters_navigation_links() -> None:
    """Links con ?pg= (paginación) y /acheter/ desnudo se filtran."""
    html = (
        '<a href="https://www.annonces-automobile.com/acheter?pg=2">next</a>'
        '<a href="https://www.annonces-automobile.com/acheter/">browse</a>'
        '<a href="https://www.annonces-automobile.com/acheter">browse2</a>'
    )
    assert AnnoncesAutomobileFRScraper()._extract(html) == []


@pytest.mark.unit
def test_annonces_extract_returns_empty_on_garbage() -> None:
    assert AnnoncesAutomobileFRScraper()._extract("") == []
    assert AnnoncesAutomobileFRScraper()._extract("<html></html>") == []
    assert AnnoncesAutomobileFRScraper()._extract("not html") == []


# -- fetch_segment behavioural matrix ------------------------------------------
@pytest.mark.unit
def test_annonces_fetch_segment_extracts_on_200() -> None:
    scraper = AnnoncesAutomobileFRScraper()
    session = _Session([_Resp(200, _ANNONCES_HTML)])
    urls = _run(scraper.fetch_segment(session, {"segment": "occasion"}, 1))
    assert urls == _ANNONCES_EXPECTED
    assert len(session.calls) == 1
    assert "l-s/occasion?pg=1" in session.urls[0]


@pytest.mark.unit
def test_annonces_fetch_segment_retries_block_then_gives_up() -> None:
    scraper = AnnoncesAutomobileFRScraper()
    _no_backoff(scraper)
    session = _Session([_Resp(429), _Resp(503), _Resp(403)])
    assert _run(scraper.fetch_segment(session, {"segment": "occasion"}, 1)) == []
    assert len(session.calls) == scraper.RETRY_ATTEMPTS


@pytest.mark.unit
def test_annonces_fetch_segment_recovers_after_block() -> None:
    scraper = AnnoncesAutomobileFRScraper()
    _no_backoff(scraper)
    session = _Session([_Resp(503), _Resp(200, _ANNONCES_HTML)])
    assert _run(scraper.fetch_segment(session, {"segment": "occasion"}, 1)) == _ANNONCES_EXPECTED
    assert len(session.calls) == 2


@pytest.mark.unit
def test_annonces_fetch_segment_non_retryable_status() -> None:
    scraper = AnnoncesAutomobileFRScraper()
    session = _Session([_Resp(404)])
    assert _run(scraper.fetch_segment(session, {"segment": "occasion"}, 1)) == []
    assert len(session.calls) == 1


@pytest.mark.unit
def test_annonces_fetch_segment_transport_error_retries() -> None:
    scraper = AnnoncesAutomobileFRScraper()
    _no_backoff(scraper)
    session = _Session([ConnectionError("reset"), _Resp(200, _ANNONCES_HTML)])
    assert _run(scraper.fetch_segment(session, {"segment": "occasion"}, 1)) == _ANNONCES_EXPECTED
    assert len(session.calls) == 2


# -- wiring --------------------------------------------------------------------
@pytest.mark.unit
def test_annonces_registry_resolves() -> None:
    scraper = get_scraper("annonces-automobile.com")
    assert isinstance(scraper, AnnoncesAutomobileFRScraper)
    assert scraper.DOMAIN == "annonces-automobile.com"


@pytest.mark.unit
def test_annonces_domain_map_baseline() -> None:
    spec = domain_get("annonces-automobile.com")
    assert spec is not None, "annonces-automobile.com missing from REGISTRY"
    assert spec.tier is Tier.T1
    assert spec.waf is WAF.NONE
    assert "FR" in spec.countries


# =========================================================================== #
# starterre.fr — SSR HTML mandataire auto (T1)
# =========================================================================== #
from scrapers.portals.starterre_fr import StarterreFRScraper

_STARTERRE_HTML = (
    '<div class="vehicles">'
    '<a href="/vehicule/peugeot-208-gt-line-12345">Peugeot 208</a>'
    '<a href="/vehicule/renault-clio-tce-67890">Renault Clio</a>'
    '<a href="/vehicule/peugeot-208-gt-line-12345">dup</a>'
    '</div>'
)

_STARTERRE_EXPECTED = [
    "https://www.starterre.fr/vehicule/peugeot-208-gt-line-12345",
    "https://www.starterre.fr/vehicule/renault-clio-tce-67890",
]


@pytest.mark.unit
def test_starterre_partition_is_single_empty_segment() -> None:
    assert StarterreFRScraper().partition_params() == [{}]


@pytest.mark.unit
def test_starterre_subdivide_is_noop() -> None:
    assert StarterreFRScraper().subdivide_segment({}) == []


@pytest.mark.unit
def test_starterre_build_url() -> None:
    scraper = StarterreFRScraper()
    assert scraper._build_url(1) == "https://www.starterre.fr/recherche?page=1"
    assert scraper._build_url(10) == "https://www.starterre.fr/recherche?page=10"


@pytest.mark.unit
def test_starterre_extract_pulls_vehicule_links_and_dedups() -> None:
    assert StarterreFRScraper()._extract(_STARTERRE_HTML) == _STARTERRE_EXPECTED


@pytest.mark.unit
def test_starterre_extract_returns_empty_on_garbage() -> None:
    assert StarterreFRScraper()._extract("") == []
    assert StarterreFRScraper()._extract("<html></html>") == []
    assert StarterreFRScraper()._extract("not html") == []


# -- fetch_segment behavioural matrix ------------------------------------------
@pytest.mark.unit
def test_starterre_fetch_segment_extracts_on_200() -> None:
    scraper = StarterreFRScraper()
    session = _Session([_Resp(200, _STARTERRE_HTML)])
    urls = _run(scraper.fetch_segment(session, {}, 1))
    assert urls == _STARTERRE_EXPECTED
    assert len(session.calls) == 1
    assert "recherche?page=1" in session.urls[0]


@pytest.mark.unit
def test_starterre_fetch_segment_retries_block_then_gives_up() -> None:
    scraper = StarterreFRScraper()
    _no_backoff(scraper)
    session = _Session([_Resp(429), _Resp(503), _Resp(403)])
    assert _run(scraper.fetch_segment(session, {}, 1)) == []
    assert len(session.calls) == scraper.RETRY_ATTEMPTS


@pytest.mark.unit
def test_starterre_fetch_segment_recovers_after_block() -> None:
    scraper = StarterreFRScraper()
    _no_backoff(scraper)
    session = _Session([_Resp(503), _Resp(200, _STARTERRE_HTML)])
    assert _run(scraper.fetch_segment(session, {}, 1)) == _STARTERRE_EXPECTED
    assert len(session.calls) == 2


@pytest.mark.unit
def test_starterre_fetch_segment_non_retryable_status() -> None:
    scraper = StarterreFRScraper()
    session = _Session([_Resp(404)])
    assert _run(scraper.fetch_segment(session, {}, 1)) == []
    assert len(session.calls) == 1


@pytest.mark.unit
def test_starterre_fetch_segment_transport_error_retries() -> None:
    scraper = StarterreFRScraper()
    _no_backoff(scraper)
    session = _Session([ConnectionError("reset"), _Resp(200, _STARTERRE_HTML)])
    assert _run(scraper.fetch_segment(session, {}, 1)) == _STARTERRE_EXPECTED
    assert len(session.calls) == 2


# -- wiring --------------------------------------------------------------------
@pytest.mark.unit
def test_starterre_registry_resolves() -> None:
    scraper = get_scraper("starterre.fr")
    assert isinstance(scraper, StarterreFRScraper)
    assert scraper.DOMAIN == "starterre.fr"


@pytest.mark.unit
def test_starterre_domain_map_baseline() -> None:
    spec = domain_get("starterre.fr")
    assert spec is not None, "starterre.fr missing from REGISTRY"
    assert spec.tier is Tier.T1
    assert spec.waf is WAF.NONE
    assert "FR" in spec.countries


# =========================================================================== #
# carizy.com — Nuxt SSR P2P auto (T1)
# =========================================================================== #
from scrapers.portals.carizy_com import CarizyFRScraper

_CARIZY_HTML = (
    '<div class="listings">'
    '<a href="/voiture-occasion/peugeot-208-essence-12345">Peugeot 208</a>'
    '<a href="/voiture-occasion/renault-captur-diesel-67890">Renault Captur</a>'
    '<a href="/voiture-occasion/peugeot-208-essence-12345">dup</a>'
    '</div>'
)

_CARIZY_EXPECTED = [
    "https://www.carizy.com/voiture-occasion/peugeot-208-essence-12345",
    "https://www.carizy.com/voiture-occasion/renault-captur-diesel-67890",
]


@pytest.mark.unit
def test_carizy_partition_is_single_empty_segment() -> None:
    assert CarizyFRScraper().partition_params() == [{}]


@pytest.mark.unit
def test_carizy_subdivide_is_noop() -> None:
    assert CarizyFRScraper().subdivide_segment({}) == []


@pytest.mark.unit
def test_carizy_build_url() -> None:
    scraper = CarizyFRScraper()
    assert scraper._build_url(1) == "https://www.carizy.com/voiture-occasion?page=1"
    assert scraper._build_url(5) == "https://www.carizy.com/voiture-occasion?page=5"


@pytest.mark.unit
def test_carizy_extract_pulls_links_and_dedups() -> None:
    assert CarizyFRScraper()._extract(_CARIZY_HTML) == _CARIZY_EXPECTED


@pytest.mark.unit
def test_carizy_extract_skips_category_paths() -> None:
    """Paths with only one segment (no slug after /voiture-occasion/) are skipped."""
    html = '<a href="/voiture-occasion/">browse</a>'
    assert CarizyFRScraper()._extract(html) == []


@pytest.mark.unit
def test_carizy_extract_returns_empty_on_garbage() -> None:
    assert CarizyFRScraper()._extract("") == []
    assert CarizyFRScraper()._extract("<html></html>") == []
    assert CarizyFRScraper()._extract("not html") == []


# -- fetch_segment behavioural matrix ------------------------------------------
@pytest.mark.unit
def test_carizy_fetch_segment_extracts_on_200() -> None:
    scraper = CarizyFRScraper()
    session = _Session([_Resp(200, _CARIZY_HTML)])
    urls = _run(scraper.fetch_segment(session, {}, 1))
    assert urls == _CARIZY_EXPECTED
    assert len(session.calls) == 1
    assert "voiture-occasion?page=1" in session.urls[0]


@pytest.mark.unit
def test_carizy_fetch_segment_retries_block_then_gives_up() -> None:
    scraper = CarizyFRScraper()
    _no_backoff(scraper)
    session = _Session([_Resp(429), _Resp(503), _Resp(403)])
    assert _run(scraper.fetch_segment(session, {}, 1)) == []
    assert len(session.calls) == scraper.RETRY_ATTEMPTS


@pytest.mark.unit
def test_carizy_fetch_segment_recovers_after_block() -> None:
    scraper = CarizyFRScraper()
    _no_backoff(scraper)
    session = _Session([_Resp(503), _Resp(200, _CARIZY_HTML)])
    assert _run(scraper.fetch_segment(session, {}, 1)) == _CARIZY_EXPECTED
    assert len(session.calls) == 2


@pytest.mark.unit
def test_carizy_fetch_segment_non_retryable_status() -> None:
    scraper = CarizyFRScraper()
    session = _Session([_Resp(404)])
    assert _run(scraper.fetch_segment(session, {}, 1)) == []
    assert len(session.calls) == 1


@pytest.mark.unit
def test_carizy_fetch_segment_transport_error_retries() -> None:
    scraper = CarizyFRScraper()
    _no_backoff(scraper)
    session = _Session([ConnectionError("reset"), _Resp(200, _CARIZY_HTML)])
    assert _run(scraper.fetch_segment(session, {}, 1)) == _CARIZY_EXPECTED
    assert len(session.calls) == 2


# -- wiring --------------------------------------------------------------------
@pytest.mark.unit
def test_carizy_registry_resolves() -> None:
    scraper = get_scraper("carizy.com")
    assert isinstance(scraper, CarizyFRScraper)
    assert scraper.DOMAIN == "carizy.com"


@pytest.mark.unit
def test_carizy_domain_map_baseline() -> None:
    spec = domain_get("carizy.com")
    assert spec is not None, "carizy.com missing from REGISTRY"
    assert spec.tier is Tier.T1
    assert spec.waf is WAF.NONE
    assert "FR" in spec.countries


# =========================================================================== #
# cardoen.be — SSR HTML concessionnaire belge (T1)
# =========================================================================== #
from scrapers.portals.cardoen_be import CardoenBEScraper

_CARDOEN_HTML = (
    '<div class="grid">'
    '<a href="/fr/achat/renault-clio-tce-12345/">Renault Clio</a>'
    '<a href="/fr/achat/volkswagen-golf-tdi-67890/">VW Golf</a>'
    '<a href="/fr/achat/renault-clio-tce-12345/">dup</a>'
    '<a href="/fr/achat/occasions/">catégorie</a>'
    '</div>'
)

_CARDOEN_EXPECTED = [
    "https://www.cardoen.be/fr/achat/renault-clio-tce-12345/",
    "https://www.cardoen.be/fr/achat/volkswagen-golf-tdi-67890/",
]


@pytest.mark.unit
def test_cardoen_partition_is_single_occasions() -> None:
    segs = CardoenBEScraper().partition_params()
    assert segs == [{"type": "occasions"}]


@pytest.mark.unit
def test_cardoen_subdivide_is_noop() -> None:
    assert CardoenBEScraper().subdivide_segment({"type": "occasions"}) == []


@pytest.mark.unit
def test_cardoen_build_url() -> None:
    scraper = CardoenBEScraper()
    assert scraper._build_url(1) == "https://www.cardoen.be/fr/achat/occasions/?page=1"
    assert scraper._build_url(10) == "https://www.cardoen.be/fr/achat/occasions/?page=10"


@pytest.mark.unit
def test_cardoen_extract_pulls_links_and_dedups() -> None:
    assert CardoenBEScraper()._extract(_CARDOEN_HTML) == _CARDOEN_EXPECTED


@pytest.mark.unit
def test_cardoen_extract_filters_category_pages() -> None:
    """Les liens de catégorie (/fr/achat/occasions/, /neuves/, /automatique/) sont filtrés."""
    html = (
        '<a href="/fr/achat/occasions/">Occasions</a>'
        '<a href="/fr/achat/neuves/">Neuves</a>'
        '<a href="/fr/achat/automatique/">Automatique</a>'
    )
    assert CardoenBEScraper()._extract(html) == []


@pytest.mark.unit
def test_cardoen_extract_returns_empty_on_garbage() -> None:
    assert CardoenBEScraper()._extract("") == []
    assert CardoenBEScraper()._extract("<html></html>") == []
    assert CardoenBEScraper()._extract("not html") == []


# -- fetch_segment behavioural matrix ------------------------------------------
@pytest.mark.unit
def test_cardoen_fetch_segment_extracts_on_200() -> None:
    scraper = CardoenBEScraper()
    session = _Session([_Resp(200, _CARDOEN_HTML)])
    urls = _run(scraper.fetch_segment(session, {"type": "occasions"}, 1))
    assert urls == _CARDOEN_EXPECTED
    assert len(session.calls) == 1
    assert "occasions/?page=1" in session.urls[0]


@pytest.mark.unit
def test_cardoen_fetch_segment_retries_block_then_gives_up() -> None:
    scraper = CardoenBEScraper()
    _no_backoff(scraper)
    session = _Session([_Resp(429), _Resp(503), _Resp(403)])
    assert _run(scraper.fetch_segment(session, {"type": "occasions"}, 1)) == []
    assert len(session.calls) == scraper.RETRY_ATTEMPTS


@pytest.mark.unit
def test_cardoen_fetch_segment_recovers_after_block() -> None:
    scraper = CardoenBEScraper()
    _no_backoff(scraper)
    session = _Session([_Resp(503), _Resp(200, _CARDOEN_HTML)])
    assert _run(scraper.fetch_segment(session, {"type": "occasions"}, 1)) == _CARDOEN_EXPECTED
    assert len(session.calls) == 2


@pytest.mark.unit
def test_cardoen_fetch_segment_non_retryable_status() -> None:
    scraper = CardoenBEScraper()
    session = _Session([_Resp(404)])
    assert _run(scraper.fetch_segment(session, {"type": "occasions"}, 1)) == []
    assert len(session.calls) == 1


@pytest.mark.unit
def test_cardoen_fetch_segment_transport_error_retries() -> None:
    scraper = CardoenBEScraper()
    _no_backoff(scraper)
    session = _Session([ConnectionError("reset"), _Resp(200, _CARDOEN_HTML)])
    assert _run(scraper.fetch_segment(session, {"type": "occasions"}, 1)) == _CARDOEN_EXPECTED
    assert len(session.calls) == 2


# -- wiring --------------------------------------------------------------------
@pytest.mark.unit
def test_cardoen_registry_resolves() -> None:
    scraper = get_scraper("cardoen.be")
    assert isinstance(scraper, CardoenBEScraper)
    assert scraper.DOMAIN == "cardoen.be"


@pytest.mark.unit
def test_cardoen_domain_map_baseline() -> None:
    spec = domain_get("cardoen.be")
    assert spec is not None, "cardoen.be missing from REGISTRY"
    assert spec.tier is Tier.T1
    assert spec.waf is WAF.CF_FREE
    assert "BE" in spec.countries


# =========================================================================== #
# moniteurautomobile.be — SSR HTML référence auto belge (T1)
# =========================================================================== #
from scrapers.portals.moniteur_auto_be import (
    MoniteurAutoBEScraper,
    _BRANDS as _MONITEUR_BRANDS,
)

_MONITEUR_HTML = (
    '<div class="results">'
    '<a href="/voitures-occasion/volkswagen-golf-tdi-12345.html">VW Golf</a>'
    '<a href="/voitures-occasion/bmw-serie-3-320d-67890.html">BMW Série 3</a>'
    '<a href="/voitures-occasion/volkswagen-golf-tdi-12345.html">dup</a>'
    '</div>'
)

_MONITEUR_EXPECTED = [
    "https://www.moniteurautomobile.be/voitures-occasion/volkswagen-golf-tdi-12345.html",
    "https://www.moniteurautomobile.be/voitures-occasion/bmw-serie-3-320d-67890.html",
]


@pytest.mark.unit
def test_moniteur_partition_shape() -> None:
    scraper = MoniteurAutoBEScraper()
    segments = scraper.partition_params()
    assert len(segments) == len(_MONITEUR_BRANDS)
    brands = [s["brand"] for s in segments]
    assert brands == list(_MONITEUR_BRANDS)


@pytest.mark.unit
def test_moniteur_subdivide_is_noop() -> None:
    assert MoniteurAutoBEScraper().subdivide_segment({"brand": "bmw"}) == []


@pytest.mark.unit
def test_moniteur_build_url_with_brand() -> None:
    scraper = MoniteurAutoBEScraper()
    assert scraper._build_url({"brand": "volkswagen"}, 3) == (
        "https://www.moniteurautomobile.be/marque--volkswagen/acheter-auto/occasion.html?page=3"
    )


@pytest.mark.unit
def test_moniteur_build_url_without_brand() -> None:
    scraper = MoniteurAutoBEScraper()
    assert scraper._build_url({}, 1) == (
        "https://www.moniteurautomobile.be/acheter-auto/occasion.html?page=1"
    )


@pytest.mark.unit
def test_moniteur_extract_pulls_links_and_dedups() -> None:
    assert MoniteurAutoBEScraper()._extract(_MONITEUR_HTML) == _MONITEUR_EXPECTED


@pytest.mark.unit
def test_moniteur_extract_returns_empty_on_garbage() -> None:
    assert MoniteurAutoBEScraper()._extract("") == []
    assert MoniteurAutoBEScraper()._extract("<html></html>") == []
    assert MoniteurAutoBEScraper()._extract("not html") == []


# -- fetch_segment behavioural matrix ------------------------------------------
@pytest.mark.unit
def test_moniteur_fetch_segment_extracts_on_200() -> None:
    scraper = MoniteurAutoBEScraper()
    session = _Session([_Resp(200, _MONITEUR_HTML)])
    urls = _run(scraper.fetch_segment(session, {"brand": "volkswagen"}, 1))
    assert urls == _MONITEUR_EXPECTED
    assert len(session.calls) == 1
    assert "marque--volkswagen" in session.urls[0]
    assert "page=1" in session.urls[0]


@pytest.mark.unit
def test_moniteur_fetch_segment_retries_block_then_gives_up() -> None:
    scraper = MoniteurAutoBEScraper()
    _no_backoff(scraper)
    session = _Session([_Resp(429), _Resp(503), _Resp(403)])
    assert _run(scraper.fetch_segment(session, {"brand": "bmw"}, 1)) == []
    assert len(session.calls) == scraper.RETRY_ATTEMPTS


@pytest.mark.unit
def test_moniteur_fetch_segment_recovers_after_block() -> None:
    scraper = MoniteurAutoBEScraper()
    _no_backoff(scraper)
    session = _Session([_Resp(503), _Resp(200, _MONITEUR_HTML)])
    assert _run(scraper.fetch_segment(session, {"brand": "bmw"}, 1)) == _MONITEUR_EXPECTED
    assert len(session.calls) == 2


@pytest.mark.unit
def test_moniteur_fetch_segment_non_retryable_status() -> None:
    scraper = MoniteurAutoBEScraper()
    session = _Session([_Resp(404)])
    assert _run(scraper.fetch_segment(session, {"brand": "bmw"}, 1)) == []
    assert len(session.calls) == 1


@pytest.mark.unit
def test_moniteur_fetch_segment_transport_error_retries() -> None:
    scraper = MoniteurAutoBEScraper()
    _no_backoff(scraper)
    session = _Session([ConnectionError("reset"), _Resp(200, _MONITEUR_HTML)])
    assert _run(scraper.fetch_segment(session, {"brand": "bmw"}, 1)) == _MONITEUR_EXPECTED
    assert len(session.calls) == 2


# -- wiring --------------------------------------------------------------------
@pytest.mark.unit
def test_moniteur_registry_resolves() -> None:
    scraper = get_scraper("moniteurautomobile.be")
    assert isinstance(scraper, MoniteurAutoBEScraper)
    assert scraper.DOMAIN == "moniteurautomobile.be"


@pytest.mark.unit
def test_moniteur_domain_map_baseline() -> None:
    spec = domain_get("moniteurautomobile.be")
    assert spec is not None, "moniteurautomobile.be missing from REGISTRY"
    assert spec.tier is Tier.T1
    assert spec.waf is WAF.NONE
    assert "BE" in spec.countries
