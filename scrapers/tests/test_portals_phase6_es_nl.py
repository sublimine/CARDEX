"""
Phase-6 portal scraper tests — ocasionplus.com (ES), autokopen.nl (NL), nederlandmobiel.nl (NL).

Cada portal se ejerce directamente contra una sesión fake duck-typed (sin curl_cffi):
partition_params grid, one-level subdivide_segment terminación, _build_url / _build_data_url
request shaping, _extract parsing + dedup, fetch_segment retry / status handling. Dos capas
de wiring también se afirman — el portal registry (`get_scraper`) y el domain→tier
registry (`domain_map`) — para que el drift de clase/string/tier salga aquí en vez
de en runtime.

Coroutines se ejecutan sincrónicamente vía asyncio.run() (convención del engine).
fetch_segment tests stub `_retry_backoff` a no-op para que la suite nunca duerma.
"""
from __future__ import annotations

import asyncio
import json as _json
from itertools import product
from typing import Any

import pytest

from scrapers.engine.router.domain_map import Tier, WAF
from scrapers.engine.router.domain_map import get as domain_get
from scrapers.portals import get_scraper
from scrapers.portals.base import BasePortalScraper
from scrapers.portals.ocasionplus_es import OcasionPlusESScraper
from scrapers.portals.autokopen_nl import AutoKopenNLScraper
from scrapers.portals.nederlandmobiel_nl import NederlandMobielNLScraper


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

    async def post(self, url: str, **kwargs: Any) -> _Resp:
        self.calls.append({"method": "POST", "url": url, **kwargs})
        return self._next()


def _no_backoff(scraper: BasePortalScraper) -> None:
    """Stub del exponential backoff para que los tests de retry corran al instante."""

    async def _noop(attempt: int, factor: float = 1.0) -> None:
        return None

    scraper._retry_backoff = _noop  # type: ignore[method-assign]


# =========================================================================== #
# ocasionplus.com — Next.js data route (T1, single segment)
# =========================================================================== #

# HTML stub con __NEXT_DATA__ conteniendo buildId
_OCASION_HTML = (
    '<html><head><script id="__NEXT_DATA__" type="application/json">'
    '{"props":{"pageProps":{}},"page":"/coches-segunda-mano",'
    '"buildId":"ocasionBuild789","isFallback":false}'
    '</script></head></html>'
)

# JSON stub de la data route — pageProps.results array
_OCASION_DATA_JSON = _json.dumps({
    "pageProps": {
        "results": [
            {"url": "/coches-segunda-mano/seat-leon-2020/12345"},
            {"url": "/coches-segunda-mano/volkswagen-golf-2019/67890"},
            {"url": "/coches-segunda-mano/seat-leon-2020/12345"},  # dup
        ]
    }
})

_OCASION_EXPECTED = [
    "https://www.ocasionplus.com/coches-segunda-mano/seat-leon-2020/12345",
    "https://www.ocasionplus.com/coches-segunda-mano/volkswagen-golf-2019/67890",
]

# JSON stub — pageProps.searchResults.vehicles (one level deeper)
_OCASION_DATA_NESTED_JSON = _json.dumps({
    "pageProps": {
        "searchResults": {
            "vehicles": [
                {"href": "/coches-segunda-mano/bmw-x3/11111"},
                {"link": "https://www.ocasionplus.com/coches-segunda-mano/audi-a4/22222"},
            ]
        }
    }
})

_OCASION_NESTED_EXPECTED = [
    "https://www.ocasionplus.com/coches-segunda-mano/bmw-x3/11111",
    "https://www.ocasionplus.com/coches-segunda-mano/audi-a4/22222",
]

# JSON stub — slug + id composition
_OCASION_DATA_SLUG_JSON = _json.dumps({
    "pageProps": {
        "listings": [
            {"slug": "toyota-yaris-2021", "id": 33333},
            {"slug": "ford-focus-2020", "vehicleId": 44444},
        ]
    }
})

