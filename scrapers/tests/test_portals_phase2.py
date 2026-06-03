"""
Phase-2 portal tests — HttpPortalScraper base + the six direct-HTTP portals.

Two layers, mirroring test_portals.py's split:

  * HttpPortalScraper is the request-shape-agnostic base that generalizes the AS24
    retry / soft-block / extraction loop and owns the year×price search grid. Its
    primitives (grid partition, price-split subdivision, the GET/POST send + retry
    loop, the WAF soft-block default) are exercised here against fakes.
  * The six concrete portals (mobile.de SRP, leboncoin, kleinanzeigen, coches.net,
    marktplaats, lacentrale) each declare only _build_request + _extract (+ one
    soft-block override for mobile.de's Akamai access-denied page). Those facts are
    asserted directly: exact request shape, extraction + dedup, and routing tier.

Coroutines run synchronously via asyncio.run(). The fake session matches the
http_base _send contract — get(url, headers, timeout) and post(url, json, headers,
timeout) — which the AS24 fake in test_portals.py does not, hence a fresh fake here.
"""
from __future__ import annotations

import asyncio
from typing import Any

import pytest

from scrapers.engine.identity import store
from scrapers.engine.router import domain_map as dm
from scrapers.engine.router.domain_map import Tier
from scrapers.portals import PORTAL_REGISTRY, get_scraper
from scrapers.portals.base import RunStatus
from scrapers.portals.http_base import (
    PRICE_RANGES,
    YEAR_BANDS,
    HttpPortalScraper,
    PortalRequest,
    split_price,
)
from scrapers.portals.cochesnet import CochesNetScraper
from scrapers.portals.kleinanzeigen import KleinanzeigenScraper
from scrapers.portals.lacentrale import LaCentraleScraper
from scrapers.portals.leboncoin import LeBonCoinScraper
from scrapers.portals.marktplaats import MarktplaatsScraper
from scrapers.portals.mobile_de import MobileDeScraper


def _run(coro: Any) -> Any:
    return asyncio.run(coro)


# --------------------------------------------------------------------------- #
# fakes — match the http_base _send contract (GET headers, POST json+headers)
# --------------------------------------------------------------------------- #
class _Resp:
    """Duck-typed response: .status_code/.text/.json()/.headers/.cookies."""

    def __init__(
        self,
        status_code: int,
        text: str = "",
        json_data: Any = None,
        headers: dict | None = None,
        cookies: dict | None = None,
    ) -> None:
        self.status_code = status_code
        self.text = text
        self._json = json_data
        self.headers = headers or {}
        self.cookies = cookies or {}

    def json(self) -> Any:
        if self._json is None:
            raise ValueError("response body is not JSON")
        return self._json


class _Session:
    """Fake AsyncSession recording GET/POST calls; yields queued responses/raises."""

    def __init__(self, responses: list[Any]) -> None:
        self._responses = list(responses)
        self.gets: list[tuple[str, dict | None]] = []
        self.posts: list[tuple[str, Any, dict | None]] = []

    async def get(self, url: str, headers: dict | None = None, timeout: int | None = None) -> Any:
        self.gets.append((url, headers))
        return self._next()

    async def post(
        self, url: str, json: Any = None, headers: dict | None = None, timeout: int | None = None
    ) -> Any:
        self.posts.append((url, json, headers))
        return self._next()

    def _next(self) -> Any:
        item = self._responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def _no_backoff(scraper: HttpPortalScraper) -> None:
    async def _noop(attempt: int, factor: float = 1.0) -> None:
        return None

    scraper._retry_backoff = _noop  # type: ignore[method-assign]


_SEG = {"year_from": 2018, "year_to": 2020, "price_from": 5000, "price_to": 10000}
_SEG_OPEN = {"year_from": 2018, "year_to": 2020, "price_from": 100000, "price_to": None}


# --------------------------------------------------------------------------- #
# shared search grid — split_price / partition / subdivision
# --------------------------------------------------------------------------- #
@pytest.mark.unit
def test_split_price_halves_a_bounded_window() -> None:
    assert split_price(5000, 10000) == [(5000, 7500), (7500, 10000)]


