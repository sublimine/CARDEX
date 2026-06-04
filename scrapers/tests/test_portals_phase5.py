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


# =========================================================================== #
# viabovag.nl -- Next.js data route SSR scraper
# =========================================================================== #
from scrapers.portals.viabovag_nl import ViaBovagNLScraper, _BUILD_ID_RE

# HTML stub con __NEXT_DATA__ conteniendo buildId
_VIABOVAG_HTML = (
    '<html><head><script id="__NEXT_DATA__" type="application/json">'
    '{"props":{"pageProps":{}},"page":"/srp","query":{"mobilityType":"auto"},'
    '"buildId":"testBuildId123","isFallback":false}'
    '</script></head></html>'
)

# JSON stub de la data route con resultados
_VIABOVAG_DATA_JSON = _json.dumps({
    "pageProps": {
        "serverSearchResults": {
            "results": [
                {
                    "id": "aaa-111",
                    "url": "https://www.viabovag.nl/auto/aanbod/renault-clio-abc123",
                    "friendlyUriPart": "renault-clio-abc123",
                    "price": 21895,
                    "vehicle": {"brand": "Renault", "model": "Clio", "year": 2024}
                },
                {
                    "id": "bbb-222",
                    "url": "https://www.viabovag.nl/auto/aanbod/bmw-3-serie-def456",
                    "friendlyUriPart": "bmw-3-serie-def456",
                    "price": 35990,
                    "vehicle": {"brand": "BMW", "model": "3 Serie", "year": 2022}
                },
                {
                    "id": "aaa-111",
                    "url": "https://www.viabovag.nl/auto/aanbod/renault-clio-abc123",
                    "friendlyUriPart": "renault-clio-abc123",
                    "price": 21895,
                    "vehicle": {"brand": "Renault", "model": "Clio", "year": 2024}
                },
            ],
            "count": 129069
        }
    }
})

_VIABOVAG_EXPECTED = [
    "https://www.viabovag.nl/auto/aanbod/renault-clio-abc123",
    "https://www.viabovag.nl/auto/aanbod/bmw-3-serie-def456",
]


@pytest.mark.unit
def test_viabovag_build_id_regex() -> None:
    match = _BUILD_ID_RE.search(_VIABOVAG_HTML)
    assert match is not None
    assert match.group(1) == "testBuildId123"


@pytest.mark.unit
def test_viabovag_partition_is_single_empty_segment() -> None:
    assert ViaBovagNLScraper().partition_params() == [{}]


@pytest.mark.unit
def test_viabovag_subdivide_is_a_noop() -> None:
    assert ViaBovagNLScraper().subdivide_segment({}) == []


@pytest.mark.unit
def test_viabovag_build_data_url() -> None:
    scraper = ViaBovagNLScraper()
    scraper._build_id = "testBuildId123"
    assert scraper._build_data_url(1) == (
        "https://www.viabovag.nl/_next/data/testBuildId123/srp.json"
        "?mobilityType=auto&selectedFilters=pagina-1"
    )
    assert scraper._build_data_url(4167) == (
        "https://www.viabovag.nl/_next/data/testBuildId123/srp.json"
        "?mobilityType=auto&selectedFilters=pagina-4167"
    )


@pytest.mark.unit
def test_viabovag_extract_pulls_urls_and_dedups() -> None:
    assert ViaBovagNLScraper()._extract(_VIABOVAG_DATA_JSON) == _VIABOVAG_EXPECTED


@pytest.mark.unit
def test_viabovag_extract_returns_empty_on_garbage() -> None:
    assert ViaBovagNLScraper()._extract("") == []
    assert ViaBovagNLScraper()._extract("not json") == []
    assert ViaBovagNLScraper()._extract('{"pageProps": {}}') == []
    assert ViaBovagNLScraper()._extract('{"pageProps": {"serverSearchResults": "x"}}') == []


@pytest.mark.unit
def test_viabovag_extract_skips_items_without_url() -> None:
    body = _json.dumps({
        "pageProps": {
            "serverSearchResults": {
                "results": [
                    {"id": "a", "price": 100},
                    {"id": "b", "url": "", "price": 200},
                    {"id": "c", "url": "https://www.viabovag.nl/auto/aanbod/ok-item", "price": 300},
                ],
                "count": 3
            }
        }
    })
    assert ViaBovagNLScraper()._extract(body) == [
        "https://www.viabovag.nl/auto/aanbod/ok-item",
    ]