_OCASION_SLUG_EXPECTED = [
    "https://www.ocasionplus.com/coches-segunda-mano/toyota-yaris-2021/33333",
    "https://www.ocasionplus.com/coches-segunda-mano/ford-focus-2020/44444",
]


# -- partition -----------------------------------------------------------------
@pytest.mark.unit
def test_ocasion_partition_single_segment() -> None:
    scraper = OcasionPlusESScraper()
    segments = scraper.partition_params()
    assert segments == [{}]


# -- buildId regex -------------------------------------------------------------
@pytest.mark.unit
def test_ocasion_build_id_regex() -> None:
    from scrapers.portals.ocasionplus_es import _BUILD_ID_RE
    match = _BUILD_ID_RE.search(_OCASION_HTML)
    assert match is not None
    assert match.group(1) == "ocasionBuild789"


# -- _extract ------------------------------------------------------------------
@pytest.mark.unit
def test_ocasion_extract_direct_url_field() -> None:
    scraper = OcasionPlusESScraper()
    urls = scraper._extract(_OCASION_DATA_JSON)
    assert urls == _OCASION_EXPECTED


@pytest.mark.unit
def test_ocasion_extract_nested_listing_array() -> None:
    scraper = OcasionPlusESScraper()
    urls = scraper._extract(_OCASION_DATA_NESTED_JSON)
    assert urls == _OCASION_NESTED_EXPECTED


@pytest.mark.unit
def test_ocasion_extract_slug_id_composition() -> None:
    scraper = OcasionPlusESScraper()
    urls = scraper._extract(_OCASION_DATA_SLUG_JSON)
    assert urls == _OCASION_SLUG_EXPECTED


@pytest.mark.unit
def test_ocasion_extract_dedups() -> None:
    scraper = OcasionPlusESScraper()
    urls = scraper._extract(_OCASION_DATA_JSON)
    assert len(urls) == 2  # 3 items, 1 dup -> 2 unique


@pytest.mark.unit
def test_ocasion_extract_returns_empty_on_garbage() -> None:
    scraper = OcasionPlusESScraper()
    assert scraper._extract("") == []
    assert scraper._extract("not json") == []
    assert scraper._extract('{"pageProps": "bad"}') == []
    assert scraper._extract('{"pageProps": {}}') == []


# -- _build_data_url -----------------------------------------------------------
@pytest.mark.unit
def test_ocasion_build_data_url() -> None:
    scraper = OcasionPlusESScraper()
    scraper._build_id = "testBuild123"
    url = scraper._build_data_url(1)
    assert url == (
        "https://www.ocasionplus.com/_next/data/testBuild123/"
        "coches-segunda-mano.json?page=1"
    )


# -- fetch_segment behavioural matrix -----------------------------------------
@pytest.mark.unit
def test_ocasion_fetch_segment_resolves_build_id_and_extracts() -> None:
    scraper = OcasionPlusESScraper()
    _no_backoff(scraper)
    session = _Session([
        _Resp(200, _OCASION_HTML),         # buildId resolution
        _Resp(200, _OCASION_DATA_JSON),    # data route
    ])
    urls = _run(scraper.fetch_segment(session, {}, 1))
    assert urls == _OCASION_EXPECTED
    assert scraper._build_id == "ocasionBuild789"
    assert len(session.calls) == 2


@pytest.mark.unit
def test_ocasion_fetch_segment_uses_cached_build_id() -> None:
    scraper = OcasionPlusESScraper()
    scraper._build_id = "cached"
    session = _Session([_Resp(200, _OCASION_DATA_JSON)])
    urls = _run(scraper.fetch_segment(session, {}, 1))
    assert urls == _OCASION_EXPECTED
    assert len(session.calls) == 1  # no resolution call


