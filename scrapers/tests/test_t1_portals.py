"""
T1 portal scraper tests — HtmlSearchScraper engine + AutoTrack/Autocasión primitives.

Mirrors test_portals.py: coroutines are driven with asyncio.run(); a fake
duck-typed session yields queued responses. Three layers:

  * HtmlSearchScraper primitives (URL building, extraction, retry/softblock GET,
    sitemap → segment enumeration incl. <sitemapindex> recursion and dedup),
    exercised through the two concrete portals.
  * subdivide_segment for AutoTrack (brand → brand+model from the sitemap map).
  * One run() smoke test per portal proving the seeded pipeline reaches OK with a
    country-correct identity (the orchestration itself is covered in test_portals).
"""
from __future__ import annotations

import asyncio
from typing import Any

import pytest

from scrapers.engine.identity import profile, store
from scrapers.engine.identity.profile import IdentityStatus, ProxyTier
from scrapers.portals import get_scraper
from scrapers.portals.autocasion_com import AutocasionESScraper
from scrapers.portals.autotrack_nl import AutoTrackNLScraper
from scrapers.portals.es.autocasion import AutocasionES
from scrapers.portals.html_search_base import HtmlSearchScraper
from scrapers.portals.nl.autotrack import AutotrackNL


def _run(coro: Any) -> Any:
    return asyncio.run(coro)


# --------------------------------------------------------------------------- #
# fakes
# --------------------------------------------------------------------------- #
class _Resp:
    """Minimal duck-typed HTTP response (curl_cffi shape: .status_code, .text)."""

    def __init__(self, status_code: int, text: str = "") -> None:
        self.status_code = status_code
        self.text = text


class _Session:
    """Fake AsyncSession: yields queued responses (or raises queued exceptions)."""

    def __init__(self, responses: list[Any]) -> None:
        self._responses = list(responses)
        self.urls: list[str] = []

    async def get(self, url: str, timeout: int | None = None) -> _Resp:
        self.urls.append(url)
        item = self._responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def _no_backoff(scraper: HtmlSearchScraper) -> None:
    async def _noop(attempt: int, factor: float = 1.0) -> None:
        return None

    scraper._retry_backoff = _noop  # type: ignore[method-assign]


def _save_active_identity(conn, country: str, ip: str, uuid: str):
    idy = profile.generate(country, ip, ProxyTier.ISP_STICKY, identity_id=uuid)
    store.save(conn, idy)
    conn.execute(
        "UPDATE identities SET status=?, warming_done=1, trust_score=1.0 WHERE id=?",
        (IdentityStatus.ACTIVE.value, idy.id),
    )
    return store.get(conn, idy.id)


# --------------------------------------------------------------------------- #
# config + validation
# --------------------------------------------------------------------------- #
@pytest.mark.unit
@pytest.mark.parametrize(
    "cls, domain, country, host",
    [
        (AutotrackNL, "autotrack.nl", "NL", "www.autotrack.nl"),
        (AutocasionES, "autocasion.com", "ES", "www.autocasion.com"),
    ],
)
def test_t1_config_and_validate(cls, domain, country, host) -> None:
    scraper = cls()
    assert scraper.DOMAIN == domain
    assert scraper.COUNTRY == country
    assert scraper.HOST == host
    assert scraper.SITEMAP_URL.startswith("https://")
    assert scraper.DETAIL_RE is not None
    scraper._validate()  # must not raise


@pytest.mark.unit
def test_t1_validate_requires_host_sitemap_detail(conn) -> None:
    class _Broken(HtmlSearchScraper):
        DOMAIN = "x.test"
        COUNTRY = "NL"
        # HOST / SITEMAP_URL / DETAIL_RE unset

        def _build_url(self, params, page_num):  # pragma: no cover - never reached
            return ""

        def _loc_to_segment(self, loc):  # pragma: no cover - never reached
            return None

    with pytest.raises(ValueError):
        _run(_Broken().run(conn, _Session([])))