# -- fetch_segment: buildId resolution + data fetch --------------------------
@pytest.mark.unit
def test_viabovag_fetch_segment_resolves_build_id_then_fetches() -> None:
    """Primera llamada resuelve buildId via HTML, luego fetch data route."""
    scraper = ViaBovagNLScraper()
    _no_backoff(scraper)
    session = _Session([
        _Resp(200, _VIABOVAG_HTML),        # buildId resolution (HTML)
        _Resp(200, _VIABOVAG_DATA_JSON),   # data route fetch
    ])
    urls = _run(scraper.fetch_segment(session, {}, 1))
    assert urls == _VIABOVAG_EXPECTED
    assert len(session.calls) == 2
    # Primera call debe ser al HTML /auto
    assert "/auto" in session.urls[0]
    assert "/_next/data/" not in session.urls[0]
    # Segunda call debe ser a la data route
    assert "/_next/data/testBuildId123/srp.json" in session.urls[1]


@pytest.mark.unit
def test_viabovag_fetch_segment_caches_build_id() -> None:
    """Segunda llamada reutiliza el buildId cacheado."""
    scraper = ViaBovagNLScraper()
    _no_backoff(scraper)
    session = _Session([
        _Resp(200, _VIABOVAG_HTML),        # buildId resolution
        _Resp(200, _VIABOVAG_DATA_JSON),   # page 1
        _Resp(200, _VIABOVAG_DATA_JSON),   # page 2 (no HTML fetch)
    ])
    _run(scraper.fetch_segment(session, {}, 1))
    urls2 = _run(scraper.fetch_segment(session, {}, 2))
    assert urls2 == _VIABOVAG_EXPECTED
    assert len(session.calls) == 3
    # Tercera call debe ir directa a data route sin HTML
    assert "/_next/data/" in session.urls[2]


@pytest.mark.unit
def test_viabovag_fetch_segment_retries_block_then_gives_up() -> None:
    scraper = ViaBovagNLScraper()
    scraper._build_id = "cached"
    _no_backoff(scraper)
    session = _Session([_Resp(429), _Resp(503), _Resp(403)])
    assert _run(scraper.fetch_segment(session, {}, 1)) == []
    assert len(session.calls) == scraper.RETRY_ATTEMPTS


@pytest.mark.unit
def test_viabovag_fetch_segment_recovers_after_block() -> None:
    scraper = ViaBovagNLScraper()
    scraper._build_id = "cached"
    _no_backoff(scraper)
    session = _Session([_Resp(503), _Resp(200, _VIABOVAG_DATA_JSON)])
    assert _run(scraper.fetch_segment(session, {}, 1)) == _VIABOVAG_EXPECTED
    assert len(session.calls) == 2


@pytest.mark.unit
def test_viabovag_fetch_segment_404_re_resolves_build_id() -> None:
    """404 en la data route => re-resolver buildId (nuevo deploy)."""
    scraper = ViaBovagNLScraper()
    scraper._build_id = "stale"
    _no_backoff(scraper)
    session = _Session([
        _Resp(404),                        # stale buildId
        _Resp(200, _VIABOVAG_HTML),        # re-resolve
        _Resp(200, _VIABOVAG_DATA_JSON),   # retry con nuevo buildId
    ])
    urls = _run(scraper.fetch_segment(session, {}, 1))
    assert urls == _VIABOVAG_EXPECTED
    assert scraper._build_id == "testBuildId123"


@pytest.mark.unit
def test_viabovag_fetch_segment_transport_error_retries() -> None:
    scraper = ViaBovagNLScraper()
    scraper._build_id = "cached"
    _no_backoff(scraper)
    session = _Session([ConnectionError("reset"), _Resp(200, _VIABOVAG_DATA_JSON)])
    assert _run(scraper.fetch_segment(session, {}, 1)) == _VIABOVAG_EXPECTED
    assert len(session.calls) == 2


# -- wiring -------------------------------------------------------------------
@pytest.mark.unit
def test_viabovag_registry_resolves() -> None:
    scraper = get_scraper("viabovag.nl")
    assert isinstance(scraper, ViaBovagNLScraper)
    assert scraper.DOMAIN == "viabovag.nl"


@pytest.mark.unit
def test_viabovag_domain_map_baseline() -> None:
    spec = domain_get("viabovag.nl")
    assert spec is not None, "viabovag.nl missing from REGISTRY"
    assert spec.tier is Tier.T1
    assert spec.waf is WAF.NONE
    assert spec.can_escalate_to is None


# =========================================================================== #
# tutti.ch — Next.js data route + msgpack tokens (T1)
# =========================================================================== #
from scrapers.portals.tutti_ch import (
    TuttiCHScraper,
    _BUILD_ID_RE as _TUTTI_BUILD_ID_RE,
    _encode_token,
    _mp_pack,
    _BRANDS as _TUTTI_BRANDS,
    _PRICE_BANDS as _TUTTI_PRICE_BANDS,
)