@pytest.mark.unit
def test_ocasion_fetch_segment_retries_block_then_gives_up() -> None:
    scraper = OcasionPlusESScraper()
    scraper._build_id = "cached"
    _no_backoff(scraper)
    session = _Session([_Resp(429), _Resp(503), _Resp(403)])
    assert _run(scraper.fetch_segment(session, {}, 1)) == []
    assert len(session.calls) == scraper.RETRY_ATTEMPTS


@pytest.mark.unit
def test_ocasion_fetch_segment_recovers_after_block() -> None:
    scraper = OcasionPlusESScraper()
    scraper._build_id = "cached"
    _no_backoff(scraper)
    session = _Session([_Resp(503), _Resp(200, _OCASION_DATA_JSON)])
    assert _run(scraper.fetch_segment(session, {}, 1)) == _OCASION_EXPECTED
    assert len(session.calls) == 2


@pytest.mark.unit
def test_ocasion_fetch_segment_404_re_resolves_build_id() -> None:
    """404 en la data route => re-resolver buildId (nuevo deploy)."""
    scraper = OcasionPlusESScraper()
    scraper._build_id = "stale"
    _no_backoff(scraper)
    session = _Session([
        _Resp(404),                        # stale buildId
        _Resp(200, _OCASION_HTML),         # re-resolve
        _Resp(200, _OCASION_DATA_JSON),    # retry con nuevo buildId
    ])
    urls = _run(scraper.fetch_segment(session, {}, 1))
    assert urls == _OCASION_EXPECTED
    assert scraper._build_id == "ocasionBuild789"


@pytest.mark.unit
def test_ocasion_fetch_segment_transport_error_retries() -> None:
    scraper = OcasionPlusESScraper()
    scraper._build_id = "cached"
    _no_backoff(scraper)
    session = _Session([ConnectionError("reset"), _Resp(200, _OCASION_DATA_JSON)])
    assert _run(scraper.fetch_segment(session, {}, 1)) == _OCASION_EXPECTED
    assert len(session.calls) == 2


@pytest.mark.unit
def test_ocasion_fetch_segment_build_id_resolve_failure() -> None:
    """Si no se puede resolver buildId, retorna vacío sin crash."""
    scraper = OcasionPlusESScraper()
    _no_backoff(scraper)
    session = _Session([
        _Resp(200, "<html>no next data here</html>"),  # no buildId
    ])
    urls = _run(scraper.fetch_segment(session, {}, 1))
    assert urls == []


# -- wiring -------------------------------------------------------------------
@pytest.mark.unit
def test_ocasion_registry_resolves() -> None:
    scraper = get_scraper("ocasionplus.com")
    assert isinstance(scraper, OcasionPlusESScraper)
    assert scraper.DOMAIN == "ocasionplus.com"


@pytest.mark.unit
def test_ocasion_domain_map_baseline() -> None:
    spec = domain_get("ocasionplus.com")
    assert spec is not None, "ocasionplus.com missing from REGISTRY"
    assert spec.tier is Tier.T1
    assert spec.waf is WAF.NONE
    assert "ES" in spec.countries


# =========================================================================== #
# autokopen.nl — Next.js data route (T1, year x price grid)
# =========================================================================== #

# HTML stub con __NEXT_DATA__ conteniendo buildId
_AUTOKOPEN_HTML = (
    '<html><head><script id="__NEXT_DATA__" type="application/json">'
    '{"props":{"pageProps":{}},"page":"/auto",'
    '"buildId":"autokopenBuild456","isFallback":false}'
    '</script></head></html>'
)

# JSON stub de la data route — pageProps.results array
_AUTOKOPEN_DATA_JSON = _json.dumps({
    "pageProps": {
        "results": [
            {"url": "/auto/detail/bmw-x5-2020-sc-autounit_52420900"},
            {"url": "/auto/detail/volkswagen-golf-2021-dealer_123456"},
            {"url": "/auto/detail/bmw-x5-2020-sc-autounit_52420900"},  # dup
        ]
    }
})