@pytest.mark.unit
def test_t1_registry_resolves_both_portals() -> None:
    # Both domains are registered to their SSR/BasePortalScraper variants, not the
    # legacy HtmlSearchScraper classes whose primitives are unit-tested above.
    assert isinstance(get_scraper("autotrack.nl"), AutoTrackNLScraper)
    assert isinstance(get_scraper("autocasion.com"), AutocasionESScraper)


# --------------------------------------------------------------------------- #
# AutoTrack — URL building
# --------------------------------------------------------------------------- #
@pytest.mark.unit
def test_autotrack_build_url_brand_only() -> None:
    url = AutotrackNL()._build_url({"brand": "volkswagen"}, 2)
    assert url == (
        "https://www.autotrack.nl/aanbod"
        "?data.merkModel.filter.0.slug=volkswagen"
        "&pageNumber=2&pageSize=30"
        "&sortField=relevance&sortOrder=asc"
    )


@pytest.mark.unit
def test_autotrack_build_url_brand_and_model() -> None:
    url = AutotrackNL()._build_url({"brand": "volkswagen", "model": "golf"}, 1)
    assert url.endswith("&data.merkModel.filter.0.models.0.slug=golf")
    assert "pageNumber=1" in url


@pytest.mark.unit
def test_autotrack_extract_detail_links_and_dedups() -> None:
    html = (
        '<a href="/a/volkswagen-golf-1234567">x</a>'
        '<a href="https://www.autotrack.nl/a/audi-a4-987654?src=grid">y</a>'
        '<a href="/a/volkswagen-golf-1234567">dup</a>'
        '<a href="/aanbod/volkswagen">category — ignored</a>'
        '<a href="/a/short-123">too few digits — ignored</a>'
    )
    urls = AutotrackNL()._extract(html)
    assert urls == [
        "https://www.autotrack.nl/a/volkswagen-golf-1234567",
        "https://www.autotrack.nl/a/audi-a4-987654",
    ]


# --------------------------------------------------------------------------- #
# Autocasión — URL building
# --------------------------------------------------------------------------- #
@pytest.mark.unit
def test_autocasion_build_url_page1_is_bare() -> None:
    url = AutocasionES()._build_url({"category": "audi-a3"}, 1)
    assert url == "https://www.autocasion.com/coches-segunda-mano/audi-a3-ocasion"
    assert "?page" not in url


@pytest.mark.unit
def test_autocasion_build_url_page_n_adds_param() -> None:
    url = AutocasionES()._build_url({"category": "audi-a3"}, 5)
    assert url == "https://www.autocasion.com/coches-segunda-mano/audi-a3-ocasion?page=5"


@pytest.mark.unit
def test_autocasion_extract_detail_links_and_dedups() -> None:
    html = (
        '<a href="/coches-segunda-mano/audi/audi-a3-sportback-ref123456">x</a>'
        '<a href="/coches-segunda-mano/bmw/serie-3-320d-ref99">y</a>'
        '<a href="/coches-segunda-mano/audi/audi-a3-sportback-ref123456">dup</a>'
        '<a href="/coches-segunda-mano/audi-a3-ocasion">category — ignored</a>'
    )
    urls = AutocasionES()._extract(html)
    assert urls == [
        "https://www.autocasion.com/coches-segunda-mano/audi/audi-a3-sportback-ref123456",
        "https://www.autocasion.com/coches-segunda-mano/bmw/serie-3-320d-ref99",
    ]


# --------------------------------------------------------------------------- #
# fetch_segment — retry / softblock / status (shared HtmlSearch loop)
# --------------------------------------------------------------------------- #
@pytest.mark.unit
def test_fetch_segment_extracts_on_200() -> None:
    scraper = AutotrackNL()
    html = '<a href="/a/seat-ibiza-555555">a</a>'
    session = _Session([_Resp(200, html)])
    urls = _run(scraper.fetch_segment(session, {"brand": "seat"}, 1))
    assert urls == ["https://www.autotrack.nl/a/seat-ibiza-555555"]
    assert len(session.urls) == 1


