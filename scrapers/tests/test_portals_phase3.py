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
from scrapers.portals.autotrack_nl import AutoTrackNLScraper
from scrapers.portals.base import BasePortalScraper
from scrapers.portals.gaspedaal_nl import GaspedaalNLScraper, _slugify
from scrapers.portals.largus_fr import LargusFRScraper
from scrapers.portals.motor_es import MotorESScraper
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

_PHASE3 = [ParuVenduFRScraper, LargusFRScraper, MotorESScraper]


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
# largus.fr — request shape & extraction
# --------------------------------------------------------------------------- #
@pytest.mark.unit
def test_largus_build_url_full_uses_cents_and_open_price() -> None:
    # price_min/price_max are CENTS (EUR ×100) — verified against the live counter.
    full = LargusFRScraper()._build_url(_YP, 3)
    assert full == (
        "https://occasion.largus.fr/auto/"
        "?price_min=1000000&price_max=2000000&year_min=2018&year_max=2020&currentpage=3"
    )
    open_top = LargusFRScraper()._build_url(_YP_OPEN, 1)
    assert "price_max" not in open_top
    assert open_top.startswith("https://occasion.largus.fr/auto/?price_min=10000000&")
    assert open_top.endswith("&year_min=2024&year_max=2026&currentpage=1")


@pytest.mark.unit
def test_largus_extract_only_uuid_paths_and_dedups() -> None:
    html = (
        '<a href="/auto/annonce-04279b1b-ce4d-4cc1-863f-d0bbd8c978a8-renault-clio-2018-130000km">x</a>'
        '<a href="/auto/annonce-1205e427-91f5-436e-8efa-c8a5cd2c9c67-volkswagen-golf-2024-25300km">y</a>'
        '<a href="/auto/annonce-04279b1b-ce4d-4cc1-863f-d0bbd8c978a8-renault-clio-2018-130000km">dup</a>'
        '<a href="/auto/annonce-NOTUUID-foo-bar">ignored — non-UUID id</a>'
        '<a href="/auto/audi/a3/">ignored — make/model nav</a>'
    )
    assert LargusFRScraper()._extract(html) == [
        "https://occasion.largus.fr/auto/annonce-04279b1b-ce4d-4cc1-863f-d0bbd8c978a8-renault-clio-2018-130000km",
        "https://occasion.largus.fr/auto/annonce-1205e427-91f5-436e-8efa-c8a5cd2c9c67-volkswagen-golf-2024-25300km",
    ]


@pytest.mark.unit
def test_largus_extract_returns_empty_on_garbage() -> None:
    assert LargusFRScraper()._extract("") == []
    assert LargusFRScraper()._extract("<html><body>404</body></html>") == []


# --------------------------------------------------------------------------- #
# autotrack.nl — single-segment scraper (global pager covers full inventory)
# --------------------------------------------------------------------------- #
@pytest.mark.unit
def test_autotrack_partition_is_single_empty_segment() -> None:
    # autotrack's pager reaches the whole 220k inventory; no partition is needed.
    assert AutoTrackNLScraper().partition_params() == [{}]


@pytest.mark.unit
def test_autotrack_subdivide_is_a_noop() -> None:
    # No subdivision should be attempted — the base scraper never has to escalate.
    assert AutoTrackNLScraper().subdivide_segment({}) == []


@pytest.mark.unit
def test_autotrack_build_url_passes_only_pagenumber() -> None:
    assert AutoTrackNLScraper()._build_url(1) == (
        "https://www.autotrack.nl/aanbod?pageNumber=1"
    )
    assert AutoTrackNLScraper()._build_url(7336) == (
        "https://www.autotrack.nl/aanbod?pageNumber=7336"
    )


@pytest.mark.unit
def test_autotrack_extract_strips_tracking_query_and_dedups() -> None:
    html = (
        '<a data-vehicle-id="59439031" href="/a/seat-leon-benzine-2020-59439031?from_srp=true">x</a>'
        '<a data-vehicle-id="59436164" href="/a/peugeot-5008-benzine-2018-59436164?from_srp=true">y</a>'
        '<a href="/a/seat-leon-benzine-2020-59439031?from_srp=true">dup</a>'
        '<a href="/a/missing-tracking">ignored — no ?from_srp=true</a>'
    )
    assert AutoTrackNLScraper()._extract(html) == [
        "https://www.autotrack.nl/a/seat-leon-benzine-2020-59439031",
        "https://www.autotrack.nl/a/peugeot-5008-benzine-2018-59436164",
    ]


@pytest.mark.unit
def test_autotrack_extract_returns_empty_on_garbage() -> None:
    assert AutoTrackNLScraper()._extract("") == []
    assert AutoTrackNLScraper()._extract("<html><body>404</body></html>") == []