_AUTOKOPEN_EXPECTED = [
    "https://autokopen.nl/auto/detail/bmw-x5-2020-sc-autounit_52420900",
    "https://autokopen.nl/auto/detail/volkswagen-golf-2021-dealer_123456",
]

# JSON stub — slug composition fallback
_AUTOKOPEN_DATA_SLUG_JSON = _json.dumps({
    "pageProps": {
        "items": [
            {"slug": "audi-a3-sportback-2022"},
            {"friendlyUrl": "opel-corsa-2019"},
        ]
    }
})

_AUTOKOPEN_SLUG_EXPECTED = [
    "https://autokopen.nl/auto/detail/audi-a3-sportback-2022",
    "https://autokopen.nl/auto/detail/opel-corsa-2019",
]

_YP = {"year_min": 2018, "year_max": 2020, "price_min": 10_000, "price_max": 20_000}
_YP_OPEN = {"year_min": 2024, "year_max": 2026, "price_min": 100_000, "price_max": None}


# -- partition -----------------------------------------------------------------
@pytest.mark.unit
def test_autokopen_partition_shape() -> None:
    scraper = AutoKopenNLScraper()
    segments = scraper.partition_params()
    assert len(segments) == len(scraper.YEAR_BANDS) * len(scraper.PRICE_BANDS)
    keys = {(s["year_min"], s["year_max"], s["price_min"], s["price_max"]) for s in segments}
    assert len(keys) == len(segments)
    assert not any("_fine" in s for s in segments)


# -- subdivide_segment --------------------------------------------------------
@pytest.mark.unit
def test_autokopen_subdivide_then_stops() -> None:
    scraper = AutoKopenNLScraper()
    subs = scraper.subdivide_segment(dict(_YP))
    assert subs
    for s in subs:
        assert s["year_min"] == s["year_max"]
        assert s["_fine"] is True
    assert {s["year_min"] for s in subs} == {2018, 2019, 2020}
    assert scraper.subdivide_segment(subs[0]) == []


@pytest.mark.unit
def test_autokopen_subdivide_open_top_band_reopens_final_subband() -> None:
    subs = AutoKopenNLScraper().subdivide_segment(dict(_YP_OPEN))
    assert subs
    by_year: dict[int, list[Any]] = {}
    for s in subs:
        by_year.setdefault(s["year_min"], []).append(s["price_max"])
    for tops in by_year.values():
        assert tops[-1] is None
        assert all(t is not None for t in tops[:-1])


# -- _split_price --------------------------------------------------------------
@pytest.mark.unit
def test_autokopen_split_price_closed_band() -> None:
    bands = AutoKopenNLScraper._split_price(10_000, 20_000)
    assert bands[0][0] == 10_000
    assert bands[-1][1] == 20_000
    assert all(b[0] < b[1] for b in bands)
    # contiguous
    for i in range(len(bands) - 1):
        assert bands[i][1] == bands[i + 1][0]


@pytest.mark.unit
def test_autokopen_split_price_open_band() -> None:
    bands = AutoKopenNLScraper._split_price(100_000, None)
    assert bands[0][0] == 100_000
    assert bands[-1][1] is None


# -- buildId regex -------------------------------------------------------------
@pytest.mark.unit
def test_autokopen_build_id_regex() -> None:
    from scrapers.portals.autokopen_nl import _BUILD_ID_RE
    match = _BUILD_ID_RE.search(_AUTOKOPEN_HTML)
    assert match is not None
    assert match.group(1) == "autokopenBuild456"


# -- _extract ------------------------------------------------------------------
@pytest.mark.unit
def test_autokopen_extract_direct_url_field() -> None:
    scraper = AutoKopenNLScraper()
    urls = scraper._extract(_AUTOKOPEN_DATA_JSON)
    assert urls == _AUTOKOPEN_EXPECTED


