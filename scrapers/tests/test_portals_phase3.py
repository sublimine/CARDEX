"""
Phase-3 portal scraper tests — Tier-0/Tier-1 high-volume targets.

Covered: paruvendu.fr (T1 Apache GET).

Each portal's primitives are exercised directly against a fake duck-typed session
(no curl_cffi): partition_params grid, one-level subdivide_segment termination,
_build_url request shaping, _extract parsing + dedup, fetch_segment retry / status
handling. Two wiring layers are also asserted — the portal registry (`get_scraper`)
and the domain→tier registry (`domain_map`) — so class/string/tier drift surfaces
here rather than at runtime.

Coroutines run synchronously via asyncio.run() (engine convention). fetch_segment
tests stub `_retry_backoff` to a no-op so the suite never sleeps.
"""
from __future__ import annotations

import asyncio
from typing import Any

import pytest

from scrapers.engine.router.domain_map import Tier, WAF
from scrapers.engine.router.domain_map import get as domain_get
from scrapers.portals import get_scraper
from scrapers.portals.base import BasePortalScraper
from scrapers.portals.paruvendu_fr import ParuVenduFRScraper


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
    """Stub the exponential backoff so retry tests run instantly."""

    async def _noop(attempt: int, factor: float = 1.0) -> None:
        return None

    scraper._retry_backoff = _noop  # type: ignore[method-assign]


_YP = {"year_from": 2018, "year_to": 2020, "price_from": 10_000, "price_to": 20_000}
_YP_OPEN = {"year_from": 2024, "year_to": 2026, "price_from": 100_000, "price_to": None}

_PHASE3 = [ParuVenduFRScraper]


# --------------------------------------------------------------------------- #
# partition_params — grid shape & uniqueness
# --------------------------------------------------------------------------- #
@pytest.mark.unit
@pytest.mark.parametrize("cls", _PHASE3)
def test_partition_shape(cls) -> None:
    scraper = cls()
    segments = scraper.partition_params()
    assert len(segments) == len(scraper.YEAR_BANDS) * len(scraper.PRICE_BANDS)
    keys = {(s["year_from"], s["year_to"], s["price_from"], s["price_to"]) for s in segments}
    assert len(keys) == len(segments)
    assert not any("_fine" in s for s in segments)


# --------------------------------------------------------------------------- #
# subdivide_segment — one-level explosion then termination
# --------------------------------------------------------------------------- #
@pytest.mark.unit
@pytest.mark.parametrize("cls", _PHASE3)
def test_subdivide_then_stops(cls) -> None:
    scraper = cls()
    subs = scraper.subdivide_segment(dict(_YP))
    assert subs
    for s in subs:
        assert s["year_from"] == s["year_to"]
        assert s["_fine"] is True
    assert {s["year_from"] for s in subs} == {2018, 2019, 2020}
    assert scraper.subdivide_segment(subs[0]) == []


@pytest.mark.unit
@pytest.mark.parametrize("cls", _PHASE3)
def test_subdivide_open_top_band_reopens_final_subband(cls) -> None:
    subs = cls().subdivide_segment(dict(_YP_OPEN))
    assert subs
    by_year: dict[int, list[Any]] = {}
    for s in subs:
        by_year.setdefault(s["year_from"], []).append(s["price_to"])
    for tops in by_year.values():
        assert tops[-1] is None
        assert all(t is not None for t in tops[:-1])


# --------------------------------------------------------------------------- #
# paruvendu.fr — request shape & extraction
# --------------------------------------------------------------------------- #
@pytest.mark.unit
def test_paruvendu_build_url_full_and_open_price() -> None:
    full = ParuVenduFRScraper()._build_url(_YP, 3)
    assert full == (
        "https://www.paruvendu.fr/auto-moto/listefo/default/default"
        "?r=VVO00000&p=3&px0=10000&px1=20000&a0=2018&a1=2020"
    )
    open_top = ParuVenduFRScraper()._build_url(_YP_OPEN, 1)
    assert "px1=" not in open_top
    assert open_top.endswith("&px0=100000&a0=2024&a1=2026")
    assert "&p=1&" in open_top


