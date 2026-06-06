"""
Phase-7 portal scraper tests — flexicar.es, clicars.com, autowereld.nl,
auto.de, youcar.be, myway.be, capcar.fr.

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
# flexicar.es — SSR HTML, Spanish dealer chain (T1)
# =========================================================================== #
from scrapers.portals.flexicar_es import FlexicarESScraper

_FLEXICAR_HTML = """
<html><body>
<a href="/coches-segunda-mano/volkswagen-golf-tsi-madrid-12345">VW Golf</a>
<a href="/coches-segunda-mano/seat-leon-fr-barcelona-67890">Seat León</a>
<a href="/coches-segunda-mano/volkswagen-golf-tsi-madrid-12345">VW Golf dup</a>
<a href="/coches-segunda-mano/toyota-corolla-valencia-11111">Toyota Corolla</a>
<a href="/coches-segunda-mano/">Search page link</a>
</body></html>
"""

_FLEXICAR_EXPECTED = [
    "https://www.flexicar.es/coches-segunda-mano/volkswagen-golf-tsi-madrid-12345",
    "https://www.flexicar.es/coches-segunda-mano/seat-leon-fr-barcelona-67890",
    "https://www.flexicar.es/coches-segunda-mano/toyota-corolla-valencia-11111",
]


@pytest.mark.unit
def test_flexicar_partition_is_single_segment() -> None:
    scraper = FlexicarESScraper()
    segments = scraper.partition_params()
    assert len(segments) == 1
    assert segments[0] == {}


@pytest.mark.unit
def test_flexicar_domain_and_country() -> None:
    scraper = FlexicarESScraper()
    assert scraper.DOMAIN == "flexicar.es"
    assert scraper.COUNTRY == "ES"


@pytest.mark.unit
def test_flexicar_build_url_page1() -> None:
    scraper = FlexicarESScraper()
    url = scraper._build_url({}, 1)
    assert url == "https://www.flexicar.es/coches-segunda-mano/"


@pytest.mark.unit
def test_flexicar_build_url_page5() -> None:
    scraper = FlexicarESScraper()
    url = scraper._build_url({}, 5)
    assert url == "https://www.flexicar.es/coches-segunda-mano/?pagina=5"


@pytest.mark.unit
def test_flexicar_extract_dedup() -> None:
    scraper = FlexicarESScraper()
    urls = scraper._extract(_FLEXICAR_HTML)
    assert urls == _FLEXICAR_EXPECTED


@pytest.mark.unit
def test_flexicar_fetch_200() -> None:
    scraper = FlexicarESScraper()
    _no_backoff(scraper)
    session = _Session([_Resp(200, _FLEXICAR_HTML)])
    urls = _run(scraper.fetch_segment(session, {}, 1))
    assert urls == _FLEXICAR_EXPECTED


@pytest.mark.unit
def test_flexicar_fetch_retry_then_ok() -> None:
    scraper = FlexicarESScraper()
    _no_backoff(scraper)
    session = _Session([_Resp(429), _Resp(200, _FLEXICAR_HTML)])
    urls = _run(scraper.fetch_segment(session, {}, 1))
    assert urls == _FLEXICAR_EXPECTED
    assert len(session.calls) == 2


@pytest.mark.unit
def test_flexicar_fetch_all_retries_exhausted() -> None:
    scraper = FlexicarESScraper()
    _no_backoff(scraper)
    session = _Session([_Resp(503)] * 3)
    urls = _run(scraper.fetch_segment(session, {}, 1))
    assert urls == []


@pytest.mark.unit
def test_flexicar_registry() -> None:
    scraper = get_scraper("flexicar.es")
    assert scraper is not None
    assert isinstance(scraper, FlexicarESScraper)


@pytest.mark.unit
def test_flexicar_domain_map() -> None:
    spec = domain_get("flexicar.es")
    assert spec is not None
    assert spec.tier == Tier.T1
    assert "ES" in spec.countries


# =========================================================================== #
# clicars.com — SSR HTML, Spanish online dealer (T1)
# =========================================================================== #
from scrapers.portals.clicars_com import ClicarsESScraper

_CLICARS_HTML = """
<html><body>
<a href="/coches-segunda-mano-ocasion/audi/audi-a3-sportback-tfsi-madrid-abc123">Audi A3</a>
<a href="/coches-segunda-mano-ocasion/bmw/bmw-serie3-320d-zaragoza-def456">BMW 320d</a>
<a href="/coches-segunda-mano-ocasion/audi/audi-a3-sportback-tfsi-madrid-abc123">Audi A3 dup</a>
<a href="/coches-segunda-mano-ocasion/madrid">Madrid filter link</a>
</body></html>
"""

_CLICARS_EXPECTED = [
    "https://www.clicars.com/coches-segunda-mano-ocasion/audi/audi-a3-sportback-tfsi-madrid-abc123",
    "https://www.clicars.com/coches-segunda-mano-ocasion/bmw/bmw-serie3-320d-zaragoza-def456",
]


@pytest.mark.unit
def test_clicars_partition_by_brand() -> None:
    scraper = ClicarsESScraper()
    segments = scraper.partition_params()
    assert len(segments) > 30  # at least 30 brands
    assert all("brand" in s for s in segments)


@pytest.mark.unit
def test_clicars_domain_and_country() -> None:
    scraper = ClicarsESScraper()
    assert scraper.DOMAIN == "clicars.com"
    assert scraper.COUNTRY == "ES"


@pytest.mark.unit
def test_clicars_build_url_brand_page1() -> None:
    scraper = ClicarsESScraper()
    url = scraper._build_url({"brand": "audi"}, 1)
    assert url == "https://www.clicars.com/coches-segunda-mano-ocasion/audi"


@pytest.mark.unit
def test_clicars_build_url_brand_page3() -> None:
    scraper = ClicarsESScraper()
    url = scraper._build_url({"brand": "bmw"}, 3)
    assert url == "https://www.clicars.com/coches-segunda-mano-ocasion/bmw?page=3"


@pytest.mark.unit
def test_clicars_extract_dedup() -> None:
    scraper = ClicarsESScraper()
    urls = scraper._extract(_CLICARS_HTML)
    assert urls == _CLICARS_EXPECTED


@pytest.mark.unit
def test_clicars_fetch_200() -> None:
    scraper = ClicarsESScraper()
    _no_backoff(scraper)
    session = _Session([_Resp(200, _CLICARS_HTML)])
    urls = _run(scraper.fetch_segment(session, {"brand": "audi"}, 1))
    assert urls == _CLICARS_EXPECTED


@pytest.mark.unit
def test_clicars_registry() -> None:
    scraper = get_scraper("clicars.com")
    assert scraper is not None
    assert isinstance(scraper, ClicarsESScraper)


@pytest.mark.unit
def test_clicars_domain_map() -> None:
    spec = domain_get("clicars.com")
    assert spec is not None
    assert spec.tier == Tier.T1
    assert "ES" in spec.countries


# =========================================================================== #
# autowereld.nl — PHP SSR, Dutch classifieds (T1)
# =========================================================================== #
from scrapers.portals.autowereld_nl import AutowereldNLScraper

_AUTOWERELD_HTML = """
<html><body>
<a href="/audi/audi-a4-avant-2-0-tdi-pro-line-123456.html">Audi A4 Avant</a>
<a href="/volkswagen/volkswagen-golf-8-1-5-tsi-style-789012.html">VW Golf 8</a>
<a href="/audi/audi-a4-avant-2-0-tdi-pro-line-123456.html">Audi A4 dup</a>
<a href="/fiat/">Brand filter link</a>
</body></html>
"""

_AUTOWERELD_EXPECTED = [
    "https://www.autowereld.nl/audi/audi-a4-avant-2-0-tdi-pro-line-123456.html",
    "https://www.autowereld.nl/volkswagen/volkswagen-golf-8-1-5-tsi-style-789012.html",
]


@pytest.mark.unit
def test_autowereld_partition_by_brand() -> None:
    scraper = AutowereldNLScraper()
    segments = scraper.partition_params()
    assert len(segments) > 30
    assert all("brand" in s for s in segments)


@pytest.mark.unit
def test_autowereld_domain_and_country() -> None:
    scraper = AutowereldNLScraper()
    assert scraper.DOMAIN == "autowereld.nl"
    assert scraper.COUNTRY == "NL"


@pytest.mark.unit
def test_autowereld_build_url_brand_page1() -> None:
    scraper = AutowereldNLScraper()
    url = scraper._build_url({"brand": "audi"}, 1)
    assert url == "https://www.autowereld.nl/audi/"


@pytest.mark.unit
def test_autowereld_build_url_brand_page2() -> None:
    scraper = AutowereldNLScraper()
    url = scraper._build_url({"brand": "audi"}, 2)
    assert url == "https://www.autowereld.nl/audi/?pagina=2"


@pytest.mark.unit
def test_autowereld_build_url_with_price_band() -> None:
    scraper = AutowereldNLScraper()
    url = scraper._build_url({"brand": "audi", "prijs_van": 10000, "prijs_tot": 15000, "_fine": True}, 1)
    assert "prijs_van=10000" in url
    assert "prijs_tot=15000" in url


@pytest.mark.unit
def test_autowereld_subdivide_creates_price_bands() -> None:
    scraper = AutowereldNLScraper()
    subs = scraper.subdivide_segment({"brand": "volkswagen"})
    assert len(subs) == 8  # 8 price bands
    assert all(s["brand"] == "volkswagen" for s in subs)
    assert all(s["_fine"] is True for s in subs)


@pytest.mark.unit
def test_autowereld_subdivide_fine_is_terminal() -> None:
    scraper = AutowereldNLScraper()
    subs = scraper.subdivide_segment({"brand": "volkswagen", "_fine": True})
    assert subs == []


@pytest.mark.unit
def test_autowereld_extract_dedup() -> None:
    scraper = AutowereldNLScraper()
    urls = scraper._extract(_AUTOWERELD_HTML)
    assert urls == _AUTOWERELD_EXPECTED


@pytest.mark.unit
def test_autowereld_fetch_200() -> None:
    scraper = AutowereldNLScraper()
    _no_backoff(scraper)
    session = _Session([_Resp(200, _AUTOWERELD_HTML)])
    urls = _run(scraper.fetch_segment(session, {"brand": "audi"}, 1))
    assert urls == _AUTOWERELD_EXPECTED


@pytest.mark.unit
def test_autowereld_registry() -> None:
    scraper = get_scraper("autowereld.nl")
    assert scraper is not None
    assert isinstance(scraper, AutowereldNLScraper)


@pytest.mark.unit
def test_autowereld_domain_map() -> None:
    spec = domain_get("autowereld.nl")
    assert spec is not None
    assert spec.tier == Tier.T1
    assert "NL" in spec.countries


# =========================================================================== #
# auto.de — WordPress, German dealer portal (T1)
# =========================================================================== #
from scrapers.portals.auto_de import AutoDEScraper

_AUTO_DE_HTML = """
<html><body>
<a href="/search/vehicle/a1b2c3d4-e5f6-7890-abcd-ef1234567890">BMW 3er</a>
<a href="/search/vehicle/11223344-5566-7788-99aa-bbccddeeff00">Audi A4</a>
<a href="/search/vehicle/a1b2c3d4-e5f6-7890-abcd-ef1234567890">BMW 3er dup</a>
<a href="/gebrauchtwagen/volkswagen/volkswagen-golf-gte-abc123">VW Golf GTE</a>
</body></html>
"""

_AUTO_DE_EXPECTED = [
    "https://www.auto.de/search/vehicle/a1b2c3d4-e5f6-7890-abcd-ef1234567890",
    "https://www.auto.de/search/vehicle/11223344-5566-7788-99aa-bbccddeeff00",
    "https://www.auto.de/gebrauchtwagen/volkswagen/volkswagen-golf-gte-abc123",
]


@pytest.mark.unit
def test_auto_de_partition_by_brand() -> None:
    scraper = AutoDEScraper()
    segments = scraper.partition_params()
    assert len(segments) > 30
    assert all("brand" in s for s in segments)


@pytest.mark.unit
def test_auto_de_domain_and_country() -> None:
    scraper = AutoDEScraper()
    assert scraper.DOMAIN == "auto.de"
    assert scraper.COUNTRY == "DE"


@pytest.mark.unit
def test_auto_de_build_url_brand_page1() -> None:
    scraper = AutoDEScraper()
    url = scraper._build_url({"brand": "audi"}, 1)
    assert url == "https://www.auto.de/gebrauchtwagen/audi/"


@pytest.mark.unit
def test_auto_de_build_url_brand_page2() -> None:
    scraper = AutoDEScraper()
    url = scraper._build_url({"brand": "bmw"}, 2)
    assert url == "https://www.auto.de/gebrauchtwagen/bmw/?page=2"


@pytest.mark.unit
def test_auto_de_extract_dedup() -> None:
    scraper = AutoDEScraper()
    urls = scraper._extract(_AUTO_DE_HTML)
    assert urls == _AUTO_DE_EXPECTED


@pytest.mark.unit
def test_auto_de_fetch_200() -> None:
    scraper = AutoDEScraper()
    _no_backoff(scraper)
    session = _Session([_Resp(200, _AUTO_DE_HTML)])
    urls = _run(scraper.fetch_segment(session, {"brand": "bmw"}, 1))
    assert urls == _AUTO_DE_EXPECTED


@pytest.mark.unit
def test_auto_de_registry() -> None:
    scraper = get_scraper("auto.de")
    assert scraper is not None
    assert isinstance(scraper, AutoDEScraper)


@pytest.mark.unit
def test_auto_de_domain_map() -> None:
    spec = domain_get("auto.de")
    assert spec is not None
    assert spec.tier == Tier.T1
    assert "DE" in spec.countries


# =========================================================================== #
# youcar.be — SSR HTML, Belgian classifieds (T1)
# =========================================================================== #
from scrapers.portals.youcar_be import YoucarBEScraper

_YOUCAR_HTML = """
<html><body>
<a href="/nl/buy/volkswagen/volkswagen-golf-8-style-antwerpen">VW Golf</a>
<a href="/nl/buy/audi/audi-a3-sportback-limburg">Audi A3</a>
<a href="/nl/buy/volkswagen/volkswagen-golf-8-style-antwerpen">VW Golf dup</a>
<a href="/nl/search">Search link</a>
</body></html>
"""

_YOUCAR_EXPECTED = [
    "https://www.youcar.be/nl/buy/volkswagen/volkswagen-golf-8-style-antwerpen",
    "https://www.youcar.be/nl/buy/audi/audi-a3-sportback-limburg",
]


@pytest.mark.unit
def test_youcar_partition_is_single_segment() -> None:
    scraper = YoucarBEScraper()
    assert scraper.partition_params() == [{}]


@pytest.mark.unit
def test_youcar_domain_and_country() -> None:
    scraper = YoucarBEScraper()
    assert scraper.DOMAIN == "youcar.be"
    assert scraper.COUNTRY == "BE"


@pytest.mark.unit
def test_youcar_build_url_page1() -> None:
    scraper = YoucarBEScraper()
    url = scraper._build_url({}, 1)
    assert url == "https://www.youcar.be/nl/search"


@pytest.mark.unit
def test_youcar_build_url_page3() -> None:
    scraper = YoucarBEScraper()
    url = scraper._build_url({}, 3)
    assert url == "https://www.youcar.be/nl/search?page=3"


@pytest.mark.unit
def test_youcar_extract_dedup() -> None:
    scraper = YoucarBEScraper()
    urls = scraper._extract(_YOUCAR_HTML)
    assert urls == _YOUCAR_EXPECTED


@pytest.mark.unit
def test_youcar_fetch_200() -> None:
    scraper = YoucarBEScraper()
    _no_backoff(scraper)
    session = _Session([_Resp(200, _YOUCAR_HTML)])
    urls = _run(scraper.fetch_segment(session, {}, 1))
    assert urls == _YOUCAR_EXPECTED


@pytest.mark.unit
def test_youcar_registry() -> None:
    scraper = get_scraper("youcar.be")
    assert scraper is not None
    assert isinstance(scraper, YoucarBEScraper)


@pytest.mark.unit
def test_youcar_domain_map() -> None:
    spec = domain_get("youcar.be")
    assert spec is not None
    assert spec.tier == Tier.T1
    assert "BE" in spec.countries


# =========================================================================== #
# myway.be — SSR HTML, D'Ieteren certified (T1)
# =========================================================================== #
from scrapers.portals.myway_be import MyWayBEScraper

_MYWAY_HTML = """
<html><body>
<a href="/fr/offre-voitures-occasion/volkswagen-golf-8-style-tsi-bruxelles/">VW Golf</a>
<a href="/fr/offre-voitures-occasion/audi-a3-sportback-35-tfsi-namur/">Audi A3</a>
<a href="/fr/offre-voitures-occasion/volkswagen-golf-8-style-tsi-bruxelles/">VW Golf dup</a>
<a href="/fr/offre-voitures-occasion/">Search page</a>
</body></html>
"""

_MYWAY_EXPECTED = [
    "https://www.myway.be/fr/offre-voitures-occasion/volkswagen-golf-8-style-tsi-bruxelles/",
    "https://www.myway.be/fr/offre-voitures-occasion/audi-a3-sportback-35-tfsi-namur/",
]


@pytest.mark.unit
def test_myway_partition_is_single_segment() -> None:
    scraper = MyWayBEScraper()
    assert scraper.partition_params() == [{}]


@pytest.mark.unit
def test_myway_domain_and_country() -> None:
    scraper = MyWayBEScraper()
    assert scraper.DOMAIN == "myway.be"
    assert scraper.COUNTRY == "BE"


@pytest.mark.unit
def test_myway_build_url_page1() -> None:
    scraper = MyWayBEScraper()
    url = scraper._build_url({}, 1)
    assert "trier-par=-publicationDate" in url
    assert "page=" not in url


@pytest.mark.unit
def test_myway_build_url_page4() -> None:
    scraper = MyWayBEScraper()
    url = scraper._build_url({}, 4)
    assert "trier-par=-publicationDate" in url
    assert "page=4" in url


@pytest.mark.unit
def test_myway_extract_dedup() -> None:
    scraper = MyWayBEScraper()
    urls = scraper._extract(_MYWAY_HTML)
    assert urls == _MYWAY_EXPECTED


@pytest.mark.unit
def test_myway_fetch_200() -> None:
    scraper = MyWayBEScraper()
    _no_backoff(scraper)
    session = _Session([_Resp(200, _MYWAY_HTML)])
    urls = _run(scraper.fetch_segment(session, {}, 1))
    assert urls == _MYWAY_EXPECTED


@pytest.mark.unit
def test_myway_registry() -> None:
    scraper = get_scraper("myway.be")
    assert scraper is not None
    assert isinstance(scraper, MyWayBEScraper)


@pytest.mark.unit
def test_myway_domain_map() -> None:
    spec = domain_get("myway.be")
    assert spec is not None
    assert spec.tier == Tier.T1
    assert "BE" in spec.countries


# =========================================================================== #
# capcar.fr — migrado al sitemap de productos (multi-strategy 2026-06)
# =========================================================================== #
from scrapers.portals.capcar_fr import CapCarFRScraper
from scrapers.portals.sitemap_listing_base import SitemapListingScraper


@pytest.mark.unit
def test_capcar_is_sitemap_based() -> None:
    s = CapCarFRScraper()
    assert isinstance(s, SitemapListingScraper)
    assert s.DOMAIN == "capcar.fr"
    assert s.COUNTRY == "FR"
    assert s.SITEMAP_URL == "https://www.capcar.fr/sitemap/products.xml"
    assert s.DETAIL_RE.search("/voiture-occasion/peugeot-308-r0107248")
    assert not s.DETAIL_RE.search("/voiture-occasion")  # bare search root excluded
    s._validate()


@pytest.mark.unit
def test_capcar_registry() -> None:
    scraper = get_scraper("capcar.fr")
    assert scraper is not None
    assert isinstance(scraper, CapCarFRScraper)


@pytest.mark.unit
def test_capcar_domain_map() -> None:
    spec = domain_get("capcar.fr")
    assert spec is not None
    assert spec.tier == Tier.T1
    assert "FR" in spec.countries


# =========================================================================== #
# Cross-cutting: all Phase 7 portals are in the registry
# =========================================================================== #
_PHASE7_DOMAINS = [
    "flexicar.es", "clicars.com", "autowereld.nl",
    "auto.de", "youcar.be", "myway.be", "capcar.fr",
]


@pytest.mark.unit
@pytest.mark.parametrize("domain", _PHASE7_DOMAINS)
def test_phase7_portal_in_registry(domain: str) -> None:
    """Every Phase 7 portal must be resolvable via get_scraper."""
    scraper = get_scraper(domain)
    assert scraper is not None, f"{domain} not found in PORTAL_REGISTRY"
    assert scraper.DOMAIN == domain


@pytest.mark.unit
@pytest.mark.parametrize("domain", _PHASE7_DOMAINS)
def test_phase7_portal_in_domain_map(domain: str) -> None:
    """Every Phase 7 portal must be registered in domain_map."""
    spec = domain_get(domain)
    assert spec is not None, f"{domain} not found in domain_map REGISTRY"
    assert spec.tier in (Tier.T0, Tier.T1), f"{domain} should be T0 or T1"


@pytest.mark.unit
@pytest.mark.parametrize("domain", _PHASE7_DOMAINS)
def test_phase7_portal_has_valid_class(domain: str) -> None:
    """Every Phase 7 scraper must extend BasePortalScraper correctly."""
    scraper = get_scraper(domain)
    assert isinstance(scraper, BasePortalScraper)
    assert scraper.DOMAIN != ""
    assert scraper.COUNTRY != ""
    assert scraper.PAGE_SIZE > 0
    assert scraper.MAX_PAGES > 0
    params = scraper.partition_params()
    assert isinstance(params, list)
    assert len(params) > 0