# --------------------------------------------------------------------------- #
# gaspedaal.nl — JSON-LD ItemList extraction + slugification
# --------------------------------------------------------------------------- #
@pytest.mark.unit
@pytest.mark.parametrize(
    "raw, expected",
    [
        ("Renault", "renault"),
        ("Mercedes-Benz", "mercedes-benz"),
        ("Citroën", "citroen"),         # accent fold — verified vs live 404
        ("DS 4", "ds-4"),
        ("BMW", "bmw"),
        ("3 Serie", "3-serie"),
    ],
)
def test_gaspedaal_slugify(raw, expected) -> None:
    assert _slugify(raw) == expected


@pytest.mark.unit
def test_gaspedaal_partition_is_single_empty_segment() -> None:
    # The global SSR pager covers the whole 338k inventory; no partition needed.
    assert GaspedaalNLScraper().partition_params() == [{}]


@pytest.mark.unit
def test_gaspedaal_subdivide_is_a_noop() -> None:
    assert GaspedaalNLScraper().subdivide_segment({}) == []


@pytest.mark.unit
def test_gaspedaal_build_url_passes_only_page() -> None:
    assert GaspedaalNLScraper()._build_url(1) == "https://www.gaspedaal.nl/zoeken?page=1"
    assert GaspedaalNLScraper()._build_url(3389) == "https://www.gaspedaal.nl/zoeken?page=3389"


_GASPEDAAL_LDJSON_HTML = """
<html><head>
<script type="application/ld+json">{"@context":"https://schema.org","@type":"ItemList","numberOfItems":2,"itemListElement":[
{"@type":"ListItem","position":1,"item":{"@type":["Car","Product"],"@id":"https://www.gaspedaal.nl/zoeken#136923530","brand":"Renault","model":"Captur"}},
{"@type":"ListItem","position":2,"item":{"@type":["Car","Product"],"@id":"https://www.gaspedaal.nl/zoeken?page=2#122829592","brand":"DS","model":"DS 4"}}
]}</script>
<script type="application/ld+json">{"@type":"BreadcrumbList","itemListElement":[{"@type":"ListItem","position":1,"item":{"@id":"/","name":"Home"}}]}</script>
</head></html>
"""


@pytest.mark.unit
def test_gaspedaal_extract_parses_json_ld_and_handles_page_echo() -> None:
    # The page-2 @id format ".../zoeken?page=2#<ID>" must match exactly the same
    # ID-extraction path as the page-1 ".../zoeken#<ID>" form.
    assert GaspedaalNLScraper()._extract(_GASPEDAAL_LDJSON_HTML) == [
        "https://www.gaspedaal.nl/auto/renault/captur/136923530",
        "https://www.gaspedaal.nl/auto/ds/ds-4/122829592",
    ]


@pytest.mark.unit
def test_gaspedaal_extract_skips_items_missing_brand_or_model() -> None:
    html = (
        '<script type="application/ld+json">'
        '{"@type":"ItemList","itemListElement":['
        '{"@type":"ListItem","position":1,"item":{"@id":"https://www.gaspedaal.nl/zoeken#1","brand":"Audi"}},'  # no model
        '{"@type":"ListItem","position":2,"item":{"@id":"https://www.gaspedaal.nl/zoeken#2","model":"A4"}},'    # no brand
        '{"@type":"ListItem","position":3,"item":{"@id":"https://www.gaspedaal.nl/zoeken#3","brand":"BMW","model":"X1"}}'  # ok
        ']}</script>'
    )
    assert GaspedaalNLScraper()._extract(html) == [
        "https://www.gaspedaal.nl/auto/bmw/x1/3",
    ]


@pytest.mark.unit
def test_gaspedaal_extract_returns_empty_on_garbage() -> None:
    assert GaspedaalNLScraper()._extract("") == []
    # Valid JSON but missing the expected ItemList type.
    assert GaspedaalNLScraper()._extract(
        '<script type="application/ld+json">{"@type":"Organization"}</script>'
    ) == []
    # Broken JSON body — must not raise.
    assert GaspedaalNLScraper()._extract(
        '<script type="application/ld+json">not even json</script>'
    ) == []


# --------------------------------------------------------------------------- #
# motor.es — base64 data-goto + cars-only filter
# --------------------------------------------------------------------------- #
import base64 as _b64


def _b64encode_url(url: str) -> str:
    return _b64.b64encode(url.encode()).decode()


@pytest.mark.unit
def test_motor_build_url_full_and_open_price() -> None:
    full = MotorESScraper()._build_url(_YP, 3)
    assert full == (
        "https://www.motor.es/segunda-mano/coches/"
        "?pagina=3&precio_min=10000&precio_max=20000&year_min=2018&year_max=2020"
    )
    open_top = MotorESScraper()._build_url(_YP_OPEN, 1)
    assert "precio_max" not in open_top
    assert open_top.endswith("&precio_min=100000&year_min=2024&year_max=2026")
    assert "?pagina=1&" in open_top  # pagina is first param, no leading &


