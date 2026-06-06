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
from typing import Any

import pytest

from scrapers.engine.router.domain_map import Tier, WAF
from scrapers.engine.router.domain_map import get as domain_get
from scrapers.portals import get_scraper
from scrapers.portals.base import BasePortalScraper
from scrapers.portals.ocasionplus_es import OcasionPlusESScraper
from scrapers.portals.autokopen_nl import AutoKopenNLScraper
from scrapers.portals.nederlandmobiel_nl import NederlandMobielNLScraper
from scrapers.portals.sitemap_listing_base import SitemapListingScraper


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
# ocasionplus.com — migrado al sitemap de fichas (multi-strategy 2026-06)
# =========================================================================== #
@pytest.mark.unit
def test_ocasion_is_sitemap_based() -> None:
    s = OcasionPlusESScraper()
    assert isinstance(s, SitemapListingScraper)
    assert s.SITEMAP_URL == "https://www.ocasionplus.com/sitemap.xml"
    assert s.CHILD_RE.search("/sitemap.fichas-coches.xml")
    assert not s.CHILD_RE.search("/sitemap.coches_audi.xml")  # per-brand SRP shards skipped
    assert s.DETAIL_RE.search("/coches-segunda-mano/skoda-karoq-10-tsi-2024-hs0htqaz")
    s._validate()


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
# autokopen.nl — migrado a los sitemaps de listings 100/101/102 (multi-strategy 2026-06)
# =========================================================================== #
@pytest.mark.unit
def test_autokopen_is_sitemap_based() -> None:
    s = AutoKopenNLScraper()
    assert isinstance(s, SitemapListingScraper)
    assert s.SITEMAP_URLS == (
        "https://autokopen.nl/sitemap/100.xml",
        "https://autokopen.nl/sitemap/101.xml",
        "https://autokopen.nl/sitemap/102.xml",
    )
    assert s.DETAIL_RE.search("/auto/detail/mercedes-benz-c-klasse-2026-10999")
    s._validate()


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