# HTML stub con __NEXT_DATA__ conteniendo buildId
_TUTTI_HTML = (
    '<html><head><script id="__NEXT_DATA__" type="application/json">'
    '{"props":{"pageProps":{}},"page":"/search",'
    '"buildId":"tuttiBuild42","isFallback":false}'
    '</script></head></html>'
)

# JSON stub de la data route
_TUTTI_DATA_JSON = _json.dumps({
    "pageProps": {
        "dehydratedState": {
            "queries": [{
                "state": {
                    "data": {
                        "listings": {
                            "edges": [
                                {"node": {"listingID": "12345", "seoInformation": {"deSlug": "bmw-320i"}}},
                                {"node": {"listingID": "67890", "seoInformation": {"deSlug": "audi-a3"}}},
                                {"node": {"listingID": "12345", "seoInformation": {"deSlug": "bmw-320i"}}},  # dup
                            ]
                        }
                    }
                }
            }]
        }
    }
})

_TUTTI_EXPECTED = [
    "https://www.tutti.ch/de/vi/12345/bmw-320i",
    "https://www.tutti.ch/de/vi/67890/audi-a3",
]


# -- _mp_pack ------------------------------------------------------------------
@pytest.mark.unit
def test_tutti_mp_pack_basic_types() -> None:
    """Inline msgpack packer produce bytes validos para el subset soportado."""
    assert _mp_pack(None) == b"\xc0"
    assert _mp_pack(True) == b"\xc3"
    assert _mp_pack(False) == b"\xc2"
    # fixint (0..127)
    assert _mp_pack(0) == b"\x00"
    assert _mp_pack(127) == b"\x7f"
    # uint8 (128..255)
    assert _mp_pack(200) == b"\xcc\xc8"
    # uint16
    assert _mp_pack(5000) == b"\xcd\x13\x88"
    # uint32
    assert _mp_pack(100_000) == b"\xce\x00\x01\x86\xa0"
    # negative fixint (-32..-1)
    assert _mp_pack(-1) == b"\xff"
    assert _mp_pack(-32) == b"\xe0"
    # fixstr
    assert _mp_pack("abc") == b"\xa3abc"
    # fixarray
    packed_list = _mp_pack([1, 2])
    assert packed_list == b"\x92\x01\x02"
    # nested
    assert _mp_pack([None, "x"]) == b"\x92\xc0\xa1x"


@pytest.mark.unit
def test_tutti_mp_pack_rejects_unsupported() -> None:
    """Tipos no soportados lanzan TypeError/ValueError."""
    import pytest as _pt
    _pt.raises(TypeError, lambda: _mp_pack(3.14))
    _pt.raises(TypeError, lambda: _mp_pack({}))
    _pt.raises(ValueError, lambda: _mp_pack(2**33))


# -- _encode_token -------------------------------------------------------------
@pytest.mark.unit
def test_tutti_encode_token_base() -> None:
    """Token sin filtros empieza con 'A' y es determinista."""
    tok = _encode_token("cars")
    assert tok.startswith("A")
    assert len(tok) > 10
    # Decodificar para verificar estructura
    import base64
    raw = tok[1:]
    raw += "=" * (-len(raw) % 4)
    data = base64.urlsafe_b64decode(raw)
    assert data  # non-empty bytes


@pytest.mark.unit
def test_tutti_encode_token_brand() -> None:
    """Token con marca incluye el slug de marca."""
    tok = _encode_token("cars", brand="bmw")
    assert tok.startswith("A")
    # Distinto al base token
    assert tok != _encode_token("cars")


@pytest.mark.unit
def test_tutti_encode_token_brand_plus_price() -> None:
    """Token combinando marca + rango de precio produce token valido y distinto."""
    tok = _encode_token("cars", brand="vw", price_min=10000, price_max=30000)
    tok_brand_only = _encode_token("cars", brand="vw")
    assert tok.startswith("A")
    assert tok != tok_brand_only


@pytest.mark.unit
def test_tutti_encode_token_price_only() -> None:
    """Token con solo rango de precio (sin marca)."""
    tok = _encode_token("cars", price_min=None, price_max=5000)
    assert tok.startswith("A")
    assert tok != _encode_token("cars")


@pytest.mark.unit
def test_tutti_encode_token_deterministic() -> None:
    """Mismos parametros producen el mismo token."""
    a = _encode_token("cars", brand="audi", price_min=5000, price_max=10000)
    b = _encode_token("cars", brand="audi", price_min=5000, price_max=10000)
    assert a == b


# -- partition / subdivide -----------------------------------------------------
@pytest.mark.unit
def test_tutti_partition_shape() -> None:
    scraper = TuttiCHScraper()
    segments = scraper.partition_params()
    assert len(segments) == len(_TUTTI_BRANDS)
    brands = [s["brand"] for s in segments]
    assert brands == list(_TUTTI_BRANDS)
    assert all("_fine" not in s for s in segments)