@pytest.mark.unit
def test_motor_extract_decodes_data_goto_keeps_cars_only_and_dedups() -> None:
    car1 = _b64encode_url("https://www.motor.es/segunda-mano/anuncio/12345/")
    car2 = _b64encode_url("https://www.motor.es/segunda-mano/anuncio/67890/")
    moto = _b64encode_url(
        "https://www.motor.es/motos/segunda-mano/anuncio/e08d153d-e509-42ef-a813-0ce9e49474d4/"
    )
    html = (
        f'<span data-goto="{car1}">x</span>'
        f'<span data-goto="{car2}">y</span>'
        f'<span data-goto="{car1}">dup</span>'
        f'<span data-goto="{moto}">moto — filtered</span>'
        '<span data-goto="!!!notbase64!!!">garbage — filtered</span>'
    )
    assert MotorESScraper()._extract(html) == [
        "https://www.motor.es/segunda-mano/anuncio/12345/",
        "https://www.motor.es/segunda-mano/anuncio/67890/",
    ]


@pytest.mark.unit
def test_motor_extract_returns_empty_on_garbage() -> None:
    assert MotorESScraper()._extract("") == []
    assert MotorESScraper()._extract("<html><body>no cards</body></html>") == []


# --------------------------------------------------------------------------- #
# fetch_segment — behavioural matrix
# --------------------------------------------------------------------------- #
_PARUVENDU_HTML = (
    '<a href="/a/voiture-occasion/seat/leon/9999999A1KVVOSELEO">x</a>'
)
_PARUVENDU_EXPECTED = ["https://www.paruvendu.fr/a/voiture-occasion/seat/leon/9999999A1KVVOSELEO"]

_LARGUS_HTML = (
    '<a href="/auto/annonce-04279b1b-ce4d-4cc1-863f-d0bbd8c978a8-renault-clio-2018-130000km">x</a>'
)
_LARGUS_EXPECTED = [
    "https://occasion.largus.fr/auto/annonce-04279b1b-ce4d-4cc1-863f-d0bbd8c978a8-renault-clio-2018-130000km"
]

_AUTOTRACK_HTML = (
    '<a data-vehicle-id="59439031" href="/a/seat-leon-benzine-2020-59439031?from_srp=true">x</a>'
)
_AUTOTRACK_EXPECTED = ["https://www.autotrack.nl/a/seat-leon-benzine-2020-59439031"]

_GASPEDAAL_OK_HTML = (
    '<script type="application/ld+json">'
    '{"@type":"ItemList","itemListElement":['
    '{"@type":"ListItem","position":1,"item":{"@id":"https://www.gaspedaal.nl/zoeken#777","brand":"Audi","model":"A4"}}'
    ']}</script>'
)
_GASPEDAAL_EXPECTED = ["https://www.gaspedaal.nl/auto/audi/a4/777"]

_MOTOR_OK_HTML = (
    f'<span data-goto="{_b64encode_url("https://www.motor.es/segunda-mano/anuncio/777/")}">x</span>'
)
_MOTOR_EXPECTED = ["https://www.motor.es/segunda-mano/anuncio/777/"]

_OK_CASES = [
    (ParuVenduFRScraper, dict(_YP), _PARUVENDU_HTML, _PARUVENDU_EXPECTED),
    (LargusFRScraper, dict(_YP), _LARGUS_HTML, _LARGUS_EXPECTED),
    (AutoTrackNLScraper, {}, _AUTOTRACK_HTML, _AUTOTRACK_EXPECTED),
    (GaspedaalNLScraper, {}, _GASPEDAAL_OK_HTML, _GASPEDAAL_EXPECTED),
    (MotorESScraper, dict(_YP), _MOTOR_OK_HTML, _MOTOR_EXPECTED),
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
        ("largus.fr", LargusFRScraper),
        ("autotrack.nl", AutoTrackNLScraper),
        ("gaspedaal.nl", GaspedaalNLScraper),
        ("motor.es", MotorESScraper),
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
        ("largus.fr", Tier.T1, WAF.NONE, None),
        ("autotrack.nl", Tier.T1, WAF.NONE, None),
        ("gaspedaal.nl", Tier.T1, WAF.NONE, None),
        ("motor.es", Tier.T1, WAF.NONE, None),
    ],
)
def test_domain_map_baselines(domain, tier, waf, ceiling) -> None:
    spec = domain_get(domain)
    assert spec is not None, f"{domain} missing from REGISTRY"
    assert spec.tier is tier
    assert spec.waf is waf
    assert spec.can_escalate_to is ceiling
