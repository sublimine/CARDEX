"""
SitemapListingScraper tests — the shared listing-sitemap discovery base plus the
config of every portal migrated onto it (Phase: multi-strategy 2026-06).

Three layers, mirroring test_t1_portals.py:
  * base mechanics: index recursion, CHILD_RE / DETAIL_RE filtering, dedup, gzip
    decode, multi-entry SITEMAP_URLS, retry, _validate;
  * caravenue internal-API _extract (the one API switch in this batch);
  * config + registry resolution for all migrated portals, and a run() smoke proving
    the seeded pipeline reaches OK with a country-correct identity.
"""
from __future__ import annotations

import asyncio
import gzip
import re
from typing import Any

import pytest

from scrapers.engine.identity import profile, store
from scrapers.engine.identity.profile import IdentityStatus, ProxyTier
from scrapers.portals import get_scraper
from scrapers.portals.caravenue_com import CaravenueFRScraper
from scrapers.portals.marktplaats_nl import MarktplaatsNLScraper
from scrapers.portals.sitemap_listing_base import SitemapListingScraper


def _run(coro: Any) -> Any:
    return asyncio.run(coro)


# --------------------------------------------------------------------------- #
# fakes
# --------------------------------------------------------------------------- #
class _Resp:
    """Duck-typed response: .status_code, .text, optional .content (bytes)."""

    def __init__(self, status_code: int, text: str = "", content: bytes | None = None) -> None:
        self.status_code = status_code
        self.text = text
        self.content = content


class _MapSession:
    """Fake AsyncSession resolving each GET against a {url: response} map."""

    def __init__(self, mapping: dict[str, Any]) -> None:
        self._mapping = mapping
        self.urls: list[str] = []

    async def get(self, url: str, timeout: int | None = None) -> _Resp:
        self.urls.append(url)
        item = self._mapping.get(url)
        if item is None:
            return _Resp(404)
        if isinstance(item, Exception):
            raise item
        return item


def _urlset(*locs: str) -> str:
    body = "".join(f"<url><loc>{loc}</loc></url>" for loc in locs)
    return f'<?xml version="1.0"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{body}</urlset>'


def _index(*locs: str) -> str:
    body = "".join(f"<sitemap><loc>{loc}</loc></sitemap>" for loc in locs)
    return f'<?xml version="1.0"?><sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{body}</sitemapindex>'


def _no_delay(scraper: SitemapListingScraper) -> None:
    scraper.SITEMAP_FETCH_DELAY = 0.0
    scraper.SITEMAP_FETCH_JITTER = 0.0


# --------------------------------------------------------------------------- #
# a minimal concrete scraper for base mechanics
# --------------------------------------------------------------------------- #
class _Demo(SitemapListingScraper):
    DOMAIN = "demo.test"
    COUNTRY = "NL"
    SITEMAP_URL = "https://demo.test/sitemap.xml"
    CHILD_RE = re.compile(r"/cars\.")            # only car children
    DETAIL_RE = re.compile(r"/v/")               # only /v/ detail URLs


def _demo() -> _Demo:
    s = _Demo()
    _no_delay(s)
    return s


# --------------------------------------------------------------------------- #
# base: index recursion + CHILD_RE/DETAIL_RE filtering + dedup
# --------------------------------------------------------------------------- #
@pytest.mark.unit
def test_harvest_walks_index_filters_children_and_details() -> None:
    mapping = {
        "https://demo.test/sitemap.xml": _Resp(200, _index(
            "https://demo.test/cars.1.xml",
            "https://demo.test/boats.1.xml",   # excluded by CHILD_RE
        )),
        "https://demo.test/cars.1.xml": _Resp(200, _urlset(
            "https://demo.test/v/audi-a3-1",
            "https://demo.test/category/audi",   # excluded by DETAIL_RE
            "https://demo.test/v/audi-a3-1",     # dup
            "https://demo.test/v/bmw-x1-2",
        )),
        "https://demo.test/boats.1.xml": _Resp(200, _urlset("https://demo.test/v/should-not-fetch")),
    }
    session = _MapSession(mapping)
    urls = _run(_demo().fetch_segment(session, {}, 1))
    assert urls == ["https://demo.test/v/audi-a3-1", "https://demo.test/v/bmw-x1-2"]
    # boats child was filtered out before fetching
    assert "https://demo.test/boats.1.xml" not in session.urls


