"""
Phase-5 portal scraper tests — 2dehands.be, viabovag.nl, tutti.ch, anibis.ch, autolina.ch.

Cada portal se ejerce directamente contra una sesión fake duck-typed (sin curl_cffi):
partition_params grid, one-level subdivide_segment terminación, _build_url request
shaping, _extract parsing + dedup, fetch_segment retry / status handling. Dos capas
de wiring también se afirman — el portal registry (`get_scraper`) y el domain→tier
registry (`domain_map`) — para que el drift de clase/string/tier salga aquí en vez
de en runtime.

Coroutines se ejecutan sincrónicamente vía asyncio.run() (convención del engine).
fetch_segment tests stub `_retry_backoff` a no-op para que la suite nunca duerma.
"""
from __future__ import annotations

import asyncio
from typing import Any

import pytest

from scrapers.engine.router.domain_map import Tier, WAF
from scrapers.engine.router.domain_map import get as domain_get
from scrapers.portals import get_scraper
from scrapers.portals.base import BasePortalScraper
from scrapers.portals.tweedehands_be import TweedehandsBEScraper


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


def _no_backoff(scraper: BasePortalScraper) -> None:
    """Stub del exponential backoff para que los tests de retry corran al instante."""

    async def _noop(attempt: int, factor: float = 1.0) -> None:
        return None

    scraper._retry_backoff = _noop  # type: ignore[method-assign]


_YP = {"year_from": 2018, "year_to": 2020, "price_from": 10_000, "price_to": 20_000}
_YP_OPEN = {"year_from": 2024, "year_to": 2026, "price_from": 100_000, "price_to": None}


# =========================================================================== #
# 2dehands.be — API LRP (clon de marktplaats.nl)
# =========================================================================== #
@pytest.mark.unit
def test_tweedehands_partition_shape() -> None:
    scraper = TweedehandsBEScraper()
    segments = scraper.partition_params()
    assert len(segments) == len(scraper.YEAR_BANDS) * len(scraper.PRICE_BANDS)
    keys = {(s["year_from"], s["year_to"], s["price_from"], s["price_to"]) for s in segments}
    assert len(keys) == len(segments)
    assert not any("_fine" in s for s in segments)


@pytest.mark.unit
def test_tweedehands_subdivide_then_stops() -> None:
    scraper = TweedehandsBEScraper()
    subs = scraper.subdivide_segment(dict(_YP))
    assert subs
    for s in subs:
        assert s["year_from"] == s["year_to"]
        assert s["_fine"] is True
    assert {s["year_from"] for s in subs} == {2018, 2019, 2020}
    assert scraper.subdivide_segment(subs[0]) == []


@pytest.mark.unit
def test_tweedehands_subdivide_open_top_band_reopens_final_subband() -> None:
    subs = TweedehandsBEScraper().subdivide_segment(dict(_YP_OPEN))
    assert subs
    by_year: dict[int, list[Any]] = {}
    for s in subs:
        by_year.setdefault(s["year_from"], []).append(s["price_to"])
    for tops in by_year.values():
        assert tops[-1] is None
        assert all(t is not None for t in tops[:-1])


@pytest.mark.unit
def test_tweedehands_build_url_full_and_open_price() -> None:
    scraper = TweedehandsBEScraper()
    full = scraper._build_url(_YP, 0)
    assert full == (
        "https://www.2dehands.be/lrp/api/search?l1CategoryId=91"
        "&offset=0&limit=30"
        "&attributeRanges[]=constructionYear:2018:2020"
        "&attributeRanges[]=PriceCents:1000000:2000000"
        "&sortBy=SORT_INDEX&sortOrder=DECREASING"
    )
    open_top = scraper._build_url(_YP_OPEN, 60)
    assert "PriceCents:10000000:" in open_top  # 100_000 * 100 = 10_000_000
    assert open_top.endswith("&sortBy=SORT_INDEX&sortOrder=DECREASING")
    assert "&offset=60&" in open_top


@pytest.mark.unit
def test_tweedehands_extract_pulls_vipurl_and_dedups() -> None:
    import json

    body = json.dumps({
        "listings": [
            {"vipUrl": "/v/auto-s/audi/a3/m2001234567", "itemId": "m2001234567"},
            {"vipUrl": "/v/auto-s/bmw/3-serie/m2001234568", "itemId": "m2001234568"},
            {"vipUrl": "/v/auto-s/audi/a3/m2001234567", "itemId": "m2001234567"},  # dup
        ]
    })
    assert TweedehandsBEScraper()._extract(body) == [
        "https://www.2dehands.be/v/auto-s/audi/a3/m2001234567",
        "https://www.2dehands.be/v/auto-s/bmw/3-serie/m2001234568",
    ]