@pytest.mark.unit
def test_autokopen_extract_slug_composition() -> None:
    scraper = AutoKopenNLScraper()
    urls = scraper._extract(_AUTOKOPEN_DATA_SLUG_JSON)
    assert urls == _AUTOKOPEN_SLUG_EXPECTED


@pytest.mark.unit
def test_autokopen_extract_dedups() -> None:
    scraper = AutoKopenNLScraper()
    urls = scraper._extract(_AUTOKOPEN_DATA_JSON)
    assert len(urls) == 2  # 3 items, 1 dup -> 2 unique


@pytest.mark.unit
def test_autokopen_extract_returns_empty_on_garbage() -> None:
    scraper = AutoKopenNLScraper()
    assert scraper._extract("") == []
    assert scraper._extract("not json") == []
    assert scraper._extract('{"pageProps": "bad"}') == []
    assert scraper._extract('{"pageProps": {}}') == []


# -- _build_data_url -----------------------------------------------------------
@pytest.mark.unit
def test_autokopen_build_data_url_with_params() -> None:
    scraper = AutoKopenNLScraper()
    scraper._build_id = "testBuild"
    url = scraper._build_data_url(
        {"year_min": 2020, "year_max": 2022, "price_min": 5000, "price_max": 15000},
        3,
    )
    assert url == (
        "https://autokopen.nl/_next/data/testBuild/auto.json?"
        "page=3&year_min=2020&year_max=2022&price_min=5000&price_max=15000"
    )


@pytest.mark.unit
def test_autokopen_build_data_url_open_price() -> None:
    scraper = AutoKopenNLScraper()
    scraper._build_id = "testBuild"
    url = scraper._build_data_url(
        {"year_min": 2024, "year_max": 2026, "price_min": 100_000, "price_max": None},
        1,
    )
    assert "price_max" not in url
    assert "price_min=100000" in url


# -- fetch_segment behavioural matrix -----------------------------------------
@pytest.mark.unit
def test_autokopen_fetch_segment_resolves_build_id_and_extracts() -> None:
    scraper = AutoKopenNLScraper()
    _no_backoff(scraper)
    session = _Session([
        _Resp(200, _AUTOKOPEN_HTML),          # buildId resolution
        _Resp(200, _AUTOKOPEN_DATA_JSON),     # data route
    ])
    urls = _run(scraper.fetch_segment(session, _YP, 1))
    assert urls == _AUTOKOPEN_EXPECTED
    assert scraper._build_id == "autokopenBuild456"
    assert len(session.calls) == 2


@pytest.mark.unit
def test_autokopen_fetch_segment_uses_cached_build_id() -> None:
    scraper = AutoKopenNLScraper()
    scraper._build_id = "cached"
    session = _Session([_Resp(200, _AUTOKOPEN_DATA_JSON)])
    urls = _run(scraper.fetch_segment(session, _YP, 1))
    assert urls == _AUTOKOPEN_EXPECTED
    assert len(session.calls) == 1


@pytest.mark.unit
def test_autokopen_fetch_segment_retries_block_then_gives_up() -> None:
    scraper = AutoKopenNLScraper()
    scraper._build_id = "cached"
    _no_backoff(scraper)
    session = _Session([_Resp(429), _Resp(503), _Resp(403)])
    assert _run(scraper.fetch_segment(session, _YP, 1)) == []
    assert len(session.calls) == scraper.RETRY_ATTEMPTS


@pytest.mark.unit
def test_autokopen_fetch_segment_recovers_after_block() -> None:
    scraper = AutoKopenNLScraper()
    scraper._build_id = "cached"
    _no_backoff(scraper)
    session = _Session([_Resp(503), _Resp(200, _AUTOKOPEN_DATA_JSON)])
    assert _run(scraper.fetch_segment(session, _YP, 1)) == _AUTOKOPEN_EXPECTED
    assert len(session.calls) == 2