@pytest.mark.unit
def test_split_price_open_ended_window_cannot_split() -> None:
    assert split_price(100000, None) == []


@pytest.mark.unit
def test_split_price_window_at_or_below_min_width_is_not_split() -> None:
    # 0..500 is exactly the floor → finer subdivision cannot help.
    assert split_price(0, 500) == []


@pytest.mark.unit
def test_partition_is_year_bands_times_disjoint_price_windows() -> None:
    scraper = MobileDeScraper()
    segments = scraper.partition_params()
    assert len(segments) == len(YEAR_BANDS) * len(PRICE_RANGES) == 88
    # Every segment is a unique (year_from, year_to, price_from, price_to) tuple.
    keys = {(s["year_from"], s["year_to"], s["price_from"], s["price_to"]) for s in segments}
    assert len(keys) == len(segments)
    # Price windows are disjoint: each segment's [from, to) is one of PRICE_RANGES.
    assert {(s["price_from"], s["price_to"]) for s in segments} == set(PRICE_RANGES)


@pytest.mark.unit
def test_subdivide_bounded_segment_yields_two_halves() -> None:
    subs = MobileDeScraper().subdivide_segment(_SEG)
    assert subs == [
        {"year_from": 2018, "year_to": 2020, "price_from": 5000, "price_to": 7500},
        {"year_from": 2018, "year_to": 2020, "price_from": 7500, "price_to": 10000},
    ]


@pytest.mark.unit
def test_subdivide_open_ended_segment_yields_nothing() -> None:
    assert MobileDeScraper().subdivide_segment(_SEG_OPEN) == []


# --------------------------------------------------------------------------- #
# per-portal config
# --------------------------------------------------------------------------- #
@pytest.mark.unit
@pytest.mark.parametrize(
    "cls, domain, country, page_size, max_pages",
    [
        (MobileDeScraper, "suchen.mobile.de", "DE", 20, 50),
        (LeBonCoinScraper, "leboncoin.fr", "FR", 35, 100),
        (KleinanzeigenScraper, "kleinanzeigen.de", "DE", 25, 50),
        (CochesNetScraper, "coches.net", "ES", 30, 50),
        (MarktplaatsScraper, "marktplaats.nl", "NL", 30, 30),
        (LaCentraleScraper, "lacentrale.fr", "FR", 16, 100),
    ],
)
def test_portal_config(cls, domain, country, page_size, max_pages) -> None:
    scraper = cls()
    assert scraper.DOMAIN == domain
    assert scraper.COUNTRY == country
    assert scraper.PAGE_SIZE == page_size
    assert scraper.MAX_PAGES == max_pages
    assert len(scraper.partition_params()) == 88


# --------------------------------------------------------------------------- #
# mobile.de — GET HTML, Akamai access-denied override
# --------------------------------------------------------------------------- #
@pytest.mark.unit
def test_mobile_de_build_request_url() -> None:
    s = MobileDeScraper()
    assert s._build_request(_SEG, 2).url == (
        "https://suchen.mobile.de/fahrzeuge/search.html"
        "?vc=Car&isSearchRequest=true&ref=srp&sb=rel&od=up&dam=false"
        "&fr=2018:2020&p=5000:10000&pageNumber=2"
    )
    # Open-ended price → trailing empty upper bound.
    assert s._build_request(_SEG_OPEN, 1).url.endswith("&p=100000:&pageNumber=1")


@pytest.mark.unit
def test_mobile_de_extract_dedups_and_prefixes() -> None:
    html = (
        'href="/fahrzeuge/details.html?id=111"'
        'href="/fahrzeuge/details.html?id=222"'
        'href="/fahrzeuge/details.html?id=111"'  # duplicate
        'href="/haendler/x"'                       # not a listing
    )
    assert MobileDeScraper()._extract(_Resp(200, html)) == [
        "https://suchen.mobile.de/fahrzeuge/details.html?id=111",
        "https://suchen.mobile.de/fahrzeuge/details.html?id=222",
    ]


