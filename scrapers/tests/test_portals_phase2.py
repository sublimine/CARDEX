"""
Phase-2 portal scraper tests — the six non-AutoScout24 portals.

Covered: leboncoin.fr (T3 DataDome finder POST), kleinanzeigen.de (T2 Akamai
path-grammar GET), coches.net (Adevinta JSON POST), lacentrale.fr (T3 DataDome
SSR GET), mobile.de (T2 Akamai SRP GET) and marktplaats.nl (T0 LRP JSON GET).

Each portal's primitives are exercised directly against a fake duck-typed session
(no curl_cffi / browser): partition_params grid, one-level subdivide_segment
termination, _build_url / _build_body request shaping, _extract parsing + dedup,
and fetch_segment retry / soft-block / status handling. Two wiring layers are also
asserted — the portal registry (`get_scraper`) and the domain→tier registry
(`domain_map`) — so class/string/tier drift surfaces here rather than at runtime.

Coroutines run synchronously via asyncio.run() (engine convention). fetch_segment
tests stub `_retry_backoff` to a no-op so the suite never sleeps.
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
from scrapers.portals.coches_net import CochesNetScraper
from scrapers.portals.kleinanzeigen_de import KleinanzeigenDEScraper
from scrapers.portals.lacentrale_fr import LaCentraleFRScraper
from scrapers.portals.leboncoin_fr import LeboncoinFRScraper
from scrapers.portals.marktplaats_nl import MarktplaatsNLScraper
from scrapers.portals.mobile_de import MobileDeScraper


def _run(coro: Any) -> Any:
    return asyncio.run(coro)


# --------------------------------------------------------------------------- #
# fakes — duck-typed session supporting BOTH GET and POST surfaces
# --------------------------------------------------------------------------- #
class _Resp:
    """Minimal duck-typed HTTP response (curl_cffi shape: .status_code, .text)."""

    def __init__(self, status_code: int, text: str = "") -> None:
        self.status_code = status_code
        self.text = text


class _Session:
    """
    Fake AsyncSession yielding queued responses (or raising queued exceptions).

    Records every call so tests can assert the exact URL (GET portals) or JSON
    body + headers (POST portals) the scraper produced.
    """

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
        self.calls.append({"method": "GET", "url": url, "json": None, "headers": None})
        return self._next()

    async def post(
        self,
        url: str,
        json: Any = None,
        headers: dict[str, str] | None = None,
        timeout: int | None = None,
    ) -> _Resp:
        self.calls.append({"method": "POST", "url": url, "json": json, "headers": headers})
        return self._next()


def _no_backoff(scraper: BasePortalScraper) -> None:
    """Stub the exponential backoff so retry tests run instantly."""

    async def _noop(attempt: int, factor: float = 1.0) -> None:
        return None

    scraper._retry_backoff = _noop  # type: ignore[method-assign]


# Sample base segment (year × price) shared by the year/price-grid portals.
_YP = {"year_from": 2018, "year_to": 2020, "price_from": 10_000, "price_to": 20_000}
_YP_OPEN = {"year_from": 2024, "year_to": 2026, "price_from": 100_000, "price_to": None}


# --------------------------------------------------------------------------- #
# partition_params — grid shape & uniqueness
# --------------------------------------------------------------------------- #
@pytest.mark.unit
@pytest.mark.parametrize(
    "cls",
    [MobileDeScraper, MarktplaatsNLScraper, KleinanzeigenDEScraper, CochesNetScraper, LaCentraleFRScraper],
)
def test_year_price_partition_shape(cls) -> None:
    scraper = cls()
    segments = scraper.partition_params()
    assert len(segments) == len(scraper.YEAR_BANDS) * len(scraper.PRICE_BANDS)
    keys = {(s["year_from"], s["year_to"], s["price_from"], s["price_to"]) for s in segments}
    assert len(keys) == len(segments)  # every cell unique
    assert not any("_fine" in s for s in segments)  # base grid is never pre-split


@pytest.mark.unit
def test_leboncoin_partition_is_department_year_price() -> None:
    scraper = LeboncoinFRScraper()
    segments = scraper.partition_params()
    expected = len(scraper.DEPARTMENTS) * len(scraper.YEAR_BANDS) * len(scraper.PRICE_BANDS)
    assert len(segments) == expected
    assert len(scraper.DEPARTMENTS) == 101  # 96 metropolitan + Corsica + 5 DOM
    assert "2A" in scraper.DEPARTMENTS and "2B" in scraper.DEPARTMENTS
    assert "971" in scraper.DEPARTMENTS  # overseas
    keys = {
        (s["department"], s["year_from"], s["year_to"], s["price_from"], s["price_to"])
        for s in segments
    }
    assert len(keys) == len(segments)


# --------------------------------------------------------------------------- #
# subdivide_segment — one-level explosion then termination
# --------------------------------------------------------------------------- #
@pytest.mark.unit
@pytest.mark.parametrize(
    "cls",
    [MobileDeScraper, MarktplaatsNLScraper, KleinanzeigenDEScraper, CochesNetScraper, LaCentraleFRScraper],
)
def test_year_price_subdivide_then_stops(cls) -> None:
    scraper = cls()
    subs = scraper.subdivide_segment(dict(_YP))
    assert subs, "a capped cell must yield sub-cells"
    # Every sub-cell is a single calendar year and carries the _fine marker.
    for s in subs:
        assert s["year_from"] == s["year_to"]
        assert s["_fine"] is True
    # Years span the original band inclusively.
    assert {s["year_from"] for s in subs} == {2018, 2019, 2020}
    # A _fine sub-cell cannot be subdivided further (one-level contract).
    assert scraper.subdivide_segment(subs[0]) == []


@pytest.mark.unit
def test_leboncoin_subdivide_preserves_department() -> None:
    scraper = LeboncoinFRScraper()
    params = {**_YP, "department": "75"}
    subs = scraper.subdivide_segment(params)
    assert subs
    assert all(s["department"] == "75" and s["_fine"] is True for s in subs)
    assert all(s["year_from"] == s["year_to"] for s in subs)
    assert scraper.subdivide_segment(subs[0]) == []


@pytest.mark.unit
@pytest.mark.parametrize(
    "cls", [MobileDeScraper, MarktplaatsNLScraper, KleinanzeigenDEScraper, CochesNetScraper, LaCentraleFRScraper]
)
def test_subdivide_open_top_band_reopens_final_subband(cls) -> None:
    # Open-ended top band (price_to=None) must keep the last sub-band open.
    subs = cls().subdivide_segment(dict(_YP_OPEN))
    assert subs
    # For each single year, exactly one sub-band stays open (price_to is None).
    by_year: dict[int, list[Any]] = {}
    for s in subs:
        by_year.setdefault(s["year_from"], []).append(s["price_to"])
    for _year, tops in by_year.items():
        assert tops[-1] is None
        assert all(t is not None for t in tops[:-1])


# --------------------------------------------------------------------------- #
# _build_url / _build_body — exact request shaping
# --------------------------------------------------------------------------- #
@pytest.mark.unit
def test_mobile_build_url_full_and_open_price() -> None:
    full = MobileDeScraper()._build_url(_YP, 3)
    assert full == (
        "https://suchen.mobile.de/fahrzeuge/search.html?vc=Car&s=Car"
        "&fr=2018:2020&p=10000:20000"
        "&dam=false&sb=rel&od=up&ref=srp&isSearchRequest=true&pageNumber=3"
    )
    open_top = MobileDeScraper()._build_url(_YP_OPEN, 1)
    assert "&p=100000:&" in open_top  # empty max → open band
    assert open_top.endswith("&pageNumber=1")


@pytest.mark.unit
def test_kleinanzeigen_build_url_path_grammar() -> None:
    full = KleinanzeigenDEScraper()._build_url(_YP, 2)
    assert full == (
        "https://www.kleinanzeigen.de/s-autos"
        "/preis:10000:20000/seite:2/c216+autos.ez_i:2018,2020"
    )
    open_top = KleinanzeigenDEScraper()._build_url(_YP_OPEN, 1)
    assert "/preis:100000:/seite:1/" in open_top  # empty price max


@pytest.mark.unit
def test_lacentrale_build_url_is_zero_based_page() -> None:
    # page is 0-BASED: page_num 1 must request page=0 (the first page).
    full = LaCentraleFRScraper()._build_url(_YP, 1)
    assert full == (
        "https://www.lacentrale.fr/listing"
        "?yearMin=2018&yearMax=2020&priceMin=10000&priceMax=20000&page=0"
    )
    # page_num 3 → page=2; open top band omits priceMax entirely.
    open_top = LaCentraleFRScraper()._build_url(_YP_OPEN, 3)
    assert "priceMax" not in open_top
    assert open_top.endswith("&priceMin=100000&page=2")


@pytest.mark.unit
def test_marktplaats_build_url_cents_and_open_price() -> None:
    # _build_url takes an offset (fetch_segment computes (page_num-1)*PAGE_SIZE).
    full = MarktplaatsNLScraper()._build_url(_YP, 30)
    assert full == (
        "https://www.marktplaats.nl/lrp/api/search?l1CategoryId=91"
        "&offset=30&limit=30"
        "&attributeRanges[]=constructionYear:2018:2020"
        "&attributeRanges[]=PriceCents:1000000:2000000"
        "&sortBy=SORT_INDEX&sortOrder=DECREASING"
    )
    open_top = MarktplaatsNLScraper()._build_url(_YP_OPEN, 0)
    assert "PriceCents:10000000:&" in open_top  # 100_000 EUR → cents, empty max


@pytest.mark.unit
def test_leboncoin_build_body_envelope() -> None:
    body = LeboncoinFRScraper()._build_body({**_YP, "department": "75"}, offset=70)
    assert body["filters"]["category"]["id"] == "2"
    assert body["filters"]["ranges"]["regdate"] == {"min": 2018, "max": 2020}
    assert body["filters"]["ranges"]["price"] == {"min": 10_000, "max": 20_000}
    assert body["filters"]["location"]["locations"] == [
        {"locationType": "department", "department_id": "75"}
    ]
    assert body["limit"] == 35 and body["offset"] == 70
    assert body["sort_by"] == "time" and body["sort_order"] == "desc"


@pytest.mark.unit
def test_leboncoin_build_body_open_price_uses_ceiling() -> None:
    body = LeboncoinFRScraper()._build_body({**_YP_OPEN, "department": "01"}, offset=0)
    # Open top band → concrete numeric ceiling (the finder rejects a null max).
    assert body["filters"]["ranges"]["price"]["max"] == 1_000_000


@pytest.mark.unit
def test_coches_build_body_envelope() -> None:
    body = CochesNetScraper()._build_body(_YP, 4)
    assert body["pagination"] == {"page": 4, "size": 30}
    assert body["sort"] == {"order": "desc", "term": "relevance"}
    f = body["filters"]
    assert f["categoryType"] == "Car"
    assert f["offerTypeIds"] == [0]
    assert f["year"] == {"from": 2018, "to": 2020}
    assert f["price"] == {"from": 10_000, "to": 20_000}


@pytest.mark.unit
def test_coches_build_body_open_price_uses_ceiling() -> None:
    body = CochesNetScraper()._build_body(_YP_OPEN, 1)
    assert body["filters"]["price"]["to"] == 1_000_000


@pytest.mark.unit
def test_coches_headers_carry_adevinta_gateway_keys() -> None:
    headers = CochesNetScraper()._headers
    assert headers["x-adevinta-channel"] == "web-desktop"
    assert headers["x-schibsted-tenant"] == "coches"
    assert headers["Content-Type"] == "application/json"


@pytest.mark.unit
def test_leboncoin_headers_carry_public_api_key() -> None:
    headers = LeboncoinFRScraper()._headers
    assert headers["api_key"] == "ba0c2dad52b3ec"
    assert headers["Content-Type"] == "application/json"


# --------------------------------------------------------------------------- #
# _extract — parsing + within-page dedup
# --------------------------------------------------------------------------- #
@pytest.mark.unit
def test_mobile_extract_canonicalizes_and_dedups() -> None:
    html = (
        '<a href="/fahrzeuge/details.html?id=111&foo=bar">x</a>'
        '<a href="/fahrzeuge/details.html?id=222">y</a>'
        '<a href="/fahrzeuge/details.html?id=111">dup</a>'
        '<a href="/haendler/some-dealer">ignored</a>'
    )
    assert MobileDeScraper()._extract(html) == [
        "https://suchen.mobile.de/fahrzeuge/details.html?id=111",
        "https://suchen.mobile.de/fahrzeuge/details.html?id=222",
    ]


@pytest.mark.unit
def test_kleinanzeigen_extract_pulls_listing_paths() -> None:
    html = (
        '<a href="/s-anzeige/vw-golf/2001234-216-1">a</a>'
        '<a href="/s-anzeige/bmw-320d/2005678-216-44">b</a>'
        '<a href="/s-anzeige/vw-golf/2001234-216-1">dup</a>'
        '<a href="/s-bestandsliste.html">ignored</a>'
    )
    assert KleinanzeigenDEScraper()._extract(html) == [
        "https://www.kleinanzeigen.de/s-anzeige/vw-golf/2001234-216-1",
        "https://www.kleinanzeigen.de/s-anzeige/bmw-320d/2005678-216-44",
    ]


@pytest.mark.unit
def test_lacentrale_extract_builds_canonical_from_id() -> None:
    html = (
        '<a data-testid="vehicleCardV2" href="/auto-occasion-annonce-12345.html">x</a>'
        '<a href="/auto-occasion-annonce-67890.html">y</a>'
        '<a href="/auto-occasion-annonce-12345.html">dup</a>'
    )
    assert LaCentraleFRScraper()._extract(html) == [
        "https://www.lacentrale.fr/auto-occasion-annonce-12345.html",
        "https://www.lacentrale.fr/auto-occasion-annonce-67890.html",
    ]


@pytest.mark.unit
def test_marktplaats_extract_prefixes_vip_urls() -> None:
    body = json.dumps(
        {
            "listings": [
                {"itemId": "m111", "vipUrl": "/v/auto-s/audi/m111-a4"},
                {"itemId": "m222", "vipUrl": "https://www.marktplaats.nl/v/full/m222"},
                {"itemId": "m111", "vipUrl": "/v/auto-s/audi/m111-a4"},  # dup
                {"itemId": "m333"},  # no vipUrl → skipped
            ]
        }
    )
    assert MarktplaatsNLScraper()._extract(body) == [
        "https://www.marktplaats.nl/v/auto-s/audi/m111-a4",
        "https://www.marktplaats.nl/v/full/m222",
    ]


@pytest.mark.unit
def test_leboncoin_extract_prefers_url_else_builds_from_list_id() -> None:
    body = json.dumps(
        {
            "ads": [
                {"list_id": 111, "url": "https://www.leboncoin.fr/ad/voitures/111"},
                {"list_id": 222, "url": "/ad/voitures/222"},  # relative → prefixed
                {"list_id": 333},  # no url → built from list_id
                {"list_id": 111, "url": "https://www.leboncoin.fr/ad/voitures/111"},  # dup
            ]
        }
    )
    assert LeboncoinFRScraper()._extract(body) == [
        "https://www.leboncoin.fr/ad/voitures/111",
        "https://www.leboncoin.fr/ad/voitures/222",
        "https://www.leboncoin.fr/ad/voitures/333",
    ]


@pytest.mark.unit
def test_coches_extract_prefixes_relative_aspx() -> None:
    body = json.dumps(
        {
            "items": [
                {"id": 1, "url": "/vw-golf-2018/12345.aspx"},
                {"id": 2, "url": "https://www.coches.net/audi/67890.aspx"},
                {"id": 1, "url": "/vw-golf-2018/12345.aspx"},  # dup
                {"id": 3},  # no url → skipped
            ]
        }
    )
    assert CochesNetScraper()._extract(body) == [
        "https://www.coches.net/vw-golf-2018/12345.aspx",
        "https://www.coches.net/audi/67890.aspx",
    ]


@pytest.mark.unit
@pytest.mark.parametrize("cls", [MarktplaatsNLScraper, LeboncoinFRScraper, CochesNetScraper])
def test_json_extract_tolerates_garbage(cls) -> None:
    scraper = cls()
    assert scraper._extract("not json at all") == []
    assert scraper._extract("[]") == []  # list, not the expected object
    assert scraper._extract("{}") == []  # object without the listings key


# --------------------------------------------------------------------------- #
# fetch_segment — behavioural matrix (GET + POST share the signature)
# --------------------------------------------------------------------------- #
# (factory, params, success_body, expected_urls)
_OK_CASES = [
    (
        LeboncoinFRScraper,
        {**_YP, "department": "75"},
        json.dumps({"ads": [{"list_id": 9, "url": "/ad/voitures/9"}]}),
        ["https://www.leboncoin.fr/ad/voitures/9"],
    ),
    (
        CochesNetScraper,
        dict(_YP),
        json.dumps({"items": [{"url": "/seat/9.aspx"}]}),
        ["https://www.coches.net/seat/9.aspx"],
    ),
    (
        MarktplaatsNLScraper,
        dict(_YP),
        json.dumps({"listings": [{"itemId": "m9", "vipUrl": "/v/m9"}]}),
        ["https://www.marktplaats.nl/v/m9"],
    ),
    (
        MobileDeScraper,
        dict(_YP),
        '<a href="/fahrzeuge/details.html?id=9">x</a>',
        ["https://suchen.mobile.de/fahrzeuge/details.html?id=9"],
    ),
    (
        KleinanzeigenDEScraper,
        dict(_YP),
        '<a href="/s-anzeige/x/9-216-1">x</a>',
        ["https://www.kleinanzeigen.de/s-anzeige/x/9-216-1"],
    ),
    (
        LaCentraleFRScraper,
        dict(_YP),
        '<a href="/auto-occasion-annonce-9.html">x</a>',
        ["https://www.lacentrale.fr/auto-occasion-annonce-9.html"],
    ),
]


@pytest.mark.unit
@pytest.mark.parametrize("cls, params, body, expected", _OK_CASES)
def test_fetch_segment_extracts_on_200(cls, params, body, expected) -> None:
    scraper = cls()
    session = _Session([_Resp(200, body)])
    assert _run(scraper.fetch_segment(session, params, 1)) == expected
    assert len(session.calls) == 1


@pytest.mark.unit
@pytest.mark.parametrize("cls, params, body, expected", _OK_CASES)
def test_fetch_segment_retries_block_status_then_gives_up(cls, params, body, expected) -> None:
    scraper = cls()
    _no_backoff(scraper)
    session = _Session([_Resp(403), _Resp(403), _Resp(403)])
    assert _run(scraper.fetch_segment(session, params, 1)) == []
    assert len(session.calls) == scraper.RETRY_ATTEMPTS


@pytest.mark.unit
@pytest.mark.parametrize("cls, params, body, expected", _OK_CASES)
def test_fetch_segment_recovers_after_block(cls, params, body, expected) -> None:
    scraper = cls()
    _no_backoff(scraper)
    session = _Session([_Resp(403), _Resp(200, body)])
    assert _run(scraper.fetch_segment(session, params, 1)) == expected
    assert len(session.calls) == 2


@pytest.mark.unit
@pytest.mark.parametrize("cls, params, body, expected", _OK_CASES)
def test_fetch_segment_non_block_status_no_retry(cls, params, body, expected) -> None:
    scraper = cls()
    session = _Session([_Resp(404)])
    assert _run(scraper.fetch_segment(session, params, 1)) == []
    assert len(session.calls) == 1  # 404 is terminal, not retried


@pytest.mark.unit
@pytest.mark.parametrize("cls, params, body, expected", _OK_CASES)
def test_fetch_segment_retries_transport_error(cls, params, body, expected) -> None:
    scraper = cls()
    _no_backoff(scraper)
    session = _Session([ConnectionError("reset"), ConnectionError("reset"), _Resp(200, body)])
    assert _run(scraper.fetch_segment(session, params, 1)) == expected
    assert len(session.calls) == 3


# Soft-block (200 body that is actually a WAF challenge) — only the portals that
# do body-marker detection: leboncoin/lacentrale (DataDome), kleinanzeigen/mobile
# (Akamai). coches/marktplaats key off status only and are excluded.
_SOFTBLOCK_CASES = [
    (LeboncoinFRScraper, {**_YP, "department": "75"}, '{"url":"captcha-delivery.com/x"}'),
    (LaCentraleFRScraper, dict(_YP), "<html>captcha-delivery.com</html>"),
    (KleinanzeigenDEScraper, dict(_YP), "<html>Zugriff verweigert</html>"),
    (MobileDeScraper, dict(_YP), "<html>Access denied</html>"),
]


@pytest.mark.unit
@pytest.mark.parametrize("cls, params, challenge", _SOFTBLOCK_CASES)
def test_fetch_segment_retries_softblock_200(cls, params, challenge) -> None:
    scraper = cls()
    _no_backoff(scraper)
    session = _Session([_Resp(200, challenge), _Resp(200, challenge), _Resp(200, challenge)])
    assert _run(scraper.fetch_segment(session, params, 1)) == []
    assert len(session.calls) == scraper.RETRY_ATTEMPTS


@pytest.mark.unit
def test_post_portals_send_json_and_headers() -> None:
    # The two POST portals must carry their body + gateway/key headers verbatim.
    lbc = LeboncoinFRScraper()
    session = _Session([_Resp(200, json.dumps({"ads": []}))])
    _run(lbc.fetch_segment(session, {**_YP, "department": "75"}, 2))
    call = session.calls[0]
    assert call["method"] == "POST"
    assert call["url"] == "https://api.leboncoin.fr/finder/search"
    assert call["headers"]["api_key"] == "ba0c2dad52b3ec"
    assert call["json"]["offset"] == (2 - 1) * lbc.PAGE_SIZE  # page→offset math

    coches = CochesNetScraper()
    session = _Session([_Resp(200, json.dumps({"items": []}))])
    _run(coches.fetch_segment(session, dict(_YP), 5))
    call = session.calls[0]
    assert call["method"] == "POST"
    assert call["url"] == "https://ms-mt--api-web.spain.advgo.net/search"
    assert call["headers"]["x-schibsted-tenant"] == "coches"
    assert call["json"]["pagination"]["page"] == 5  # coches paginates 1-based


# --------------------------------------------------------------------------- #
# wiring — portal registry resolution
# --------------------------------------------------------------------------- #
@pytest.mark.unit
@pytest.mark.parametrize(
    "domain, cls",
    [
        ("leboncoin.fr", LeboncoinFRScraper),
        ("kleinanzeigen.de", KleinanzeigenDEScraper),
        ("coches.net", CochesNetScraper),
        ("lacentrale.fr", LaCentraleFRScraper),
        ("mobile.de", MobileDeScraper),
        ("marktplaats.nl", MarktplaatsNLScraper),
    ],
)
def test_registry_resolves_domain_to_scraper(domain, cls) -> None:
    scraper = get_scraper(domain)
    assert isinstance(scraper, cls)
    assert scraper.DOMAIN == domain


@pytest.mark.unit
def test_registry_returns_none_for_unknown_domain() -> None:
    assert get_scraper("nonexistent-portal.example") is None


# --------------------------------------------------------------------------- #
# wiring — domain→tier registry (the corrected baselines)
# --------------------------------------------------------------------------- #
@pytest.mark.unit
@pytest.mark.parametrize(
    "domain, tier, waf, ceiling",
    [
        ("marktplaats.nl", Tier.T0, WAF.NONE, None),
        ("coches.net", Tier.T1, WAF.NONE, Tier.T2),
        ("kleinanzeigen.de", Tier.T2, WAF.AKAMAI_V3, Tier.T3),
        ("mobile.de", Tier.T2, WAF.AKAMAI_V3, Tier.T3),
        ("leboncoin.fr", Tier.T3, WAF.DATADOME, None),
        ("lacentrale.fr", Tier.T3, WAF.DATADOME, None),
    ],
)
def test_domain_map_baselines(domain, tier, waf, ceiling) -> None:
    spec = domain_get(domain)
    assert spec is not None, f"{domain} missing from REGISTRY"
    assert spec.tier is tier
    assert spec.waf is waf
    assert spec.can_escalate_to is ceiling


@pytest.mark.unit
def test_domain_map_matches_www_subdomain() -> None:
    # The matcher allows optional leading subdomains, so www.<host> resolves too.
    assert domain_get("www.mobile.de").tier is Tier.T2
    assert domain_get("www.marktplaats.nl").tier is Tier.T0