@pytest.mark.unit
def test_autokopen_fetch_segment_404_re_resolves_build_id() -> None:
    """404 en la data route => re-resolver buildId (nuevo deploy)."""
    scraper = AutoKopenNLScraper()
    scraper._build_id = "stale"
    _no_backoff(scraper)
    session = _Session([
        _Resp(404),                           # stale buildId
        _Resp(200, _AUTOKOPEN_HTML),          # re-resolve
        _Resp(200, _AUTOKOPEN_DATA_JSON),     # retry con nuevo buildId
    ])
    urls = _run(scraper.fetch_segment(session, _YP, 1))
    assert urls == _AUTOKOPEN_EXPECTED
    assert scraper._build_id == "autokopenBuild456"


@pytest.mark.unit
def test_autokopen_fetch_segment_transport_error_retries() -> None:
    scraper = AutoKopenNLScraper()
    scraper._build_id = "cached"
    _no_backoff(scraper)
    session = _Session([ConnectionError("reset"), _Resp(200, _AUTOKOPEN_DATA_JSON)])
    assert _run(scraper.fetch_segment(session, _YP, 1)) == _AUTOKOPEN_EXPECTED
    assert len(session.calls) == 2


# -- wiring -------------------------------------------------------------------
@pytest.mark.unit
def test_autokopen_registry_resolves() -> None:
    scraper = get_scraper("autokopen.nl")
    assert isinstance(scraper, AutoKopenNLScraper)
    assert scraper.DOMAIN == "autokopen.nl"


@pytest.mark.unit
def test_autokopen_domain_map_baseline() -> None:
    spec = domain_get("autokopen.nl")
    assert spec is not None, "autokopen.nl missing from REGISTRY"
    assert spec.tier is Tier.T1
    assert spec.waf is WAF.NONE
    assert "NL" in spec.countries


# =========================================================================== #
# nederlandmobiel.nl — PHP SSR HTML regex extraction (T0, price grid)
# =========================================================================== #

_NM_HTML = """
<html><body>
<div class="results">
  <a href="/tweedehands-auto/fiat/panda-grande-panda-0-9-twinair-turbo/22273556">
    <img src="https://images.nederlandmobiel.nl/auto/22273556/320/1.jpg"/>
  </a>
  <a href="/tweedehands-auto/bmw/3-serie-touring-320i-m-sport/22280001">
    <img src="https://images.nederlandmobiel.nl/auto/22280001/320/1.jpg"/>
  </a>
  <a href="/tweedehands-auto/fiat/panda-grande-panda-0-9-twinair-turbo/22273556">
    <!-- duplicate -->
  </a>
  <a href="/tweedehands-auto/audi/a4-avant-40-tfsi-s-line/22290003">
    <img src="https://images.nederlandmobiel.nl/auto/22290003/320/1.jpg"/>
  </a>
</div>
</body></html>
"""

_NM_EXPECTED = [
    "https://www.nederlandmobiel.nl/tweedehands-auto/fiat/panda-grande-panda-0-9-twinair-turbo/22273556",
    "https://www.nederlandmobiel.nl/tweedehands-auto/bmw/3-serie-touring-320i-m-sport/22280001",
    "https://www.nederlandmobiel.nl/tweedehands-auto/audi/a4-avant-40-tfsi-s-line/22290003",
]

_NM_PRICE_PARAMS = {"price_from": 5_000, "price_to": 10_000}
_NM_PRICE_OPEN = {"price_from": 100_000, "price_to": None}


# -- partition -----------------------------------------------------------------
@pytest.mark.unit
def test_nm_partition_shape() -> None:
    scraper = NederlandMobielNLScraper()
    segments = scraper.partition_params()
    assert len(segments) == len(scraper.PRICE_BANDS)
    keys = {(s["price_from"], s["price_to"]) for s in segments}
    assert len(keys) == len(segments)
    assert not any("_fine" in s for s in segments)