@pytest.mark.unit
def test_harvest_second_page_is_empty() -> None:
    session = _MapSession({"https://demo.test/sitemap.xml": _Resp(200, _urlset("https://demo.test/v/x-1"))})
    assert _run(_demo().fetch_segment(session, {}, 2)) == []
    assert session.urls == []  # no fetch at all on page 2


@pytest.mark.unit
def test_harvest_unescapes_entities() -> None:
    session = _MapSession({
        "https://demo.test/sitemap.xml": _Resp(200, _urlset("https://demo.test/v/a?x=1&amp;y=2")),
    })
    urls = _run(_demo().fetch_segment(session, {}, 1))
    assert urls == ["https://demo.test/v/a?x=1&y=2"]


@pytest.mark.unit
def test_harvest_decodes_gzip_child_by_magic_bytes() -> None:
    gz = gzip.compress(_urlset("https://demo.test/v/skoda-1").encode("utf-8"))
    mapping = {
        "https://demo.test/sitemap.xml": _Resp(200, _index("https://demo.test/cars.1.xml.gz")),
        "https://demo.test/cars.1.xml.gz": _Resp(200, text="", content=gz),
    }
    urls = _run(_demo().fetch_segment(_MapSession(mapping), {}, 1))
    assert urls == ["https://demo.test/v/skoda-1"]


@pytest.mark.unit
def test_harvest_multi_entry_sitemaps() -> None:
    class _Multi(_Demo):
        SITEMAP_URL = ""
        SITEMAP_URLS = ("https://demo.test/100.xml", "https://demo.test/101.xml")
        CHILD_RE = None  # urlsets directly

    s = _Multi()
    _no_delay(s)
    mapping = {
        "https://demo.test/100.xml": _Resp(200, _urlset("https://demo.test/v/a-1")),
        "https://demo.test/101.xml": _Resp(200, _urlset("https://demo.test/v/b-2")),
    }
    urls = _run(s.fetch_segment(_MapSession(mapping), {}, 1))
    assert urls == ["https://demo.test/v/a-1", "https://demo.test/v/b-2"]


@pytest.mark.unit
def test_harvest_skips_revisited_sitemap_url() -> None:
    # A child that points back to the index must not loop forever.
    mapping = {
        "https://demo.test/sitemap.xml": _Resp(200, _index("https://demo.test/cars.1.xml")),
        "https://demo.test/cars.1.xml": _Resp(200, _index("https://demo.test/sitemap.xml")),
    }
    session = _MapSession(mapping)
    assert _run(_demo().fetch_segment(session, {}, 1)) == []
    assert session.urls.count("https://demo.test/sitemap.xml") == 1


@pytest.mark.unit
def test_harvest_non_200_child_is_skipped_not_fatal() -> None:
    mapping = {
        "https://demo.test/sitemap.xml": _Resp(200, _index(
            "https://demo.test/cars.1.xml", "https://demo.test/cars.2.xml",
        )),
        "https://demo.test/cars.1.xml": _Resp(404),
        "https://demo.test/cars.2.xml": _Resp(200, _urlset("https://demo.test/v/ok-1")),
    }
    urls = _run(_demo().fetch_segment(_MapSession(mapping), {}, 1))
    assert urls == ["https://demo.test/v/ok-1"]


@pytest.mark.unit
def test_validate_requires_sitemap_and_detail() -> None:
    class _Broken(SitemapListingScraper):
        DOMAIN = "x.test"
        COUNTRY = "NL"
        # SITEMAP_URL / DETAIL_RE unset

    with pytest.raises(ValueError):
        _Broken()._validate()


# --------------------------------------------------------------------------- #
# caravenue — internal API _extract
# --------------------------------------------------------------------------- #
@pytest.mark.unit
def test_caravenue_extract_pulls_vehicle_slugs() -> None:
    body = (
        '{"data":{"formatedResponse":{"content":['
        '{"componentType":"params","props":{}},'
        '{"componentType":"EventCards","props":[]},'
        '{"componentType":"Vehicules","props":['
        '{"slug":"kia-stonic-kmu306090"},'
        '{"slug":"audi-a3-xyz"},'
        '{"slug":"kia-stonic-kmu306090"},'   # dup
        '{"name":"no-slug"}]}'
        '],"pagination":{"totalPages":101}}}}'
    )
    urls = CaravenueFRScraper()._extract(body)
    assert urls == [
        "https://www.caravenue.com/fr/voiture-occasion/kia-stonic-kmu306090",
        "https://www.caravenue.com/fr/voiture-occasion/audi-a3-xyz",
    ]


