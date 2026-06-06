"""
Phase-8 portal scraper tests — pkw.de, autohaus24.de, autohus.de,
buscocoches.com, belgiemobiel.be, vroom.be, carforyou.ch,
occasions.jeanlain.com.

Each portal is exercised against a fake duck-typed session (no curl_cffi):
partition_params grid, subdivide_segment termination, _build_url request
shaping, _extract parsing + dedup, fetch_segment retry / status handling.
Registry and domain_map wiring are also asserted to catch drift.

Coroutines run synchronously via asyncio.run() (engine convention).
fetch_segment tests stub _retry_backoff to no-op so the suite never sleeps.
"""
from __future__ import annotations

import asyncio
from typing import Any

import pytest

from scrapers.engine.router.domain_map import Tier, WAF
from scrapers.engine.router.domain_map import get as domain_get
from scrapers.portals import get_scraper
from scrapers.portals.base import BasePortalScraper


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
    """Stub exponential backoff so retry tests run instantly."""

    async def _noop(attempt: int, factor: float = 1.0) -> None:
        return None

    scraper._retry_backoff = _noop  # type: ignore[method-assign]


# =========================================================================== #
# pkw.de — SSR HTML, German marketplace (T1)
# =========================================================================== #
from scrapers.portals.pkw_de import PkwDEScraper

_PKW_HTML = """
<html><body>
<a href="/gebrauchtwagen/audi-a3-sportback-tfsi-12345">Audi A3</a>
<a href="/autokatalog/bmw/3er/bmw-320d-touring-67890">BMW 320d</a>
<a href="/gebrauchtwagen/vw-golf-tsi-99887">VW Golf</a>
<a href="/autokatalog/bmw/3er/bmw-320d-touring-67890">BMW 320d DUP</a>
</body></html>
"""


class TestPkwDE:
    def test_registry(self) -> None:
        s = get_scraper("pkw.de")
        assert s is not None
        assert isinstance(s, PkwDEScraper)
        assert s.DOMAIN == "pkw.de"
        assert s.COUNTRY == "DE"

    def test_domain_map(self) -> None:
        spec = domain_get("pkw.de")
        assert spec is not None
        assert spec.tier is Tier.T1

    def test_partition_params(self) -> None:
        s = PkwDEScraper()
        params = s.partition_params()
        brands = [p["brand"] for p in params]
        assert "audi" in brands
        assert "bmw" in brands
        assert "volkswagen" in brands
        assert len(params) == len(s.BRANDS)

    def test_build_url_page1(self) -> None:
        s = PkwDEScraper()
        url = s._build_url({"brand": "audi"}, 1)
        assert url == "https://www.pkw.de/autokatalog/audi"

    def test_build_url_page3(self) -> None:
        s = PkwDEScraper()
        url = s._build_url({"brand": "bmw"}, 3)
        assert url == "https://www.pkw.de/autokatalog/bmw?page=3"

    def test_extract_dedup(self) -> None:
        s = PkwDEScraper()
        urls = s._extract(_PKW_HTML)
        assert len(urls) == 3  # deduplicated
        assert any("audi-a3" in u for u in urls)
        assert any("bmw-320d" in u for u in urls)
        assert any("vw-golf" in u for u in urls)

    def test_fetch_segment_200(self) -> None:
        s = PkwDEScraper()
        _no_backoff(s)
        sess = _Session([_Resp(200, _PKW_HTML)])
        urls = _run(s.fetch_segment(sess, {"brand": "audi"}, 1))
        assert len(urls) == 3

    def test_fetch_segment_403_retry(self) -> None:
        s = PkwDEScraper()
        _no_backoff(s)
        sess = _Session([_Resp(403), _Resp(403), _Resp(200, _PKW_HTML)])
        urls = _run(s.fetch_segment(sess, {"brand": "bmw"}, 1))
        assert len(urls) == 3
        assert len(sess.calls) == 3

    def test_fetch_segment_all_fail(self) -> None:
        s = PkwDEScraper()
        _no_backoff(s)
        sess = _Session([_Resp(500), _Resp(500), _Resp(500)])
        urls = _run(s.fetch_segment(sess, {"brand": "audi"}, 1))
        assert urls == []

    def test_fetch_segment_transport_error(self) -> None:
        s = PkwDEScraper()
        _no_backoff(s)
        sess = _Session([ConnectionError("timeout"), _Resp(200, _PKW_HTML)])
        urls = _run(s.fetch_segment(sess, {"brand": "audi"}, 1))
        assert len(urls) == 3