@pytest.mark.unit
def test_fetch_segment_retries_block_then_gives_up() -> None:
    scraper = AutocasionES()
    _no_backoff(scraper)
    session = _Session([_Resp(403), _Resp(429), _Resp(503)])
    urls = _run(scraper.fetch_segment(session, {"category": "audi"}, 1))
    assert urls == []
    assert len(session.urls) == scraper.RETRY_ATTEMPTS


@pytest.mark.unit
def test_fetch_segment_recovers_after_block() -> None:
    scraper = AutotrackNL()
    _no_backoff(scraper)
    html = '<a href="/a/ok-100000">ok</a>'
    session = _Session([_Resp(503), _Resp(200, html)])
    urls = _run(scraper.fetch_segment(session, {"brand": "kia"}, 1))
    assert urls == ["https://www.autotrack.nl/a/ok-100000"]
    assert len(session.urls) == 2


@pytest.mark.unit
def test_fetch_segment_retries_softblock_200() -> None:
    scraper = AutocasionES()
    _no_backoff(scraper)
    challenge = "<html><title>Just a moment...</title>checking your browser</html>"
    session = _Session([_Resp(200, challenge)] * 3)
    urls = _run(scraper.fetch_segment(session, {"category": "bmw"}, 1))
    assert urls == []
    assert len(session.urls) == scraper.RETRY_ATTEMPTS


@pytest.mark.unit
def test_fetch_segment_non_block_status_returns_empty_no_retry() -> None:
    scraper = AutotrackNL()
    session = _Session([_Resp(404)])
    urls = _run(scraper.fetch_segment(session, {"brand": "fiat"}, 1))
    assert urls == []
    assert len(session.urls) == 1


@pytest.mark.unit
def test_fetch_segment_retries_transport_error() -> None:
    scraper = AutocasionES()
    _no_backoff(scraper)
    html = '<a href="/coches-segunda-mano/seat/leon-ref7">z</a>'
    session = _Session([ConnectionError("reset"), ConnectionError("reset"), _Resp(200, html)])
    urls = _run(scraper.fetch_segment(session, {"category": "seat"}, 1))
    assert urls == ["https://www.autocasion.com/coches-segunda-mano/seat/leon-ref7"]
    assert len(session.urls) == 3


# --------------------------------------------------------------------------- #
# sitemap → segments
# --------------------------------------------------------------------------- #
_AUTOTRACK_SITEMAP = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://www.autotrack.nl/auto/volkswagen</loc></url>
  <url><loc>https://www.autotrack.nl/auto/volkswagen/golf</loc></url>
  <url><loc>https://www.autotrack.nl/auto/volkswagen/polo</loc></url>
  <url><loc>https://www.autotrack.nl/auto/audi</loc></url>
  <url><loc>https://www.autotrack.nl/auto/audi/a4</loc></url>
  <url><loc>https://www.autotrack.nl/auto/volkswagen</loc></url>
  <url><loc>https://www.autotrack.nl/iets-anders</loc></url>
</urlset>
"""


@pytest.mark.unit
def test_autotrack_sitemap_enumerates_brands_and_builds_model_map() -> None:
    scraper = AutotrackNL()
    segments = _run(scraper.load_segments_from_sitemap(_Session([_Resp(200, _AUTOTRACK_SITEMAP)])))
    # Brand-only locs become segments; duplicate brand + model locs + junk excluded.
    assert segments == [{"brand": "volkswagen"}, {"brand": "audi"}]
    assert scraper.partition_params() == segments
    assert scraper._brand_models == {"volkswagen": ["golf", "polo"], "audi": ["a4"]}


@pytest.mark.unit
def test_autotrack_subdivide_uses_model_map() -> None:
    scraper = AutotrackNL()
    _run(scraper.load_segments_from_sitemap(_Session([_Resp(200, _AUTOTRACK_SITEMAP)])))
    subs = scraper.subdivide_segment({"brand": "volkswagen"})
    assert subs == [
        {"brand": "volkswagen", "model": "golf"},
        {"brand": "volkswagen", "model": "polo"},
    ]
    # A model segment cannot subdivide further; unknown brand → no models.
    assert scraper.subdivide_segment({"brand": "volkswagen", "model": "golf"}) == []
    assert scraper.subdivide_segment({"brand": "ferrari"}) == []


_AUTOCASION_SITEMAP = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://www.autocasion.com/coches-segunda-mano/audi-a3-ocasion</loc></url>
  <url><loc>https://www.autocasion.com/coches-segunda-mano/seat-leon-ocasion</loc></url>
  <url><loc>https://www.autocasion.com/coches-segunda-mano/audi-a3-ocasion</loc></url>
  <url><loc>https://www.autocasion.com/quienes-somos</loc></url>
</urlset>
"""