@pytest.mark.unit
def test_caravenue_extract_handles_missing_vehicles_block() -> None:
    assert CaravenueFRScraper()._extract('{"data":{"formatedResponse":{"content":[]}}}') == []
    assert CaravenueFRScraper()._extract("not json") == []


# --------------------------------------------------------------------------- #
# config + registry resolution for every migrated portal
# --------------------------------------------------------------------------- #
_MIGRATED: tuple[tuple[str, str], ...] = (
    ("marktplaats.nl", "NL"),
    ("2dehands.be", "BE"),
    ("2ememain.be", "BE"),
    ("autokopen.nl", "NL"),
    ("cardoen.be", "BE"),
    ("vroom.be", "BE"),
    ("gowago.ch", "CH"),
    ("aramisauto.com", "FR"),
    ("annonces-automobile.com", "FR"),
    ("carizy.com", "FR"),
    ("capcar.fr", "FR"),
    ("occasions.jeanlain.com", "FR"),
    ("gueudet.fr", "FR"),
    ("distinxion.fr", "FR"),
    ("ocasionplus.com", "ES"),
    ("autoboerse.de", "DE"),
    ("truckscout24.com", "DE"),
    ("classic-trader.com", "DE"),
    ("simplicicar.com", "FR"),
)


@pytest.mark.unit
@pytest.mark.parametrize("domain, country", _MIGRATED)
def test_migrated_sitemap_scraper_config(domain: str, country: str) -> None:
    scraper = get_scraper(domain)
    assert isinstance(scraper, SitemapListingScraper)
    assert scraper.DOMAIN == domain
    assert scraper.COUNTRY == country
    assert scraper.DETAIL_RE is not None
    assert scraper._entry_sitemaps() and all(u.startswith("https://") for u in scraper._entry_sitemaps())
    scraper._validate()  # must not raise


@pytest.mark.unit
def test_caravenue_registry_and_config() -> None:
    scraper = get_scraper("caravenue.com")
    assert isinstance(scraper, CaravenueFRScraper)
    assert scraper.DOMAIN == "caravenue.com"
    assert scraper.COUNTRY == "FR"


# --------------------------------------------------------------------------- #
# run() smoke — seeded pipeline reaches OK with a country-correct identity
# --------------------------------------------------------------------------- #
def _save_active_identity(conn, country: str, ip: str, uuid: str):
    idy = profile.generate(country, ip, ProxyTier.ISP_STICKY, identity_id=uuid)
    store.save(conn, idy)
    conn.execute(
        "UPDATE identities SET status=?, warming_done=1, trust_score=1.0 WHERE id=?",
        (IdentityStatus.ACTIVE.value, idy.id),
    )
    return store.get(conn, idy.id)


@pytest.mark.unit
def test_marktplaats_run_ok_harvests_sitemap(conn) -> None:
    idy = _save_active_identity(conn, "NL", "203.0.113.31", "55555555-5555-5555-5555-555555555555")
    scraper = MarktplaatsNLScraper()
    _no_delay(scraper)
    scraper.SLEEP_BASE = 0.0
    scraper.SLEEP_JITTER = 0.0
    mapping = {
        "https://www.marktplaats.nl/sitemap/sitemap.xml": _Resp(200, _index(
            "https://www.marktplaats.nl/sitemap/l2.auto-s.bmw.1.sitemap.xml.gz",
            "https://www.marktplaats.nl/sitemap/admarkt_l2.auto-s.bmw.1.sitemap.xml.gz",  # excluded
        )),
        "https://www.marktplaats.nl/sitemap/l2.auto-s.bmw.1.sitemap.xml.gz": _Resp(
            200, text="", content=gzip.compress(_urlset(
                "https://www.marktplaats.nl/v/auto-s/bmw/m1-bmw-1",
                "https://www.marktplaats.nl/v/auto-s/bmw/m2-bmw-2",
            ).encode("utf-8")),
        ),
    }
    received: list[str] = []

    async def sink(urls: list[str]) -> None:
        received.extend(urls)

    result = _run(scraper.run(conn, _MapSession(mapping), on_urls=sink))
    assert result.status.value == "ok"
    assert result.identity_id == idy.id
    assert result.tier == "T0"
    assert set(received) == {
        "https://www.marktplaats.nl/v/auto-s/bmw/m1-bmw-1",
        "https://www.marktplaats.nl/v/auto-s/bmw/m2-bmw-2",
    }