# =========================================================================== #
# autohaus24.de — SSR HTML, German dealer platform (T1)
# =========================================================================== #
from scrapers.portals.autohaus24_de import Autohaus24DEScraper

_AH24_HTML = """
<html><body>
<a href="/gebrauchtwagen/audi-a4-avant-muenchen-54321">Audi A4</a>
<a href="/gebrauchtwagen/bmw-x3-berlin-98765">BMW X3</a>
<a href="/gebrauchtwagen/">Index page</a>
</body></html>
"""


class TestAutohaus24DE:
    def test_registry(self) -> None:
        s = get_scraper("autohaus24.de")
        assert s is not None
        assert isinstance(s, Autohaus24DEScraper)

    def test_domain_map(self) -> None:
        spec = domain_get("autohaus24.de")
        assert spec is not None
        assert spec.tier is Tier.T1

    def test_partition_params(self) -> None:
        s = Autohaus24DEScraper()
        params = s.partition_params()
        assert len(params) == len(s.BRANDS)
        assert all("brand" in p for p in params)

    def test_build_url(self) -> None:
        s = Autohaus24DEScraper()
        url = s._build_url({"brand": "audi"}, 1)
        assert "brand=audi" in url
        assert "page=" not in url
        url2 = s._build_url({"brand": "audi"}, 2)
        assert "page=2" in url2

    def test_extract_skips_index(self) -> None:
        s = Autohaus24DEScraper()
        urls = s._extract(_AH24_HTML)
        assert len(urls) == 2  # skips /gebrauchtwagen/ index
        assert not any(u.endswith("/gebrauchtwagen/") for u in urls)

    def test_fetch_segment_200(self) -> None:
        s = Autohaus24DEScraper()
        _no_backoff(s)
        sess = _Session([_Resp(200, _AH24_HTML)])
        urls = _run(s.fetch_segment(sess, {"brand": "audi"}, 1))
        assert len(urls) == 2


# =========================================================================== #
# autohus.de — SSR HTML, large German dealer (T1)
# =========================================================================== #
from scrapers.portals.autohus_de import AutohusDEScraper

_AUTOHUS_HTML = """
<html><body>
<a href="/de/fahrzeug/vw-golf-8-tsi-bremen-123456">VW Golf 8</a>
<a href="/de/fahrzeug/bmw-520d-touring-bockel-234567">BMW 520d</a>
<a href="/de/fahrzeugsuche/audi-a4-verden-345678">Audi A4</a>
</body></html>
"""


class TestAutohusDE:
    def test_registry(self) -> None:
        s = get_scraper("autohus.de")
        assert s is not None
        assert isinstance(s, AutohusDEScraper)

    def test_domain_map(self) -> None:
        spec = domain_get("autohus.de")
        assert spec is not None
        assert spec.tier is Tier.T1

    def test_partition_params(self) -> None:
        s = AutohusDEScraper()
        params = s.partition_params()
        assert len(params) == len(s.PRICE_BANDS)
        assert all("price_min" in p for p in params)

    def test_subdivide_segment(self) -> None:
        s = AutohusDEScraper()
        subs = s.subdivide_segment({"price_min": 0, "price_max": 5000})
        assert len(subs) == 4
        # Open-ended segment should not subdivide
        subs_open = s.subdivide_segment({"price_min": 50000, "price_max": None})
        assert subs_open == []

    def test_build_url(self) -> None:
        s = AutohusDEScraper()
        url = s._build_url({"price_min": 5000, "price_max": 10000}, 1)
        assert "price_from=5000" in url
        assert "price_to=10000" in url
        url2 = s._build_url({"price_min": 5000, "price_max": 10000}, 3)
        assert "page=3" in url2

    def test_extract(self) -> None:
        s = AutohusDEScraper()
        urls = s._extract(_AUTOHUS_HTML)
        assert len(urls) == 3
        assert any("vw-golf" in u for u in urls)

    def test_fetch_segment_200(self) -> None:
        s = AutohusDEScraper()
        _no_backoff(s)
        sess = _Session([_Resp(200, _AUTOHUS_HTML)])
        urls = _run(s.fetch_segment(sess, {"price_min": 0, "price_max": 5000}, 1))
        assert len(urls) == 3


# =========================================================================== #
# buscocoches.com — SSR HTML, Spanish classifieds (T1)
# =========================================================================== #
from scrapers.portals.buscocoches_com import BuscocochesESScraper