@pytest.mark.unit
def test_tutti_subdivide_creates_price_bands() -> None:
    scraper = TuttiCHScraper()
    subs = scraper.subdivide_segment({"brand": "bmw"})
    assert len(subs) == len(_TUTTI_PRICE_BANDS)
    for s in subs:
        assert s["brand"] == "bmw"
        assert s["_fine"] is True
        assert "price_min" in s
        assert "price_max" in s


@pytest.mark.unit
def test_tutti_subdivide_stops_on_fine() -> None:
    """Segmentos ya subdivididos (_fine=True) retornan lista vacia."""
    scraper = TuttiCHScraper()
    assert scraper.subdivide_segment({"brand": "bmw", "_fine": True}) == []


# -- _build_data_url -----------------------------------------------------------
@pytest.mark.unit
def test_tutti_build_data_url_page1_no_param() -> None:
    scraper = TuttiCHScraper()
    scraper._build_id = "tuttiBuild42"
    token = "ATestToken123"
    url = scraper._build_data_url(token, 1)
    assert url == "https://www.tutti.ch/_next/data/tuttiBuild42/de/q/autos/ATestToken123.json"
    assert "?page=" not in url


@pytest.mark.unit
def test_tutti_build_data_url_page_gt1() -> None:
    scraper = TuttiCHScraper()
    scraper._build_id = "tuttiBuild42"
    token = "ATestToken123"
    url = scraper._build_data_url(token, 5)
    assert url == "https://www.tutti.ch/_next/data/tuttiBuild42/de/q/autos/ATestToken123.json?page=5"


# -- _extract ------------------------------------------------------------------
@pytest.mark.unit
def test_tutti_extract_pulls_urls_and_dedups() -> None:
    assert TuttiCHScraper()._extract(_TUTTI_DATA_JSON) == _TUTTI_EXPECTED


@pytest.mark.unit
def test_tutti_extract_handles_missing_slug() -> None:
    """Nodo sin deSlug produce URL sin slug final."""
    body = _json.dumps({
        "pageProps": {"dehydratedState": {"queries": [{"state": {"data": {
            "listings": {"edges": [
                {"node": {"listingID": "999", "seoInformation": {}}},
            ]}
        }}}]}}
    })
    assert TuttiCHScraper()._extract(body) == ["https://www.tutti.ch/de/vi/999"]


@pytest.mark.unit
def test_tutti_extract_returns_empty_on_garbage() -> None:
    assert TuttiCHScraper()._extract("") == []
    assert TuttiCHScraper()._extract("not json") == []
    assert TuttiCHScraper()._extract('{"pageProps": {}}') == []
    assert TuttiCHScraper()._extract('{"pageProps": {"dehydratedState": "bad"}}') == []


@pytest.mark.unit
def test_tutti_extract_skips_missing_listingID() -> None:
    body = _json.dumps({
        "pageProps": {"dehydratedState": {"queries": [{"state": {"data": {
            "listings": {"edges": [
                {"node": {"seoInformation": {"deSlug": "orphan"}}},
                {"node": {"listingID": "ok1", "seoInformation": {"deSlug": "valid"}}},
            ]}
        }}}]}}
    })
    assert TuttiCHScraper()._extract(body) == ["https://www.tutti.ch/de/vi/ok1/valid"]


# -- fetch_segment behavioural matrix ------------------------------------------
@pytest.mark.unit
def test_tutti_fetch_segment_resolves_build_id_then_fetches() -> None:
    """Primera llamada resuelve buildId via HTML, luego fetch data route."""
    scraper = TuttiCHScraper()
    _no_backoff(scraper)
    session = _Session([
        _Resp(200, _TUTTI_HTML),        # buildId resolution (/de)
        _Resp(200, _TUTTI_DATA_JSON),   # data route fetch
    ])
    urls = _run(scraper.fetch_segment(session, {"brand": "bmw"}, 1))
    assert urls == _TUTTI_EXPECTED
    assert len(session.calls) == 2
    # Primera call al HTML /de
    assert "/de" in session.urls[0]
    assert "/_next/data/" not in session.urls[0]
    # Segunda call a la data route
    assert "/_next/data/tuttiBuild42/" in session.urls[1]