@pytest.mark.unit
def test_mobile_de_soft_block_on_akamai_access_denied_200() -> None:
    s = MobileDeScraper()
    # A clean 200 is not a soft block; the Akamai "Access Denied" 200 page is.
    assert s._is_soft_block(_Resp(200, "<html>normal results</html>")) is False
    assert s._is_soft_block(_Resp(200, "<h1>Access Denied</h1> Reference #18.abc")) is True


# --------------------------------------------------------------------------- #
# leboncoin — POST JSON finder, DataDome default soft-block
# --------------------------------------------------------------------------- #
@pytest.mark.unit
def test_leboncoin_build_request_body_and_headers() -> None:
    req = LeBonCoinScraper()._build_request(_SEG, 3)
    assert req.method == "POST"
    assert req.url == "https://api.leboncoin.fr/finder/search"
    assert req.json_body["filters"]["category"]["id"] == "2"
    assert req.json_body["filters"]["ranges"]["regdate"] == {"min": 2018, "max": 2020}
    assert req.json_body["filters"]["ranges"]["price"] == {"min": 5000, "max": 10000}
    assert req.json_body["offset"] == 70  # (page 3 - 1) * 35
    assert req.json_body["limit"] == 35
    assert req.headers["api_key"]
    assert req.headers["Origin"] == "https://www.leboncoin.fr"


@pytest.mark.unit
def test_leboncoin_build_request_omits_price_max_when_open_ended() -> None:
    req = LeBonCoinScraper()._build_request(_SEG_OPEN, 1)
    assert req.json_body["filters"]["ranges"]["price"] == {"min": 100000}


@pytest.mark.unit
def test_leboncoin_extract_pulls_ad_urls_with_guards() -> None:
    payload = {
        "ads": [
            {"url": "https://www.leboncoin.fr/voitures/1.htm"},
            {"url": "https://www.leboncoin.fr/voitures/2.htm"},
            {"url": "https://www.leboncoin.fr/voitures/1.htm"},  # duplicate
            {"no_url": True},                                     # missing url
            "not-a-dict",                                         # wrong type
        ]
    }
    assert LeBonCoinScraper()._extract(_Resp(200, json_data=payload)) == [
        "https://www.leboncoin.fr/voitures/1.htm",
        "https://www.leboncoin.fr/voitures/2.htm",
    ]


@pytest.mark.unit
def test_leboncoin_extract_non_dict_payload_is_empty() -> None:
    assert LeBonCoinScraper()._extract(_Resp(200, json_data=[1, 2, 3])) == []
    # Non-JSON body → _response_json returns None → []
    assert LeBonCoinScraper()._extract(_Resp(200, text="<html/>")) == []


# --------------------------------------------------------------------------- #
# kleinanzeigen — GET HTML
# --------------------------------------------------------------------------- #
@pytest.mark.unit
def test_kleinanzeigen_build_request_url() -> None:
    s = KleinanzeigenScraper()
    assert s._build_request(_SEG, 2).url == (
        "https://www.kleinanzeigen.de/s-autos/preis:5000:10000/seite:2"
        "/c216+autos.ez_i:2018,2020"
    )
    assert s._build_request(_SEG_OPEN, 1).url == (
        "https://www.kleinanzeigen.de/s-autos/preis:100000:/seite:1"
        "/c216+autos.ez_i:2018,2020"
    )


@pytest.mark.unit
def test_kleinanzeigen_extract_dedups_and_prefixes() -> None:
    html = (
        'href="/s-anzeige/bmw-320d/2890-216-1234"'
        'href="/s-anzeige/audi-a4/2891-216-5678"'
        'href="/s-anzeige/bmw-320d/2890-216-1234"'  # duplicate
        'href="/s-bmw/some-search"'                  # not a listing
    )
    assert KleinanzeigenScraper()._extract(_Resp(200, html)) == [
        "https://www.kleinanzeigen.de/s-anzeige/bmw-320d/2890-216-1234",
        "https://www.kleinanzeigen.de/s-anzeige/audi-a4/2891-216-5678",
    ]