_BUSCO_HTML = """
<html><body>
<a href="/coche-segunda-mano/audi-a3-sportback-madrid-111222.html">Audi A3</a>
<a href="/vehiculo/seat-leon-fr-barcelona-333444.html">Seat León</a>
<a href="/bmw-de-segunda-mano.html">BMW Category</a>
</body></html>
"""


class TestBuscocochesES:
    def test_registry(self) -> None:
        s = get_scraper("buscocoches.com")
        assert s is not None
        assert isinstance(s, BuscocochesESScraper)

    def test_domain_map(self) -> None:
        spec = domain_get("buscocoches.com")
        assert spec is not None
        assert spec.tier is Tier.T1

    def test_partition_params(self) -> None:
        s = BuscocochesESScraper()
        params = s.partition_params()
        brands = [p["brand"] for p in params]
        assert "seat" in brands
        assert "volkswagen" in brands

    def test_build_url(self) -> None:
        s = BuscocochesESScraper()
        url = s._build_url({"brand": "audi"}, 1)
        assert url == "https://www.buscocoches.com/audi-de-segunda-mano.html"
        url2 = s._build_url({"brand": "audi"}, 2)
        assert "pagina=2" in url2

    def test_extract(self) -> None:
        s = BuscocochesESScraper()
        urls = s._extract(_BUSCO_HTML)
        assert len(urls) == 2  # skips category page
        assert not any("segunda-mano.html" == u.split("/")[-1] for u in urls)

    def test_fetch_segment_200(self) -> None:
        s = BuscocochesESScraper()
        _no_backoff(s)
        sess = _Session([_Resp(200, _BUSCO_HTML)])
        urls = _run(s.fetch_segment(sess, {"brand": "audi"}, 1))
        assert len(urls) == 2


# =========================================================================== #
# belgiemobiel.be — PHP SSR, Belgian classifieds (T1)
# =========================================================================== #
from scrapers.portals.belgiemobiel_be import BelgieMobielBEScraper

_BMBE_HTML = """
<html><body>
<a href="/tweedehands-auto/volkswagen/vw-golf-tsi-brussel/12345678">VW Golf</a>
<a href="/tweedehands-auto/audi/audi-a4-avant-antwerpen/23456789">Audi A4</a>
<a href="/tweedehands-auto/volkswagen/vw-golf-tsi-brussel/12345678">VW Golf DUP</a>
</body></html>
"""


class TestBelgieMobielBE:
    def test_registry(self) -> None:
        s = get_scraper("belgiemobiel.be")
        assert s is not None
        assert isinstance(s, BelgieMobielBEScraper)

    def test_domain_map(self) -> None:
        spec = domain_get("belgiemobiel.be")
        assert spec is not None
        assert spec.tier is Tier.T1

    def test_partition_params(self) -> None:
        s = BelgieMobielBEScraper()
        params = s.partition_params()
        assert len(params) == len(s.BRAND_IDS)
        assert all("brand_id" in p and "brand_slug" in p for p in params)

    def test_build_url(self) -> None:
        s = BelgieMobielBEScraper()
        url = s._build_url({"brand_id": 29, "brand_slug": "bmw"}, 1)
        assert "/auto-occasions/29/bmw" in url
        assert "merk[]=29" in url
        url2 = s._build_url({"brand_id": 29, "brand_slug": "bmw"}, 3)
        assert "pagina=3" in url2

    def test_extract_dedup(self) -> None:
        s = BelgieMobielBEScraper()
        urls = s._extract(_BMBE_HTML)
        assert len(urls) == 2  # deduplicated

    def test_fetch_segment_200(self) -> None:
        s = BelgieMobielBEScraper()
        _no_backoff(s)
        sess = _Session([_Resp(200, _BMBE_HTML)])
        urls = _run(s.fetch_segment(sess, {"brand_id": 29, "brand_slug": "bmw"}, 1))
        assert len(urls) == 2


# =========================================================================== #
# vroom.be — SSR HTML, Belgian mobility platform (T1)
# =========================================================================== #
from scrapers.portals.sitemap_listing_base import SitemapListingScraper
from scrapers.portals.vroom_be import VroomBEScraper


class TestVroomBE:
    """vroom.be migrated to the FR listing sitemap (multi-strategy 2026-06)."""

    def test_registry(self) -> None:
        s = get_scraper("vroom.be")
        assert isinstance(s, VroomBEScraper)
        assert isinstance(s, SitemapListingScraper)

    def test_domain_map(self) -> None:
        assert domain_get("vroom.be").tier is Tier.T1

    def test_sitemap_config(self) -> None:
        s = VroomBEScraper()
        assert s.SITEMAP_URL == "https://www.vroom.be/sitemap_index.xml"
        assert s.CHILD_RE.search("/sitemaps/listings-fr-0001.xml")
        assert not s.CHILD_RE.search("/sitemaps/listings-nl-0001.xml")  # FR only
        assert not s.CHILD_RE.search("/sitemaps/media-0001.xml")
        assert s.DETAIL_RE.search("/fr/voitures-occasion/volkswagen-t-cross-2817040372")
        s._validate()