@pytest.mark.unit
def test_tutti_fetch_segment_caches_build_id() -> None:
    """Segunda llamada reutiliza el buildId cacheado — sin fetch HTML."""
    scraper = TuttiCHScraper()
    _no_backoff(scraper)
    session = _Session([
        _Resp(200, _TUTTI_HTML),        # buildId resolution
        _Resp(200, _TUTTI_DATA_JSON),   # page 1
        _Resp(200, _TUTTI_DATA_JSON),   # page 2 (no HTML)
    ])
    _run(scraper.fetch_segment(session, {"brand": "bmw"}, 1))
    urls2 = _run(scraper.fetch_segment(session, {"brand": "bmw"}, 2))
    assert urls2 == _TUTTI_EXPECTED
    assert len(session.calls) == 3
    # Tercera call va directa a data route
    assert "/_next/data/" in session.urls[2]


@pytest.mark.unit
def test_tutti_fetch_segment_retries_block_then_gives_up() -> None:
    scraper = TuttiCHScraper()
    scraper._build_id = "cached"
    _no_backoff(scraper)
    session = _Session([_Resp(429), _Resp(503), _Resp(403)])
    assert _run(scraper.fetch_segment(session, {"brand": "bmw"}, 1)) == []
    assert len(session.calls) == scraper.RETRY_ATTEMPTS


@pytest.mark.unit
def test_tutti_fetch_segment_recovers_after_block() -> None:
    scraper = TuttiCHScraper()
    scraper._build_id = "cached"
    _no_backoff(scraper)
    session = _Session([_Resp(503), _Resp(200, _TUTTI_DATA_JSON)])
    assert _run(scraper.fetch_segment(session, {"brand": "bmw"}, 1)) == _TUTTI_EXPECTED
    assert len(session.calls) == 2


@pytest.mark.unit
def test_tutti_fetch_segment_404_re_resolves_build_id() -> None:
    """404 en data route => re-resolver buildId (nuevo deploy mid-scrape)."""
    scraper = TuttiCHScraper()
    scraper._build_id = "stale"
    _no_backoff(scraper)
    session = _Session([
        _Resp(404),                     # stale buildId
        _Resp(200, _TUTTI_HTML),        # re-resolve
        _Resp(200, _TUTTI_DATA_JSON),   # retry con tuttiBuild42
    ])
    urls = _run(scraper.fetch_segment(session, {"brand": "bmw"}, 1))
    assert urls == _TUTTI_EXPECTED
    assert scraper._build_id == "tuttiBuild42"


@pytest.mark.unit
def test_tutti_fetch_segment_transport_error_retries() -> None:
    scraper = TuttiCHScraper()
    scraper._build_id = "cached"
    _no_backoff(scraper)
    session = _Session([ConnectionError("reset"), _Resp(200, _TUTTI_DATA_JSON)])
    assert _run(scraper.fetch_segment(session, {"brand": "bmw"}, 1)) == _TUTTI_EXPECTED
    assert len(session.calls) == 2


@pytest.mark.unit
def test_tutti_fetch_segment_non_retryable_status() -> None:
    """Status no retryable (e.g. 301) retorna vacio sin reintentos."""
    scraper = TuttiCHScraper()
    scraper._build_id = "cached"
    session = _Session([_Resp(301)])
    assert _run(scraper.fetch_segment(session, {"brand": "bmw"}, 1)) == []
    assert len(session.calls) == 1


# -- wiring --------------------------------------------------------------------
@pytest.mark.unit
def test_tutti_registry_resolves() -> None:
    scraper = get_scraper("tutti.ch")
    assert isinstance(scraper, TuttiCHScraper)
    assert scraper.DOMAIN == "tutti.ch"


@pytest.mark.unit
def test_tutti_domain_map_baseline() -> None:
    spec = domain_get("tutti.ch")
    assert spec is not None, "tutti.ch missing from REGISTRY"
    assert spec.tier is Tier.T1
    assert spec.waf is WAF.CF_FREE
    assert "CH" in spec.countries


# =========================================================================== #
# anibis.ch — Clon francés de tutti.ch (mismo backend Scout24, T1)
# =========================================================================== #
from scrapers.portals.anibis_ch import AnibisCHScraper

# HTML stub con __NEXT_DATA__ conteniendo buildId
_ANIBIS_HTML = (
    '<html><head><script id="__NEXT_DATA__" type="application/json">'
    '{"props":{"pageProps":{}},"page":"/[lang]/q/[[...slug]]",'
    '"buildId":"anibisBuild99","isFallback":false}'
    '</script></head></html>'
)