# --------------------------------------------------------------------------- #
# coches.net — POST JSON (Adevinta)
# --------------------------------------------------------------------------- #
@pytest.mark.unit
def test_coches_build_request_body_and_headers() -> None:
    req = CochesNetScraper()._build_request(_SEG, 4)
    assert req.method == "POST"
    assert req.json_body["pagination"] == {"page": 4, "size": 30}
    assert req.json_body["filters"]["price"] == {"from": 5000, "to": 10000}
    assert req.json_body["filters"]["year"] == {"from": 2018, "to": 2020}
    assert req.headers["X-Schibsted-Tenant"] == "coches"


@pytest.mark.unit
def test_coches_build_request_omits_price_to_when_open_ended() -> None:
    req = CochesNetScraper()._build_request(_SEG_OPEN, 1)
    assert req.json_body["filters"]["price"] == {"from": 100000}


@pytest.mark.unit
def test_coches_extract_pulls_item_urls_with_guards() -> None:
    payload = {
        "items": [
            {"url": "https://www.coches.net/audi-a4-2018-12345678.aspx"},
            {"url": "https://www.coches.net/bmw-320d-2019-22222222.aspx"},
            {"url": "https://www.coches.net/audi-a4-2018-12345678.aspx"},  # dup
            {"id": 999},                                                    # no url
            42,                                                             # wrong type
        ]
    }
    assert CochesNetScraper()._extract(_Resp(200, json_data=payload)) == [
        "https://www.coches.net/audi-a4-2018-12345678.aspx",
        "https://www.coches.net/bmw-320d-2019-22222222.aspx",
    ]
    assert CochesNetScraper()._extract(_Resp(200, json_data={"nope": []})) == []


# --------------------------------------------------------------------------- #
# marktplaats — GET returning JSON (lrp)
# --------------------------------------------------------------------------- #
@pytest.mark.unit
def test_marktplaats_build_request_url_cents_and_offset() -> None:
    s = MarktplaatsScraper()
    assert s._build_request(_SEG, 2).url == (
        "https://www.marktplaats.nl/lrp/api/search?l1CategoryId=91"
        "&offset=30&limit=30"
        "&attributesByKey[]=PriceCents:500000:1000000"
        "&attributesByKey[]=constructionYear:2018:2020"
    )
    # Open-ended price → empty upper cents bound.
    assert "PriceCents:10000000:&" in s._build_request(_SEG_OPEN, 1).url


@pytest.mark.unit
def test_marktplaats_extract_prefixes_relative_keeps_absolute_dedups() -> None:
    payload = {
        "listings": [
            {"vipUrl": "/v/auto-s/bmw/m1"},
            {"vipUrl": "https://www.marktplaats.nl/v/auto-s/audi/m2"},
            {"vipUrl": "/v/auto-s/bmw/m1"},  # duplicate
            {"noUrl": 1},                     # missing vipUrl
        ]
    }
    assert MarktplaatsScraper()._extract(_Resp(200, json_data=payload)) == [
        "https://www.marktplaats.nl/v/auto-s/bmw/m1",
        "https://www.marktplaats.nl/v/auto-s/audi/m2",
    ]
    assert MarktplaatsScraper()._extract(_Resp(200, text="not json")) == []


# --------------------------------------------------------------------------- #
# lacentrale — GET HTML, DataDome default soft-block
# --------------------------------------------------------------------------- #
@pytest.mark.unit
def test_lacentrale_build_request_url() -> None:
    s = LaCentraleScraper()
    assert s._build_request(_SEG, 3).url == (
        "https://www.lacentrale.fr/listing?priceMin=5000&priceMax=10000"
        "&yearMin=2018&yearMax=2020&page=3"
    )
    # Open-ended price omits priceMax entirely.
    open_url = s._build_request(_SEG_OPEN, 1).url
    assert "priceMax" not in open_url
    assert open_url == (
        "https://www.lacentrale.fr/listing?priceMin=100000"
        "&yearMin=2018&yearMax=2020&page=1"
    )