@pytest.mark.unit
def test_tweedehands_extract_handles_absolute_urls() -> None:
    import json

    body = json.dumps({
        "listings": [
            {"vipUrl": "https://www.2dehands.be/v/auto-s/vw/golf/m123", "itemId": "m123"},
        ]
    })
    assert TweedehandsBEScraper()._extract(body) == [
        "https://www.2dehands.be/v/auto-s/vw/golf/m123",
    ]


@pytest.mark.unit
def test_tweedehands_extract_returns_empty_on_garbage() -> None:
    assert TweedehandsBEScraper()._extract("") == []
    assert TweedehandsBEScraper()._extract("not json") == []
    assert TweedehandsBEScraper()._extract('{"listings": "not a list"}') == []
    assert TweedehandsBEScraper()._extract('{"other": []}') == []


# --------------------------------------------------------------------------- #
# fetch_segment — behavioural matrix (2dehands.be)
# --------------------------------------------------------------------------- #
import json as _json

_TWEEDEHANDS_JSON = _json.dumps({
    "listings": [
        {"vipUrl": "/v/auto-s/seat/leon/m999", "itemId": "m999"},
    ]
})
_TWEEDEHANDS_EXPECTED = ["https://www.2dehands.be/v/auto-s/seat/leon/m999"]


@pytest.mark.unit
def test_tweedehands_fetch_segment_extracts_on_200() -> None:
    scraper = TweedehandsBEScraper()
    session = _Session([_Resp(200, _TWEEDEHANDS_JSON)])
    assert _run(scraper.fetch_segment(session, _YP, 1)) == _TWEEDEHANDS_EXPECTED
    assert len(session.calls) == 1


@pytest.mark.unit
def test_tweedehands_fetch_segment_retries_block_status_then_gives_up() -> None:
    scraper = TweedehandsBEScraper()
    _no_backoff(scraper)
    session = _Session([_Resp(429), _Resp(503), _Resp(403)])
    assert _run(scraper.fetch_segment(session, _YP, 1)) == []
    assert len(session.calls) == scraper.RETRY_ATTEMPTS


@pytest.mark.unit
def test_tweedehands_fetch_segment_recovers_after_block() -> None:
    scraper = TweedehandsBEScraper()
    _no_backoff(scraper)
    session = _Session([_Resp(503), _Resp(200, _TWEEDEHANDS_JSON)])
    assert _run(scraper.fetch_segment(session, _YP, 1)) == _TWEEDEHANDS_EXPECTED
    assert len(session.calls) == 2


@pytest.mark.unit
def test_tweedehands_fetch_segment_non_block_status_no_retry() -> None:
    scraper = TweedehandsBEScraper()
    session = _Session([_Resp(404)])
    assert _run(scraper.fetch_segment(session, _YP, 1)) == []
    assert len(session.calls) == 1


@pytest.mark.unit
def test_tweedehands_fetch_segment_retries_transport_error() -> None:
    scraper = TweedehandsBEScraper()
    _no_backoff(scraper)
    session = _Session([ConnectionError("reset"), ConnectionError("reset"), _Resp(200, _TWEEDEHANDS_JSON)])
    assert _run(scraper.fetch_segment(session, _YP, 1)) == _TWEEDEHANDS_EXPECTED
    assert len(session.calls) == 3


# --------------------------------------------------------------------------- #
# wiring — portal registry & domain→tier registry
# --------------------------------------------------------------------------- #
@pytest.mark.unit
def test_tweedehands_registry_resolves() -> None:
    scraper = get_scraper("2dehands.be")
    assert isinstance(scraper, TweedehandsBEScraper)
    assert scraper.DOMAIN == "2dehands.be"


@pytest.mark.unit
def test_tweedehands_domain_map_baseline() -> None:
    spec = domain_get("2dehands.be")
    assert spec is not None, "2dehands.be missing from REGISTRY"
    assert spec.tier is Tier.T0
    assert spec.waf is WAF.NONE
    assert spec.can_escalate_to is None