# JSON stub — misma estructura que tutti.ch, con frSlug
_ANIBIS_DATA_JSON = _json.dumps({
    "pageProps": {
        "dehydratedState": {
            "queries": [{
                "state": {
                    "data": {
                        "listings": {
                            "edges": [
                                {"node": {"listingID": "A001", "seoInformation": {"deSlug": "bmw-320i-de", "frSlug": "berne/vehicules/voitures/bmw-320i", "itSlug": "bmw-320i-it"}}},
                                {"node": {"listingID": "A002", "seoInformation": {"deSlug": "audi-a3-de", "frSlug": "zurich/vehicules/voitures/audi-a3", "itSlug": "audi-a3-it"}}},
                                {"node": {"listingID": "A001", "seoInformation": {"deSlug": "bmw-320i-de", "frSlug": "berne/vehicules/voitures/bmw-320i", "itSlug": "bmw-320i-it"}}},  # dup
                            ]
                        }
                    }
                }
            }]
        }
    }
})

_ANIBIS_EXPECTED = [
    "https://www.anibis.ch/fr/vi/A001/berne/vehicules/voitures/bmw-320i",
    "https://www.anibis.ch/fr/vi/A002/zurich/vehicules/voitures/audi-a3",
]


@pytest.mark.unit
def test_anibis_inherits_brands_and_price_bands() -> None:
    """AnibisCHScraper hereda marcas y bandas de precio de TuttiCHScraper."""
    scraper = AnibisCHScraper()
    assert scraper.BRANDS == TuttiCHScraper.BRANDS
    assert scraper.PRICE_BANDS == TuttiCHScraper.PRICE_BANDS
    assert scraper.PAGE_SIZE == 30
    assert scraper.MAX_PAGES == 101


@pytest.mark.unit
def test_anibis_locale_constants() -> None:
    scraper = AnibisCHScraper()
    assert scraper.DOMAIN == "anibis.ch"
    assert scraper.HOST == "www.anibis.ch"
    assert scraper.LANG == "fr"
    assert scraper.CATEGORY_SLUG == "voitures"
    assert scraper.SLUG_KEY == "frSlug"


@pytest.mark.unit
def test_anibis_partition_shape() -> None:
    scraper = AnibisCHScraper()
    segments = scraper.partition_params()
    assert len(segments) == len(scraper.BRANDS)
    brands = [s["brand"] for s in segments]
    assert brands == list(scraper.BRANDS)


@pytest.mark.unit
def test_anibis_subdivide_creates_price_bands() -> None:
    scraper = AnibisCHScraper()
    subs = scraper.subdivide_segment({"brand": "audi"})
    assert len(subs) == len(scraper.PRICE_BANDS)
    for s in subs:
        assert s["brand"] == "audi"
        assert s["_fine"] is True


@pytest.mark.unit
def test_anibis_subdivide_stops_on_fine() -> None:
    assert AnibisCHScraper().subdivide_segment({"brand": "audi", "_fine": True}) == []


@pytest.mark.unit
def test_anibis_build_data_url_uses_french_path() -> None:
    scraper = AnibisCHScraper()
    scraper._build_id = "anibisBuild99"
    token = "ATestToken456"
    url1 = scraper._build_data_url(token, 1)
    assert url1 == "https://www.anibis.ch/_next/data/anibisBuild99/fr/q/voitures/ATestToken456.json"
    url5 = scraper._build_data_url(token, 5)
    assert url5 == "https://www.anibis.ch/_next/data/anibisBuild99/fr/q/voitures/ATestToken456.json?page=5"


@pytest.mark.unit
def test_anibis_extract_uses_frSlug() -> None:
    """_extract usa frSlug para construir URLs de detalle."""
    assert AnibisCHScraper()._extract(_ANIBIS_DATA_JSON) == _ANIBIS_EXPECTED


@pytest.mark.unit
def test_anibis_extract_handles_missing_frSlug() -> None:
    body = _json.dumps({
        "pageProps": {"dehydratedState": {"queries": [{"state": {"data": {
            "listings": {"edges": [
                {"node": {"listingID": "X99", "seoInformation": {"deSlug": "only-de"}}},
            ]}
        }}}]}}
    })
    # frSlug is missing — fallback a URL sin slug
    assert AnibisCHScraper()._extract(body) == ["https://www.anibis.ch/fr/vi/X99"]


@pytest.mark.unit
def test_anibis_extract_returns_empty_on_garbage() -> None:
    assert AnibisCHScraper()._extract("") == []
    assert AnibisCHScraper()._extract("not json") == []
    assert AnibisCHScraper()._extract('{"pageProps": {}}') == []


# -- fetch_segment behavioural matrix ------------------------------------------
@pytest.mark.unit
def test_anibis_fetch_segment_resolves_build_id_then_fetches() -> None:
    scraper = AnibisCHScraper()
    _no_backoff(scraper)
    session = _Session([
        _Resp(200, _ANIBIS_HTML),
        _Resp(200, _ANIBIS_DATA_JSON),
    ])
    urls = _run(scraper.fetch_segment(session, {"brand": "bmw"}, 1))
    assert urls == _ANIBIS_EXPECTED
    assert len(session.calls) == 2
    assert "/fr" in session.urls[0]
    assert "/_next/data/anibisBuild99/fr/q/voitures/" in session.urls[1]


