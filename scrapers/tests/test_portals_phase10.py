"""
Phase-10 portal scraper tests — wallapop.com, autohero.com, heycar.com,
comparis.ch.

T2→T0/T1 bypass scrapers exercised against a fake duck-typed session (no
curl_cffi): partition_params grid, subdivide_segment termination, _build_url
request shaping, _extract parsing + dedup, fetch_segment retry / status
handling.  Registry and domain_map wiring are also asserted to catch drift.

wallapop uses cursor-based pagination (special _paginate override).
autohero uses POST with GraphQL body.
heycar uses 0-indexed page/size REST API.
comparis uses regex-based SSR HTML extraction.

Coroutines run synchronously via asyncio.run() (engine convention).
fetch_segment tests stub _retry_backoff to no-op so the suite never sleeps.
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
# fakes — duck-typed session matching the engine contract
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

    async def get(self, url: str, timeout: int | None = None, **kw: Any) -> _Resp:
        self.calls.append({"method": "GET", "url": url, "kwargs": kw})
        return self._next()

    async def post(
        self,
        url: str,
        json: Any | None = None,
        headers: dict[str, str] | None = None,
        timeout: int | None = None,
        **kw: Any,
    ) -> _Resp:
        self.calls.append({"method": "POST", "url": url, "json": json, "headers": headers})
        return self._next()


def _no_backoff(scraper: BasePortalScraper) -> None:
    """Stub exponential backoff so retry tests run instantly."""

    async def _noop(attempt: int, factor: float = 1.0) -> None:
        return None

    scraper._retry_backoff = _noop  # type: ignore[method-assign]


# =========================================================================== #
# wallapop.com — Mobile API bypass (T0)
# =========================================================================== #
from scrapers.portals.wallapop_com import WallapopComScraper

_WALLAPOP_JSON = json.dumps({
    "search_objects": [
        {"id": "abc1", "web_slug": "bmw-320d-i12345", "title": "BMW 320d",
         "price": {"amount": 15000, "currency": "EUR"}},
        {"id": "abc2", "web_slug": "audi-a3-i67890", "title": "Audi A3",
         "price": {"amount": 12000, "currency": "EUR"}},
        {"id": "abc3", "web_slug": "vw-golf-i11111", "title": "VW Golf",
         "price": {"amount": 8000, "currency": "EUR"}},
    ],
    "next_page": "eyJjdXJzb3IiOiJ0ZXN0In0=",
})

_WALLAPOP_LAST_PAGE = json.dumps({
    "search_objects": [
        {"id": "xyz1", "web_slug": "seat-leon-i99999", "title": "Seat Leon",
         "price": {"amount": 11000, "currency": "EUR"}},
    ],
    "next_page": None,
})


class TestWallapopCom:
    def test_registry(self) -> None:
        s = get_scraper("wallapop.com")
        assert s is not None
        assert isinstance(s, WallapopComScraper)
        assert s.DOMAIN == "wallapop.com"
        assert s.COUNTRY == "ES"

    def test_domain_map(self) -> None:
        spec = domain_get("wallapop.com")
        assert spec is not None
        assert spec.tier is Tier.T0
        assert spec.waf is WAF.PERIMETER_X

    def test_partition_params_geo_x_price(self) -> None:
        s = WallapopComScraper()
        params = s.partition_params()
        # 8 cities x 8 price bands = 64
        assert len(params) == len(s.GEO_CENTRES) * len(s.PRICE_BANDS)
        assert all("latitude" in p for p in params)
        assert all("longitude" in p for p in params)
        assert all("price_from" in p for p in params)

    def test_subdivide_segment(self) -> None:
        s = WallapopComScraper()
        params = {"city": "Madrid", "latitude": 40.4168, "longitude": -3.7038,
                  "price_from": 10_000, "price_to": 20_000}
        subs = s.subdivide_segment(params)
        assert len(subs) >= 2
        assert all(sub.get("_fine") for sub in subs)
        # Fine segments don't subdivide further.
        assert s.subdivide_segment(subs[0]) == []

    def test_build_url(self) -> None:
        s = WallapopComScraper()
        params = {"city": "Madrid", "latitude": 40.4168, "longitude": -3.7038,
                  "price_from": 5000, "price_to": 10000}
        url = s._build_url(params)
        assert "api.wallapop.com" in url
        assert "category_ids=100" in url
        assert "latitude=40.4168" in url
        assert "min_sale_price=5000" in url
        assert "max_sale_price=10000" in url

    def test_build_url_open_ceiling(self) -> None:
        s = WallapopComScraper()
        params = {"city": "Madrid", "latitude": 40.4168, "longitude": -3.7038,
                  "price_from": 100000, "price_to": None}
        url = s._build_url(params)
        assert "max_sale_price" not in url

    def test_build_url_with_cursor(self) -> None:
        s = WallapopComScraper()
        params = {"city": "Madrid", "latitude": 40.4168, "longitude": -3.7038,
                  "price_from": 0, "price_to": 5000, "_cursor": "abc123"}
        url = s._build_url(params)
        assert "start=abc123" in url

    def test_extract(self) -> None:
        s = WallapopComScraper()
        urls, cursor = s._extract(_WALLAPOP_JSON)
        assert len(urls) == 3
        assert cursor == "eyJjdXJzb3IiOiJ0ZXN0In0="
        assert all("es.wallapop.com/item/" in u for u in urls)
        assert "bmw-320d-i12345" in urls[0]

    def test_extract_dedup(self) -> None:
        s = WallapopComScraper()
        dup_json = json.dumps({
            "search_objects": [
                {"id": "a", "web_slug": "same-slug"},
                {"id": "b", "web_slug": "same-slug"},
                {"id": "c", "web_slug": "other-slug"},
            ],
            "next_page": None,
        })
        urls, _ = s._extract(dup_json)
        assert len(urls) == 2

    def test_extract_empty(self) -> None:
        s = WallapopComScraper()
        urls, cursor = s._extract("{}")
        assert urls == []
        assert cursor is None

    def test_extract_invalid_json(self) -> None:
        s = WallapopComScraper()
        urls, cursor = s._extract("not json")
        assert urls == []
        assert cursor is None

    def test_fetch_segment_200(self) -> None:
        s = WallapopComScraper()
        _no_backoff(s)
        sess = _Session([_Resp(200, _WALLAPOP_JSON)])
        params = {"city": "Madrid", "latitude": 40.4168, "longitude": -3.7038,
                  "price_from": 0, "price_to": 5000}
        urls = _run(s.fetch_segment(sess, params, 1))
        assert len(urls) == 3

    def test_fetch_segment_429_retry(self) -> None:
        s = WallapopComScraper()
        _no_backoff(s)
        sess = _Session([_Resp(429), _Resp(429), _Resp(200, _WALLAPOP_JSON)])
        params = {"city": "Barcelona", "latitude": 41.3874, "longitude": 2.1686,
                  "price_from": 0, "price_to": 5000}
        urls = _run(s.fetch_segment(sess, params, 1))
        assert len(urls) == 3
        assert len(sess.calls) == 3

    def test_fetch_segment_all_fail(self) -> None:
        s = WallapopComScraper()
        _no_backoff(s)
        sess = _Session([_Resp(500), _Resp(500), _Resp(500)])
        params = {"city": "Madrid", "latitude": 40.4168, "longitude": -3.7038,
                  "price_from": 0, "price_to": 5000}
        urls = _run(s.fetch_segment(sess, params, 1))
        assert urls == []

    def test_fetch_segment_transport_error(self) -> None:
        s = WallapopComScraper()
        _no_backoff(s)
        sess = _Session([ConnectionError("timeout"), _Resp(200, _WALLAPOP_JSON)])
        params = {"city": "Madrid", "latitude": 40.4168, "longitude": -3.7038,
                  "price_from": 0, "price_to": 5000}
        urls = _run(s.fetch_segment(sess, params, 1))
        assert len(urls) == 3


# =========================================================================== #
# autohero.com — GraphQL API bypass (T0)
# =========================================================================== #
from scrapers.portals.autohero_com import AutoheroCOMScraper

_AUTOHERO_JSON = json.dumps({
    "data": {
        "searchAdV9AdsV2": {
            "total": 3,
            "data": [
                {"id": "ah1", "carUrlTitle": "bmw-320d-xdrive", "manufacturer": "BMW",
                 "model": "320d", "offerPrice": 25000, "countryCode": "DE"},
                {"id": "ah2", "carUrlTitle": "audi-a4-avant", "manufacturer": "Audi",
                 "model": "A4", "offerPrice": 22000, "countryCode": "DE"},
                {"id": "ah3", "carUrlTitle": "vw-golf-gti", "manufacturer": "VW",
                 "model": "Golf GTI", "offerPrice": 28000, "countryCode": "DE"},
            ],
        }
    }
})


class TestAutoheroCOM:
    def test_registry(self) -> None:
        s = get_scraper("autohero.com")
        assert s is not None
        assert isinstance(s, AutoheroCOMScraper)
        assert s.DOMAIN == "autohero.com"
        assert s.COUNTRY == "DE"

    def test_domain_map(self) -> None:
        spec = domain_get("autohero.com")
        assert spec is not None
        assert spec.tier is Tier.T0

    def test_partition_params_countries(self) -> None:
        s = AutoheroCOMScraper()
        params = s.partition_params()
        assert len(params) == 8  # DE, IT, FR, ES, AT, PL, NL, SE
        codes = {p["country_code"] for p in params}
        assert "DE" in codes
        assert "FR" in codes
        assert "ES" in codes

    def test_subdivide_always_empty(self) -> None:
        s = AutoheroCOMScraper()
        assert s.subdivide_segment({"country_code": "DE"}) == []

    def test_build_query(self) -> None:
        s = AutoheroCOMScraper()
        body = s._build_query("DE", 0)
        assert "query" in body
        assert '"countryCode"' in body["query"]
        assert '"DE"' in body["query"]
        assert "offset:0" in body["query"]

    def test_build_query_offset(self) -> None:
        s = AutoheroCOMScraper()
        body = s._build_query("FR", 200)
        assert "offset:200" in body["query"]
        assert '"FR"' in body["query"]

    def test_extract(self) -> None:
        s = AutoheroCOMScraper()
        urls = s._extract(_AUTOHERO_JSON, "DE")
        assert len(urls) == 3
        assert all("autohero.com/de/buy/" in u for u in urls)
        assert "bmw-320d-xdrive-ah1" in urls[0]

    def test_extract_dedup(self) -> None:
        s = AutoheroCOMScraper()
        dup_json = json.dumps({
            "data": {"searchAdV9AdsV2": {"total": 2, "data": [
                {"id": "x", "carUrlTitle": "same-car", "manufacturer": "BMW"},
                {"id": "x", "carUrlTitle": "same-car", "manufacturer": "BMW"},
            ]}}
        })
        urls = s._extract(dup_json, "DE")
        assert len(urls) == 1

    def test_extract_rawjson_string(self) -> None:
        """Test RawJson return type where searchAdV9AdsV2 is a JSON string."""
        s = AutoheroCOMScraper()
        inner = json.dumps({"total": 1, "data": [
            {"id": "rj1", "carUrlTitle": "test-car", "manufacturer": "Test"},
        ]})
        payload = json.dumps({"data": {"searchAdV9AdsV2": inner}})
        urls = s._extract(payload, "FR")
        assert len(urls) == 1
        assert "autohero.com/fr/buy/test-car-rj1" in urls[0]

    def test_extract_empty(self) -> None:
        s = AutoheroCOMScraper()
        assert s._extract("{}", "DE") == []
        assert s._extract("not json", "DE") == []

    def test_fetch_segment_200(self) -> None:
        s = AutoheroCOMScraper()
        _no_backoff(s)
        sess = _Session([_Resp(200, _AUTOHERO_JSON)])
        urls = _run(s.fetch_segment(sess, {"country_code": "DE"}, 1))
        assert len(urls) == 3
        assert sess.calls[0]["method"] == "POST"

    def test_fetch_segment_retry(self) -> None:
        s = AutoheroCOMScraper()
        _no_backoff(s)
        sess = _Session([_Resp(503), _Resp(200, _AUTOHERO_JSON)])
        urls = _run(s.fetch_segment(sess, {"country_code": "IT"}, 1))
        assert len(urls) == 3
        assert len(sess.calls) == 2

    def test_fetch_segment_all_fail(self) -> None:
        s = AutoheroCOMScraper()
        _no_backoff(s)
        sess = _Session([_Resp(403), _Resp(403), _Resp(403)])
        urls = _run(s.fetch_segment(sess, {"country_code": "DE"}, 1))
        assert urls == []


# =========================================================================== #
# heycar.com — REST API bypass, FR market (T0)
# =========================================================================== #
from scrapers.portals.heycar_com import HeycarFRScraper

_HEYCAR_JSON = json.dumps({
    "content": [
        {"id": "hc1", "heycarId": "hcd1", "make": {"label": "BMW"},
         "model": {"label": "3 Series"}, "pricing": {"price": 25000}},
        {"id": "hc2", "heycarId": "hcd2", "make": {"label": "Audi"},
         "model": {"label": "A4"}, "pricing": {"price": 22000}},
    ],
    "totalElements": 2,
    "totalPages": 1,
    "pageable": {"pageNumber": 0, "pageSize": 500},
})


class TestHeycarFR:
    def test_registry(self) -> None:
        s = get_scraper("heycar.com")
        assert s is not None
        assert isinstance(s, HeycarFRScraper)
        assert s.DOMAIN == "heycar.com"
        assert s.COUNTRY == "FR"

    def test_domain_map(self) -> None:
        spec = domain_get("heycar.com")
        assert spec is not None
        assert spec.tier is Tier.T0

    def test_partition_params(self) -> None:
        s = HeycarFRScraper()
        params = s.partition_params()
        assert len(params) == len(s.PRICE_BANDS)
        assert all("price_from" in p for p in params)

    def test_subdivide_segment(self) -> None:
        s = HeycarFRScraper()
        params = {"price_from": 10000, "price_to": 20000}
        subs = s.subdivide_segment(params)
        assert len(subs) >= 2
        assert all(sub.get("_fine") for sub in subs)
        assert s.subdivide_segment(subs[0]) == []

    def test_build_url_page1(self) -> None:
        s = HeycarFRScraper()
        url = s._build_url({"price_from": 5000, "price_to": 10000}, 0)
        assert "group-mobility-trader.com" in url
        assert "page=0" in url
        assert "size=500" in url
        assert "priceFrom=5000" in url
        assert "priceTo=10000" in url

    def test_build_url_page_conversion(self) -> None:
        """fetch_segment converts 1-based page_num to 0-based api_page."""
        s = HeycarFRScraper()
        url = s._build_url({"price_from": 0, "price_to": 5000}, 2)
        assert "page=2" in url

    def test_build_url_open_ceiling(self) -> None:
        s = HeycarFRScraper()
        url = s._build_url({"price_from": 100000, "price_to": None}, 0)
        assert "priceTo" not in url
        assert "priceFrom=100000" in url

    def test_extract(self) -> None:
        s = HeycarFRScraper()
        urls = s._extract(_HEYCAR_JSON)
        assert len(urls) == 2
        assert all("heycar.com/fr/vehicule/" in u for u in urls)
        assert "hc1" in urls[0]
        assert "hc2" in urls[1]

    def test_extract_fallback_heycarid(self) -> None:
        s = HeycarFRScraper()
        fallback_json = json.dumps({
            "content": [{"heycarId": "fallback1"}],
            "totalElements": 1,
        })
        urls = s._extract(fallback_json)
        assert len(urls) == 1
        assert "fallback1" in urls[0]

    def test_extract_dedup(self) -> None:
        s = HeycarFRScraper()
        dup_json = json.dumps({
            "content": [
                {"id": "same"},
                {"id": "same"},
                {"id": "other"},
            ],
            "totalElements": 3,
        })
        urls = s._extract(dup_json)
        assert len(urls) == 2

    def test_extract_empty(self) -> None:
        s = HeycarFRScraper()
        assert s._extract("{}") == []
        assert s._extract("not json") == []

    def test_fetch_segment_200(self) -> None:
        s = HeycarFRScraper()
        _no_backoff(s)
        sess = _Session([_Resp(200, _HEYCAR_JSON)])
        urls = _run(s.fetch_segment(sess, {"price_from": 0, "price_to": 5000}, 1))
        assert len(urls) == 2

    def test_fetch_segment_retry(self) -> None:
        s = HeycarFRScraper()
        _no_backoff(s)
        sess = _Session([_Resp(429), _Resp(200, _HEYCAR_JSON)])
        urls = _run(s.fetch_segment(sess, {"price_from": 0, "price_to": 5000}, 1))
        assert len(urls) == 2

    def test_fetch_segment_all_fail(self) -> None:
        s = HeycarFRScraper()
        _no_backoff(s)
        sess = _Session([_Resp(503), _Resp(503), _Resp(503)])
        urls = _run(s.fetch_segment(sess, {"price_from": 0, "price_to": 5000}, 1))
        assert urls == []


# =========================================================================== #
# comparis.ch — SSR HTML scraping (T1)
# =========================================================================== #
from scrapers.portals.comparis_ch import ComparisCHScraper

_COMPARIS_HTML = """
<html><body>
<a href="/carfinder/marktplatz/details/show/32911044">Seat Altea XL</a>
<a href="/carfinder/marktplatz/details/show/32813341">Hyundai Terracan</a>
<a href="/carfinder/marktplatz/details/show/32785540">VW Polo</a>
<a href="/carfinder/marktplatz/details/show/32911044">Seat Altea DUP</a>
<a href="/carfinder/search">Search page link</a>
</body></html>
"""


class TestComparisCH:
    def test_registry(self) -> None:
        s = get_scraper("comparis.ch")
        assert s is not None
        assert isinstance(s, ComparisCHScraper)
        assert s.DOMAIN == "comparis.ch"
        assert s.COUNTRY == "CH"

    def test_domain_map(self) -> None:
        spec = domain_get("comparis.ch")
        assert spec is not None
        # Re-verified live 2026-06-09: comparis.ch is DataDome-protected (x-datadome:protected,
        # captcha body, 403 to curl_cffi Chrome), NOT the stale 'T1 / no-WAF' the 2026-06-04 note
        # claimed. The DOSSIER had it right. Test corrected to the verified truth (no vender mentiras).
        assert spec.tier is Tier.T3
        assert spec.waf is WAF.DATADOME

    def test_partition_params_year_x_price(self) -> None:
        s = ComparisCHScraper()
        params = s.partition_params()
        # 11 year bands x 10 price bands = 110
        assert len(params) == len(s.YEAR_BANDS) * len(s.PRICE_BANDS)
        assert all("year_from" in p for p in params)
        assert all("price_from" in p for p in params)

    def test_subdivide_segment(self) -> None:
        s = ComparisCHScraper()
        params = {"year_from": 2020, "year_to": 2022, "price_from": 20000, "price_to": 30000}
        subs = s.subdivide_segment(params)
        assert len(subs) >= 2
        assert all(sub.get("_fine") for sub in subs)
        # Fine segments don't subdivide further.
        assert s.subdivide_segment(subs[0]) == []

    def test_build_url_page1(self) -> None:
        s = ComparisCHScraper()
        url = s._build_url({"year_from": 2020, "year_to": 2024,
                            "price_from": 10000, "price_to": 20000}, 1)
        assert "comparis.ch" in url
        assert "page=0" in url  # 1-based -> 0-based
        assert "yearfrom=2020" in url
        assert "yearto=2024" in url
        assert "pricefrom=10000" in url
        assert "priceto=20000" in url
        assert "condition=occasion" in url

    def test_build_url_page3(self) -> None:
        s = ComparisCHScraper()
        url = s._build_url({"year_from": 2020, "year_to": 2024,
                            "price_from": 0, "price_to": 5000}, 3)
        assert "page=2" in url  # 3-based -> 2

    def test_build_url_open_ceiling(self) -> None:
        s = ComparisCHScraper()
        url = s._build_url({"year_from": 2020, "year_to": 2024,
                            "price_from": 100000, "price_to": None}, 1)
        assert "priceto" not in url.lower()

    def test_extract_dedup(self) -> None:
        s = ComparisCHScraper()
        urls = s._extract(_COMPARIS_HTML)
        assert len(urls) == 3  # 4 links but 32911044 appears twice → deduplicated
        assert any("32911044" in u for u in urls)
        assert any("32813341" in u for u in urls)
        assert any("32785540" in u for u in urls)

    def test_extract_ignores_non_detail(self) -> None:
        """Links not matching the detail pattern are ignored."""
        s = ComparisCHScraper()
        urls = s._extract('<a href="/carfinder/search">foo</a>')
        assert urls == []

    def test_extract_empty(self) -> None:
        s = ComparisCHScraper()
        assert s._extract("") == []
        assert s._extract("<html></html>") == []

    def test_fetch_segment_200(self) -> None:
        s = ComparisCHScraper()
        _no_backoff(s)
        sess = _Session([_Resp(200, _COMPARIS_HTML)])
        urls = _run(s.fetch_segment(
            sess,
            {"year_from": 2020, "year_to": 2024, "price_from": 0, "price_to": 5000},
            1,
        ))
        assert len(urls) == 3

    def test_fetch_segment_403_retry(self) -> None:
        s = ComparisCHScraper()
        _no_backoff(s)
        sess = _Session([_Resp(403), _Resp(403), _Resp(200, _COMPARIS_HTML)])
        urls = _run(s.fetch_segment(
            sess,
            {"year_from": 2020, "year_to": 2024, "price_from": 0, "price_to": 5000},
            1,
        ))
        assert len(urls) == 3
        assert len(sess.calls) == 3

    def test_fetch_segment_all_fail(self) -> None:
        s = ComparisCHScraper()
        _no_backoff(s)
        sess = _Session([_Resp(500), _Resp(500), _Resp(500)])
        urls = _run(s.fetch_segment(
            sess,
            {"year_from": 2020, "year_to": 2024, "price_from": 0, "price_to": 5000},
            1,
        ))
        assert urls == []

    def test_fetch_segment_transport_error(self) -> None:
        s = ComparisCHScraper()
        _no_backoff(s)
        sess = _Session([ConnectionError("timeout"), _Resp(200, _COMPARIS_HTML)])
        urls = _run(s.fetch_segment(
            sess,
            {"year_from": 2020, "year_to": 2024, "price_from": 0, "price_to": 5000},
            1,
        ))
        assert len(urls) == 3