@pytest.mark.unit
def test_paruvendu_extract_canonicalizes_and_dedups() -> None:
    html = (
        '<a href="/a/voiture-occasion/peugeot/308/1291560917A1KVVOPE308">x</a>'
        '<a href="/a/voiture-occasion/citroen/c3/1291268067A1KVVOCIC3">y</a>'
        '<a href="/a/voiture-occasion/peugeot/308/1291560917A1KVVOPE308">dup</a>'
        '<a href="/moto-scooter/yamaha/r1/XYZ">ignored — wrong rubric</a>'
    )
    assert ParuVenduFRScraper()._extract(html) == [
        "https://www.paruvendu.fr/a/voiture-occasion/peugeot/308/1291560917A1KVVOPE308",
        "https://www.paruvendu.fr/a/voiture-occasion/citroen/c3/1291268067A1KVVOCIC3",
    ]


@pytest.mark.unit
def test_paruvendu_extract_returns_empty_on_garbage() -> None:
    assert ParuVenduFRScraper()._extract("") == []
    assert ParuVenduFRScraper()._extract("<html><body>404</body></html>") == []


# --------------------------------------------------------------------------- #
# fetch_segment — behavioural matrix
# --------------------------------------------------------------------------- #
_PARUVENDU_HTML = (
    '<a href="/a/voiture-occasion/seat/leon/9999999A1KVVOSELEO">x</a>'
)
_PARUVENDU_EXPECTED = ["https://www.paruvendu.fr/a/voiture-occasion/seat/leon/9999999A1KVVOSELEO"]

_OK_CASES = [
    (ParuVenduFRScraper, dict(_YP), _PARUVENDU_HTML, _PARUVENDU_EXPECTED),
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
    session = _Session([_Resp(429), _Resp(503), _Resp(403)])
    assert _run(scraper.fetch_segment(session, params, 1)) == []
    assert len(session.calls) == scraper.RETRY_ATTEMPTS


@pytest.mark.unit
@pytest.mark.parametrize("cls, params, body, expected", _OK_CASES)
def test_fetch_segment_recovers_after_block(cls, params, body, expected) -> None:
    scraper = cls()
    _no_backoff(scraper)
    session = _Session([_Resp(503), _Resp(200, body)])
    assert _run(scraper.fetch_segment(session, params, 1)) == expected
    assert len(session.calls) == 2


@pytest.mark.unit
@pytest.mark.parametrize("cls, params, body, expected", _OK_CASES)
def test_fetch_segment_non_block_status_no_retry(cls, params, body, expected) -> None:
    scraper = cls()
    session = _Session([_Resp(404)])
    assert _run(scraper.fetch_segment(session, params, 1)) == []
    assert len(session.calls) == 1


@pytest.mark.unit
@pytest.mark.parametrize("cls, params, body, expected", _OK_CASES)
def test_fetch_segment_retries_transport_error(cls, params, body, expected) -> None:
    scraper = cls()
    _no_backoff(scraper)
    session = _Session([ConnectionError("reset"), ConnectionError("reset"), _Resp(200, body)])
    assert _run(scraper.fetch_segment(session, params, 1)) == expected
    assert len(session.calls) == 3


# --------------------------------------------------------------------------- #
# wiring — portal registry & domain→tier registry
# --------------------------------------------------------------------------- #
@pytest.mark.unit
@pytest.mark.parametrize(
    "domain, cls",
    [
        ("paruvendu.fr", ParuVenduFRScraper),
    ],
)
def test_registry_resolves_domain_to_scraper(domain, cls) -> None:
    scraper = get_scraper(domain)
    assert isinstance(scraper, cls)
    assert scraper.DOMAIN == domain


@pytest.mark.unit
@pytest.mark.parametrize(
    "domain, tier, waf, ceiling",
    [
        ("paruvendu.fr", Tier.T1, WAF.NONE, None),
    ],
)
def test_domain_map_baselines(domain, tier, waf, ceiling) -> None:
    spec = domain_get(domain)
    assert spec is not None, f"{domain} missing from REGISTRY"
    assert spec.tier is tier
    assert spec.waf is waf
    assert spec.can_escalate_to is ceiling