# -- subdivide_segment --------------------------------------------------------
@pytest.mark.unit
def test_nm_subdivide_then_stops() -> None:
    scraper = NederlandMobielNLScraper()
    subs = scraper.subdivide_segment(dict(_NM_PRICE_PARAMS))
    assert subs
    for s in subs:
        assert s["_fine"] is True
        assert s["price_from"] < (s["price_to"] if s["price_to"] is not None else float("inf"))
    assert scraper.subdivide_segment(subs[0]) == []


@pytest.mark.unit
def test_nm_subdivide_open_top_band() -> None:
    subs = NederlandMobielNLScraper().subdivide_segment(dict(_NM_PRICE_OPEN))
    assert subs
    assert subs[-1]["price_to"] is None
    assert all(s["price_to"] is not None for s in subs[:-1])


# -- _split_price --------------------------------------------------------------
@pytest.mark.unit
def test_nm_split_price_closed_band() -> None:
    bands = NederlandMobielNLScraper._split_price(5_000, 10_000)
    assert bands[0][0] == 5_000
    assert bands[-1][1] == 10_000
    assert all(b[0] < b[1] for b in bands)
    for i in range(len(bands) - 1):
        assert bands[i][1] == bands[i + 1][0]


@pytest.mark.unit
def test_nm_split_price_open_band() -> None:
    bands = NederlandMobielNLScraper._split_price(100_000, None)
    assert bands[0][0] == 100_000
    assert bands[-1][1] is None


# -- listing regex -------------------------------------------------------------
@pytest.mark.unit
def test_nm_listing_regex_matches_detail_urls() -> None:
    scraper = NederlandMobielNLScraper()
    matches = scraper._listing_re.findall(_NM_HTML)
    paths = [m[0] for m in matches]
    assert "/tweedehands-auto/fiat/panda-grande-panda-0-9-twinair-turbo/22273556" in paths
    assert "/tweedehands-auto/bmw/3-serie-touring-320i-m-sport/22280001" in paths


@pytest.mark.unit
def test_nm_listing_regex_rejects_category_pages() -> None:
    """Category links like /tweedehands-auto/fiat should NOT match (only 2 segments)."""
    scraper = NederlandMobielNLScraper()
    html = '<a href="/tweedehands-auto/fiat">'
    assert scraper._listing_re.findall(html) == []


# -- _extract ------------------------------------------------------------------
@pytest.mark.unit
def test_nm_extract_pulls_urls_and_dedups() -> None:
    scraper = NederlandMobielNLScraper()
    urls = scraper._extract(_NM_HTML)
    assert urls == _NM_EXPECTED


@pytest.mark.unit
def test_nm_extract_returns_empty_on_no_listings() -> None:
    scraper = NederlandMobielNLScraper()
    assert scraper._extract("<html><body>No results</body></html>") == []
    assert scraper._extract("") == []


# -- _build_url ----------------------------------------------------------------
@pytest.mark.unit
def test_nm_build_url_with_price_and_page() -> None:
    scraper = NederlandMobielNLScraper()
    url = scraper._build_url({"price_from": 5000, "price_to": 10000}, 3)
    assert url == (
        "https://www.nederlandmobiel.nl/index.php?"
        "module=zoeken&voertuig=auto&prijs_van=5000&prijs_tm=10000&pagina=3"
    )


@pytest.mark.unit
def test_nm_build_url_page_1_no_pagina() -> None:
    scraper = NederlandMobielNLScraper()
    url = scraper._build_url({"price_from": 0, "price_to": 1000}, 1)
    assert "pagina" not in url


@pytest.mark.unit
def test_nm_build_url_open_price_no_prijs_tm() -> None:
    scraper = NederlandMobielNLScraper()
    url = scraper._build_url({"price_from": 100_000, "price_to": None}, 1)
    assert "prijs_van=100000" in url
    assert "prijs_tm" not in url