@pytest.mark.unit
def test_anibis_fetch_segment_caches_build_id() -> None:
    scraper = AnibisCHScraper()
    _no_backoff(scraper)
    session = _Session([
        _Resp(200, _ANIBIS_HTML),
        _Resp(200, _ANIBIS_DATA_JSON),
        _Resp(200, _ANIBIS_DATA_JSON),
    ])
    _run(scraper.fetch_segment(session, {"brand": "bmw"}, 1))
    urls2 = _run(scraper.fetch_segment(session, {"brand": "bmw"}, 2))
    assert urls2 == _ANIBIS_EXPECTED
    assert len(session.calls) == 3
    assert "/_next/data/" in session.urls[2]


@pytest.mark.unit
def test_anibis_fetch_segment_retries_block_then_gives_up() -> None:
    scraper = AnibisCHScraper()
    scraper._build_id = "cached"
    _no_backoff(scraper)
    session = _Session([_Resp(429), _Resp(503), _Resp(403)])
    assert _run(scraper.fetch_segment(session, {"brand": "bmw"}, 1)) == []
    assert len(session.calls) == scraper.RETRY_ATTEMPTS


@pytest.mark.unit
def test_anibis_fetch_segment_recovers_after_block() -> None:
    scraper = AnibisCHScraper()
    scraper._build_id = "cached"
    _no_backoff(scraper)
    session = _Session([_Resp(503), _Resp(200, _ANIBIS_DATA_JSON)])
    assert _run(scraper.fetch_segment(session, {"brand": "bmw"}, 1)) == _ANIBIS_EXPECTED


@pytest.mark.unit
def test_anibis_fetch_segment_404_re_resolves_build_id() -> None:
    scraper = AnibisCHScraper()
    scraper._build_id = "stale"
    _no_backoff(scraper)
    session = _Session([
        _Resp(404),
        _Resp(200, _ANIBIS_HTML),
        _Resp(200, _ANIBIS_DATA_JSON),
    ])
    urls = _run(scraper.fetch_segment(session, {"brand": "bmw"}, 1))
    assert urls == _ANIBIS_EXPECTED
    assert scraper._build_id == "anibisBuild99"


@pytest.mark.unit
def test_anibis_fetch_segment_transport_error_retries() -> None:
    scraper = AnibisCHScraper()
    scraper._build_id = "cached"
    _no_backoff(scraper)
    session = _Session([ConnectionError("reset"), _Resp(200, _ANIBIS_DATA_JSON)])
    assert _run(scraper.fetch_segment(session, {"brand": "bmw"}, 1)) == _ANIBIS_EXPECTED


# -- wiring --------------------------------------------------------------------
@pytest.mark.unit
def test_anibis_registry_resolves() -> None:
    scraper = get_scraper("anibis.ch")
    assert isinstance(scraper, AnibisCHScraper)
    assert scraper.DOMAIN == "anibis.ch"


@pytest.mark.unit
def test_anibis_domain_map_baseline() -> None:
    spec = domain_get("anibis.ch")
    assert spec is not None, "anibis.ch missing from REGISTRY"
    assert spec.tier is Tier.T1
    assert spec.waf is WAF.CF_FREE
    assert "CH" in spec.countries


# =========================================================================== #
# autolina.ch — API REST abierta m.autolina.ch (T0)
# =========================================================================== #
from scrapers.portals.autolina_ch import AutolinaCHScraper

# JSON stub de la API
_AUTOLINA_JSON = _json.dumps({
    "status": 1,
    "data": {
        "count": "94637",
        "cars": [
            {"carId": 4658983, "slug": "vw-touareg", "makeSlug": "vw", "modelSlug": "touareg", "makeName": "VW"},
            {"carId": 5002139, "slug": "hyundai-tucson", "makeSlug": "hyundai", "modelSlug": "tucson", "makeName": "HYUNDAI"},
            {"carId": 4658983, "slug": "vw-touareg", "makeSlug": "vw", "modelSlug": "touareg", "makeName": "VW"},  # dup
        ]
    }
})

_AUTOLINA_EXPECTED = [
    "https://www.autolina.ch/auto/vw-touareg/4658983",
    "https://www.autolina.ch/auto/hyundai-tucson/5002139",
]


@pytest.mark.unit
def test_autolina_partition_is_single_empty_segment() -> None:
    assert AutolinaCHScraper().partition_params() == [{}]


@pytest.mark.unit
def test_autolina_subdivide_is_noop() -> None:
    assert AutolinaCHScraper().subdivide_segment({}) == []