@pytest.mark.unit
def test_lacentrale_extract_dedups_and_builds_full_url() -> None:
    html = (
        'href="/auto-occasion-annonce-69123456.html"'
        'href="/auto-occasion-annonce-69987654.html"'
        'href="/auto-occasion-annonce-69123456.html"'  # duplicate
        'href="/voiture-occasion.html"'                  # not a listing
    )
    assert LaCentraleScraper()._extract(_Resp(200, html)) == [
        "https://www.lacentrale.fr/auto-occasion-annonce-69123456.html",
        "https://www.lacentrale.fr/auto-occasion-annonce-69987654.html",
    ]


# --------------------------------------------------------------------------- #
# fetch_segment — the shared http_base retry/softblock/transport loop
# --------------------------------------------------------------------------- #
@pytest.mark.unit
def test_fetch_segment_get_extracts_on_200() -> None:
    s = KleinanzeigenScraper()
    html = 'href="/s-anzeige/bmw/1-216-1"'
    session = _Session([_Resp(200, html)])
    urls = _run(s.fetch_segment(session, _SEG, 1))
    assert urls == ["https://www.kleinanzeigen.de/s-anzeige/bmw/1-216-1"]
    # GET path: one request, no extra headers layered by the portal.
    assert len(session.gets) == 1 and session.posts == []
    assert session.gets[0][1] is None


@pytest.mark.unit
def test_fetch_segment_post_sends_json_and_headers() -> None:
    s = CochesNetScraper()
    payload = {"items": [{"url": "https://www.coches.net/x-1.aspx"}]}
    session = _Session([_Resp(200, json_data=payload)])
    urls = _run(s.fetch_segment(session, _SEG, 1))
    assert urls == ["https://www.coches.net/x-1.aspx"]
    # POST path: json body + portal headers forwarded to the session.
    assert len(session.posts) == 1 and session.gets == []
    sent_url, sent_json, sent_headers = session.posts[0]
    assert sent_json["pagination"]["page"] == 1
    assert sent_headers["X-Adevinta-Channel"] == "web"


@pytest.mark.unit
def test_fetch_segment_retries_block_status_then_gives_up() -> None:
    s = KleinanzeigenScraper()
    _no_backoff(s)
    session = _Session([_Resp(403), _Resp(429), _Resp(503)])
    urls = _run(s.fetch_segment(session, _SEG, 1))
    assert urls == []
    assert len(session.gets) == s.RETRY_ATTEMPTS


@pytest.mark.unit
def test_fetch_segment_recovers_after_block() -> None:
    s = KleinanzeigenScraper()
    _no_backoff(s)
    html = 'href="/s-anzeige/ok/9-216-9"'
    session = _Session([_Resp(403), _Resp(200, html)])
    urls = _run(s.fetch_segment(session, _SEG, 1))
    assert urls == ["https://www.kleinanzeigen.de/s-anzeige/ok/9-216-9"]
    assert len(session.gets) == 2


@pytest.mark.unit
def test_fetch_segment_retries_cloudflare_softblock_200() -> None:
    s = KleinanzeigenScraper()
    _no_backoff(s)
    challenge = "<html><title>Just a moment...</title>checking your browser</html>"
    session = _Session([_Resp(200, challenge)] * s.RETRY_ATTEMPTS)
    urls = _run(s.fetch_segment(session, _SEG, 1))
    assert urls == []
    assert len(session.gets) == s.RETRY_ATTEMPTS


@pytest.mark.unit
def test_fetch_segment_retries_datadome_softblock_200() -> None:
    s = LeBonCoinScraper()
    _no_backoff(s)
    challenge = '{"redirect":"https://geo.captcha-delivery.com/captcha/"}'
    session = _Session([_Resp(200, challenge)] * s.RETRY_ATTEMPTS)
    urls = _run(s.fetch_segment(session, _SEG, 1))
    assert urls == []
    assert len(session.posts) == s.RETRY_ATTEMPTS


@pytest.mark.unit
def test_fetch_segment_non_block_status_returns_empty_no_retry() -> None:
    s = KleinanzeigenScraper()
    session = _Session([_Resp(404)])
    urls = _run(s.fetch_segment(session, _SEG, 1))
    assert urls == []
    assert len(session.gets) == 1