# -- fetch_segment behavioural matrix -----------------------------------------
@pytest.mark.unit
def test_nm_fetch_segment_extracts_on_200() -> None:
    scraper = NederlandMobielNLScraper()
    session = _Session([_Resp(200, _NM_HTML)])
    urls = _run(scraper.fetch_segment(session, _NM_PRICE_PARAMS, 1))
    assert urls == _NM_EXPECTED
    assert len(session.calls) == 1


@pytest.mark.unit
def test_nm_fetch_segment_retries_block_then_gives_up() -> None:
    scraper = NederlandMobielNLScraper()
    _no_backoff(scraper)
    session = _Session([_Resp(429), _Resp(503), _Resp(403)])
    assert _run(scraper.fetch_segment(session, _NM_PRICE_PARAMS, 1)) == []
    assert len(session.calls) == scraper.RETRY_ATTEMPTS


@pytest.mark.unit
def test_nm_fetch_segment_recovers_after_block() -> None:
    scraper = NederlandMobielNLScraper()
    _no_backoff(scraper)
    session = _Session([_Resp(503), _Resp(200, _NM_HTML)])
    assert _run(scraper.fetch_segment(session, _NM_PRICE_PARAMS, 1)) == _NM_EXPECTED
    assert len(session.calls) == 2


@pytest.mark.unit
def test_nm_fetch_segment_non_retryable_status() -> None:
    scraper = NederlandMobielNLScraper()
    session = _Session([_Resp(404)])
    assert _run(scraper.fetch_segment(session, _NM_PRICE_PARAMS, 1)) == []
    assert len(session.calls) == 1


@pytest.mark.unit
def test_nm_fetch_segment_transport_error_retries() -> None:
    scraper = NederlandMobielNLScraper()
    _no_backoff(scraper)
    session = _Session([ConnectionError("reset"), _Resp(200, _NM_HTML)])
    assert _run(scraper.fetch_segment(session, _NM_PRICE_PARAMS, 1)) == _NM_EXPECTED
    assert len(session.calls) == 2


# -- wiring -------------------------------------------------------------------
@pytest.mark.unit
def test_nm_registry_resolves() -> None:
    scraper = get_scraper("nederlandmobiel.nl")
    assert isinstance(scraper, NederlandMobielNLScraper)
    assert scraper.DOMAIN == "nederlandmobiel.nl"


@pytest.mark.unit
def test_nm_domain_map_baseline() -> None:
    spec = domain_get("nederlandmobiel.nl")
    assert spec is not None, "nederlandmobiel.nl missing from REGISTRY"
    assert spec.tier is Tier.T0
    assert spec.waf is WAF.NONE
    assert "NL" in spec.countries


# =========================================================================== #
# Cross-portal sanity — all Phase 6 scrapers instantiate and satisfy ABC
# =========================================================================== #
@pytest.mark.unit
@pytest.mark.parametrize("domain,cls", [
    ("ocasionplus.com", OcasionPlusESScraper),
    ("autokopen.nl", AutoKopenNLScraper),
    ("nederlandmobiel.nl", NederlandMobielNLScraper),
])
def test_phase6_scraper_is_concrete_subclass(domain: str, cls: type) -> None:
    scraper = cls()
    assert isinstance(scraper, BasePortalScraper)
    assert scraper.DOMAIN == domain
    assert scraper.COUNTRY in ("ES", "NL")
    assert scraper.PAGE_SIZE > 0
    assert scraper.MAX_PAGES > 0
    segments = scraper.partition_params()
    assert isinstance(segments, list)
    assert len(segments) >= 1


@pytest.mark.unit
@pytest.mark.parametrize("domain", [
    "ocasionplus.com",
    "autokopen.nl",
    "nederlandmobiel.nl",
])
def test_phase6_domain_map_has_entry(domain: str) -> None:
    spec = domain_get(domain)
    assert spec is not None, f"{domain} missing from domain_map REGISTRY"
    assert spec.tier in (Tier.T0, Tier.T1)