# =========================================================================== #
# carforyou.ch — SSR HTML, Swiss marketplace (T1)
# =========================================================================== #
from scrapers.portals.carforyou_ch import CarForYouCHScraper

_CFY_HTML = """
<html><body>
<a href="/de/auto/audi/a4/audi-a4-avant-2020-zurich-556677">Audi A4</a>
<a href="/de/auto/bmw/3er/bmw-320d-touring-bern-889900">BMW 320d</a>
<a href="/de/fahrzeug/vw-golf-8-tsi-luzern-1122334">VW Golf</a>
</body></html>
"""


class TestCarForYouCH:
    def test_registry(self) -> None:
        s = get_scraper("carforyou.ch")
        assert s is not None
        assert isinstance(s, CarForYouCHScraper)

    def test_domain_map(self) -> None:
        spec = domain_get("carforyou.ch")
        assert spec is not None
        assert spec.tier is Tier.T1

    def test_partition_params(self) -> None:
        s = CarForYouCHScraper()
        params = s.partition_params()
        assert len(params) == len(s.BRANDS)

    def test_build_url(self) -> None:
        s = CarForYouCHScraper()
        url = s._build_url({"brand": "audi"}, 1)
        assert "/de/auto/audi" in url
        url2 = s._build_url({"brand": "bmw"}, 5)
        assert "page=5" in url2

    def test_extract(self) -> None:
        s = CarForYouCHScraper()
        urls = s._extract(_CFY_HTML)
        assert len(urls) >= 2
        assert any("audi-a4" in u for u in urls)

    def test_fetch_segment_200(self) -> None:
        s = CarForYouCHScraper()
        _no_backoff(s)
        sess = _Session([_Resp(200, _CFY_HTML)])
        urls = _run(s.fetch_segment(sess, {"brand": "audi"}, 1))
        assert len(urls) >= 2


# =========================================================================== #
# occasions.jeanlain.com — SSR HTML, French dealer chain (T1)
# =========================================================================== #
from scrapers.portals.jeanlain_fr import JeanLainFRScraper


class TestJeanLainFR:
    """occasions.jeanlain.com migrated to the vehicle sitemap (multi-strategy 2026-06)."""

    def test_registry(self) -> None:
        s = get_scraper("occasions.jeanlain.com")
        assert isinstance(s, JeanLainFRScraper)
        assert isinstance(s, SitemapListingScraper)

    def test_domain_map(self) -> None:
        assert domain_get("occasions.jeanlain.com").tier is Tier.T1

    def test_sitemap_config(self) -> None:
        s = JeanLainFRScraper()
        assert s.SITEMAP_URL == "https://occasions.jeanlain.com/sitemap.xml"
        assert s.CHILD_RE.search("/vehicle-sitemap.xml")
        assert s.DETAIL_RE.search("/voiture/volkswagen/modele-t-roc/t-roc-398113")
        s._validate()


# =========================================================================== #
# Cross-portal: registry completeness + domain_map wiring
# =========================================================================== #
class TestPhase8RegistryCompleteness:
    """Verify every Phase 8 scraper is in the portal registry and domain_map."""

    _PHASE8_DOMAINS: tuple[str, ...] = (
        "pkw.de", "autohaus24.de", "autohus.de", "buscocoches.com",
        "belgiemobiel.be", "vroom.be", "carforyou.ch", "occasions.jeanlain.com",
    )

    def test_all_in_registry(self) -> None:
        for domain in self._PHASE8_DOMAINS:
            s = get_scraper(domain)
            assert s is not None, f"{domain} not in portal registry"
            assert s.DOMAIN == domain

    def test_all_in_domain_map(self) -> None:
        for domain in self._PHASE8_DOMAINS:
            spec = domain_get(domain)
            assert spec is not None, f"{domain} not in domain_map"
            assert spec.tier is Tier.T1

    def test_all_have_country(self) -> None:
        for domain in self._PHASE8_DOMAINS:
            s = get_scraper(domain)
            assert s is not None
            assert s.COUNTRY in ("DE", "FR", "ES", "NL", "BE", "CH")