@pytest.mark.unit
def test_fetch_segment_retries_transport_error() -> None:
    s = KleinanzeigenScraper()
    _no_backoff(s)
    html = 'href="/s-anzeige/z/0-216-0"'
    session = _Session([ConnectionError("reset"), ConnectionError("reset"), _Resp(200, html)])
    urls = _run(s.fetch_segment(session, _SEG, 1))
    assert urls == ["https://www.kleinanzeigen.de/s-anzeige/z/0-216-0"]
    assert len(session.gets) == 3


# --------------------------------------------------------------------------- #
# run() orchestration — the new primitives drive the inherited template method
# --------------------------------------------------------------------------- #
class _HttpFakePortal(HttpPortalScraper):
    """Tiny HttpPortalScraper to exercise run() end-to-end through the base loop.

    DOMAIN is autoscout24.de (T2) only to reuse the tier/identity path the
    active_identity fixture is built for; the request/extract shape is synthetic.
    """

    DOMAIN = "autoscout24.de"
    COUNTRY = "DE"
    PAGE_SIZE = 2
    MAX_PAGES = 3
    SLEEP_BASE = 0.0
    SLEEP_JITTER = 0.0

    def partition_params(self) -> list[dict]:
        return [{"year_from": 2020, "year_to": 2022, "price_from": 0, "price_to": 5000}]

    def _build_request(self, params, page_num) -> PortalRequest:
        return PortalRequest(url=f"https://example.test/p{page_num}")

    def _extract(self, response) -> list[str]:
        return [u for u in self._response_text(response).split() if u]


@pytest.mark.unit
def test_run_collects_urls_and_rewards_trust(conn, active_identity) -> None:
    scraper = _HttpFakePortal()
    # page 1 full (2 urls) → continue; page 2 short (1 url) → segment exhausts.
    session = _Session([_Resp(200, "u1 u2"), _Resp(200, "u3")])

    sink: list[str] = []

    async def on_urls(urls: list[str]) -> None:
        sink.extend(urls)

    before = store.get(conn, active_identity.id).trust_score
    result = _run(scraper.run(conn, session, on_urls=on_urls))
    after = store.get(conn, active_identity.id).trust_score

    assert result.status is RunStatus.OK
    assert sorted(result.urls) == ["u1", "u2", "u3"]
    assert result.segments == 1
    assert sorted(sink) == ["u1", "u2", "u3"]
    assert after == pytest.approx(before + 0.05)
    # Two GET pages were fetched through the real http_base send path.
    assert len(session.gets) == 2


# --------------------------------------------------------------------------- #
# registry + routing
# --------------------------------------------------------------------------- #
@pytest.mark.unit
@pytest.mark.parametrize(
    "domain, cls",
    [
        ("suchen.mobile.de", MobileDeScraper),
        ("leboncoin.fr", LeBonCoinScraper),
        ("kleinanzeigen.de", KleinanzeigenScraper),
        ("coches.net", CochesNetScraper),
        ("marktplaats.nl", MarktplaatsScraper),
        ("lacentrale.fr", LaCentraleScraper),
    ],
)
def test_get_scraper_resolves_each_portal(domain, cls) -> None:
    assert PORTAL_REGISTRY[domain] is cls
    assert isinstance(get_scraper(domain), cls)


@pytest.mark.unit
def test_routing_tiers_for_phase2_portals() -> None:
    assert dm.get("suchen.mobile.de").tier is Tier.T2
    assert dm.get("suchen.mobile.de").can_escalate_to is Tier.T3
    # The bare mobile.de T0 mobile-API path must be preserved (first-match-wins).
    assert dm.get("mobile.de").tier is Tier.T0
    assert dm.get("www.mobile.de") is not None
    assert dm.get("leboncoin.fr").tier is Tier.T3
    assert dm.get("lacentrale.fr").tier is Tier.T3
    assert dm.get("kleinanzeigen.de").tier is Tier.T1
    assert dm.get("marktplaats.nl").tier is Tier.T1
    assert dm.get("coches.net").tier is Tier.T1
    assert dm.get("coches.net").can_escalate_to is Tier.T2