@pytest.mark.unit
def test_autolina_build_url() -> None:
    scraper = AutolinaCHScraper()
    assert scraper._build_url(0) == "https://m.autolina.ch/api/v2/searchcars?limit=100&offset=0"
    assert scraper._build_url(200) == "https://m.autolina.ch/api/v2/searchcars?limit=100&offset=200"


@pytest.mark.unit
def test_autolina_extract_pulls_urls_and_dedups() -> None:
    assert AutolinaCHScraper()._extract(_AUTOLINA_JSON) == _AUTOLINA_EXPECTED


@pytest.mark.unit
def test_autolina_extract_handles_missing_slug() -> None:
    body = _json.dumps({
        "status": 1,
        "data": {"count": "1", "cars": [{"carId": 999}]}
    })
    assert AutolinaCHScraper()._extract(body) == ["https://www.autolina.ch/auto/999"]


@pytest.mark.unit
def test_autolina_extract_skips_missing_carId() -> None:
    body = _json.dumps({
        "status": 1,
        "data": {"count": "2", "cars": [
            {"slug": "orphan"},
            {"carId": 111, "slug": "ok-item"},
        ]}
    })
    assert AutolinaCHScraper()._extract(body) == ["https://www.autolina.ch/auto/ok-item/111"]


@pytest.mark.unit
def test_autolina_extract_returns_empty_on_garbage() -> None:
    assert AutolinaCHScraper()._extract("") == []
    assert AutolinaCHScraper()._extract("not json") == []
    assert AutolinaCHScraper()._extract('{"status": 1}') == []
    assert AutolinaCHScraper()._extract('{"status": 1, "data": "bad"}') == []
    assert AutolinaCHScraper()._extract('{"status": 1, "data": {"cars": "not list"}}') == []


# -- fetch_segment behavioural matrix ------------------------------------------
@pytest.mark.unit
def test_autolina_fetch_segment_extracts_on_200() -> None:
    scraper = AutolinaCHScraper()
    session = _Session([_Resp(200, _AUTOLINA_JSON)])
    urls = _run(scraper.fetch_segment(session, {}, 1))
    assert urls == _AUTOLINA_EXPECTED
    assert len(session.calls) == 1
    assert "offset=0" in session.urls[0]
    assert "limit=100" in session.urls[0]


@pytest.mark.unit
def test_autolina_fetch_segment_page2_offset() -> None:
    scraper = AutolinaCHScraper()
    session = _Session([_Resp(200, _AUTOLINA_JSON)])
    _run(scraper.fetch_segment(session, {}, 3))
    assert "offset=200" in session.urls[0]


@pytest.mark.unit
def test_autolina_fetch_segment_retries_block_then_gives_up() -> None:
    scraper = AutolinaCHScraper()
    _no_backoff(scraper)
    session = _Session([_Resp(429), _Resp(503), _Resp(403)])
    assert _run(scraper.fetch_segment(session, {}, 1)) == []
    assert len(session.calls) == scraper.RETRY_ATTEMPTS


@pytest.mark.unit
def test_autolina_fetch_segment_recovers_after_block() -> None:
    scraper = AutolinaCHScraper()
    _no_backoff(scraper)
    session = _Session([_Resp(503), _Resp(200, _AUTOLINA_JSON)])
    assert _run(scraper.fetch_segment(session, {}, 1)) == _AUTOLINA_EXPECTED


@pytest.mark.unit
def test_autolina_fetch_segment_non_retryable_status() -> None:
    scraper = AutolinaCHScraper()
    session = _Session([_Resp(404)])
    assert _run(scraper.fetch_segment(session, {}, 1)) == []
    assert len(session.calls) == 1


@pytest.mark.unit
def test_autolina_fetch_segment_transport_error_retries() -> None:
    scraper = AutolinaCHScraper()
    _no_backoff(scraper)
    session = _Session([ConnectionError("reset"), _Resp(200, _AUTOLINA_JSON)])
    assert _run(scraper.fetch_segment(session, {}, 1)) == _AUTOLINA_EXPECTED
    assert len(session.calls) == 2


# -- wiring --------------------------------------------------------------------
@pytest.mark.unit
def test_autolina_registry_resolves() -> None:
    scraper = get_scraper("autolina.ch")
    assert isinstance(scraper, AutolinaCHScraper)
    assert scraper.DOMAIN == "autolina.ch"


@pytest.mark.unit
def test_autolina_domain_map_baseline() -> None:
    spec = domain_get("autolina.ch")
    assert spec is not None, "autolina.ch missing from REGISTRY"
    assert spec.tier is Tier.T0
    assert spec.waf is WAF.NONE
    assert "CH" in spec.countries