@pytest.mark.unit
def test_autocasion_sitemap_enumerates_categories_deduped() -> None:
    scraper = AutocasionES()
    segments = _run(scraper.load_segments_from_sitemap(_Session([_Resp(200, _AUTOCASION_SITEMAP)])))
    assert segments == [{"category": "audi-a3"}, {"category": "seat-leon"}]


# --------------------------------------------------------------------------- #
# sitemap index recursion
# --------------------------------------------------------------------------- #
@pytest.mark.unit
def test_sitemap_index_recursion_collects_child_urlset() -> None:
    index = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        "<sitemap><loc>https://www.autotrack.nl/child.xml</loc></sitemap>"
        "</sitemapindex>"
    )
    child = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        "<url><loc>https://www.autotrack.nl/auto/bmw</loc></url>"
        "</urlset>"
    )
    scraper = AutotrackNL()
    session = _Session([_Resp(200, index), _Resp(200, child)])
    segments = _run(scraper.load_segments_from_sitemap(session))
    assert segments == [{"brand": "bmw"}]
    assert session.urls == [
        "https://www.autotrack.nl/sitemap_brand_model_auto.xml",
        "https://www.autotrack.nl/child.xml",
    ]


@pytest.mark.unit
def test_sitemap_fetch_failure_yields_no_segments() -> None:
    scraper = AutocasionES()
    segments = _run(scraper.load_segments_from_sitemap(_Session([_Resp(500)])))
    assert segments == []
    assert scraper.partition_params() == []


# --------------------------------------------------------------------------- #
# run() smoke — seeded pipeline reaches OK with a country-correct identity
# --------------------------------------------------------------------------- #
@pytest.mark.unit
def test_autotrack_run_ok_with_nl_identity(conn) -> None:
    idy = _save_active_identity(conn, "NL", "203.0.113.21", "33333333-3333-3333-3333-333333333333")
    scraper = AutotrackNL(segments=[{"brand": "volkswagen"}])
    scraper.SLEEP_BASE = 0.0
    scraper.SLEEP_JITTER = 0.0
    # One short page (< PAGE_SIZE 30) → segment exhausts after page 1.
    html = '<a href="/a/vw-golf-1234567">a</a><a href="/a/vw-polo-7654321">b</a>'
    received: list[str] = []

    async def sink(urls: list[str]) -> None:
        received.extend(urls)

    result = _run(scraper.run(conn, _Session([_Resp(200, html)]), on_urls=sink))
    assert result.status.value == "ok"
    assert result.identity_id == idy.id
    assert set(received) == {
        "https://www.autotrack.nl/a/vw-golf-1234567",
        "https://www.autotrack.nl/a/vw-polo-7654321",
    }
    assert result.tier == "T1"


@pytest.mark.unit
def test_autocasion_run_ok_with_es_identity(conn) -> None:
    idy = _save_active_identity(conn, "ES", "203.0.113.22", "44444444-4444-4444-4444-444444444444")
    scraper = AutocasionES(segments=[{"category": "audi-a3"}])
    scraper.SLEEP_BASE = 0.0
    scraper.SLEEP_JITTER = 0.0
    html = '<a href="/coches-segunda-mano/audi/a3-ref1">a</a>'
    received: list[str] = []

    async def sink(urls: list[str]) -> None:
        received.extend(urls)

    result = _run(scraper.run(conn, _Session([_Resp(200, html)]), on_urls=sink))
    assert result.status.value == "ok"
    assert result.identity_id == idy.id
    assert received == ["https://www.autocasion.com/coches-segunda-mano/audi/a3-ref1"]
    assert result.tier == "T1"
