"""
Phase-9 portal scraper tests — gowago.ch, gueudet.fr, distinxion.fr.

Coverage gap closure: every remaining T0/T1 portal discovered during the
Phase 9 deep sweep. Each portal exercised against fake duck-typed sessions.

Tests: partition_params grid, _build_url request shaping, _extract parsing
+ dedup, fetch_segment retry/status handling, registry and domain_map wiring.

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
# gowago.ch — Swiss leasing marketplace, Next.js SSR (T1)
# =========================================================================== #
from scrapers.portals.gowago_ch import GowagoCHScraper

_GOWAGO_HTML = """
<html><body>
<a href="/en/listing/audi-q4-e-tron/410FCDFE?downPayment=3960&leasingMileage=10000">Audi Q4</a>
<a href="/en/listing/bmw-3-series/ZGPYX2Q6K1VG?downPayment=6004&leasingMileage=10000">BMW 3</a>
<a href="/en/listing/tesla-model-3/SPJQW1DR6WR8?downPayment=4410">Tesla M3</a>
<a href="/en/listing/audi-q4-e-tron/410FCDFE?downPayment=5000&leasingMileage=15000">Audi Q4 DUP</a>
<a href="/de/listing/vw-golf/42A2AD2D?downPayment=7927">VW Golf</a>
</body></html>
"""


class TestGowagoCH:
    def test_registry(self) -> None:
        s = get_scraper("gowago.ch")
        assert s is not None
        assert isinstance(s, GowagoCHScraper)
        assert s.DOMAIN == "gowago.ch"
        assert s.COUNTRY == "CH"

    def test_domain_map(self) -> None:
        spec = domain_get("gowago.ch")
        assert spec is not None
        assert spec.tier is Tier.T1
        assert spec.waf is WAF.NONE

    def test_partition_params(self) -> None:
        s = GowagoCHScraper()
        params = s.partition_params()
        assert len(params) == 1
        assert params[0] == {}

    def test_build_url_page1(self) -> None:
        s = GowagoCHScraper()
        url = s._build_url(1)
        assert url == "https://gowago.ch/en/explore/vehicleType/used"

    def test_build_url_page5(self) -> None:
        s = GowagoCHScraper()
        url = s._build_url(5)
        assert url == "https://gowago.ch/en/explore/vehicleType/used?page=5"

    def test_extract_dedup(self) -> None:
        s = GowagoCHScraper()
        urls = s._extract(_GOWAGO_HTML)
        # 410FCDFE appears twice with different query params → dedup by path
        assert len(urls) == 4
        assert "https://gowago.ch/en/listing/audi-q4-e-tron/410FCDFE" in urls
        assert "https://gowago.ch/en/listing/bmw-3-series/ZGPYX2Q6K1VG" in urls
        assert "https://gowago.ch/en/listing/tesla-model-3/SPJQW1DR6WR8" in urls
        assert "https://gowago.ch/de/listing/vw-golf/42A2AD2D" in urls

    def test_extract_empty(self) -> None:
        s = GowagoCHScraper()
        assert s._extract("<html><body>No listings</body></html>") == []

    def test_fetch_segment_200(self) -> None:
        s = GowagoCHScraper()
        _no_backoff(s)
        session = _Session([_Resp(200, _GOWAGO_HTML)])
        urls = _run(s.fetch_segment(session, {}, 1))
        assert len(urls) == 4
        assert session.urls[0] == "https://gowago.ch/en/explore/vehicleType/used"

    def test_fetch_segment_403_retry(self) -> None:
        s = GowagoCHScraper()
        _no_backoff(s)
        session = _Session([_Resp(403), _Resp(200, _GOWAGO_HTML)])
        urls = _run(s.fetch_segment(session, {}, 1))
        assert len(urls) == 4
        assert len(session.calls) == 2

    def test_fetch_segment_all_failures(self) -> None:
        s = GowagoCHScraper()
        _no_backoff(s)
        session = _Session([_Resp(503)] * 3)
        urls = _run(s.fetch_segment(session, {}, 1))
        assert urls == []

    def test_fetch_segment_transport_error(self) -> None:
        s = GowagoCHScraper()
        _no_backoff(s)
        session = _Session([ConnectionError("timeout"), _Resp(200, _GOWAGO_HTML)])
        urls = _run(s.fetch_segment(session, {}, 1))
        assert len(urls) == 4

    def test_subdivide_empty(self) -> None:
        s = GowagoCHScraper()
        assert s.subdivide_segment({}) == []


# =========================================================================== #
# gueudet.fr — French dealer group, SSR HTML (T1)
# =========================================================================== #
from scrapers.portals.gueudet_fr import GueudetFRScraper

_GUEUDET_HTML = """
<html><body>
<a href="/voiture/occasion/renault-clio-tce-100-equilibre-818129">Renault Clio</a>
<a href="/voiture/occasion/peugeot-3008-gt-pack-bluehdi-130-818119">Peugeot 3008</a>
<a href="/voiture/occasion/citroen-c3-puretech-83-shine-818088">Citroen C3</a>
<a href="/voiture/occasion/renault-clio-tce-100-equilibre-818129">Renault Clio DUP</a>
<a href="/voiture/peugeot-5008-bluehdi-130-allure-818062">Peugeot 5008</a>
</body></html>
"""


class TestGueudetFR:
    def test_registry(self) -> None:
        s = get_scraper("gueudet.fr")
        assert s is not None
        assert isinstance(s, GueudetFRScraper)
        assert s.DOMAIN == "gueudet.fr"
        assert s.COUNTRY == "FR"

    def test_domain_map(self) -> None:
        spec = domain_get("gueudet.fr")
        assert spec is not None
        assert spec.tier is Tier.T1
        assert spec.waf is WAF.NONE

    def test_partition_params(self) -> None:
        s = GueudetFRScraper()
        params = s.partition_params()
        brands = [p["brand"] for p in params]
        assert "renault" in brands
        assert "peugeot" in brands
        assert "bmw" in brands
        assert len(params) == len(s.BRANDS)

    def test_build_url_page1(self) -> None:
        s = GueudetFRScraper()
        url = s._build_url({"brand": "renault"}, 1)
        assert url == "https://www.gueudet.fr/voiture/occasion?marque=renault"

    def test_build_url_page3(self) -> None:
        s = GueudetFRScraper()
        url = s._build_url({"brand": "peugeot"}, 3)
        assert url == "https://www.gueudet.fr/voiture/occasion?marque=peugeot&page=3"

    def test_extract_dedup(self) -> None:
        s = GueudetFRScraper()
        urls = s._extract(_GUEUDET_HTML)
        # Clio 818129 appears twice → dedup
        assert len(urls) == 4
        assert "https://www.gueudet.fr/voiture/occasion/renault-clio-tce-100-equilibre-818129" in urls
        assert "https://www.gueudet.fr/voiture/occasion/peugeot-3008-gt-pack-bluehdi-130-818119" in urls
        assert "https://www.gueudet.fr/voiture/occasion/citroen-c3-puretech-83-shine-818088" in urls
        assert "https://www.gueudet.fr/voiture/peugeot-5008-bluehdi-130-allure-818062" in urls

    def test_extract_empty(self) -> None:
        s = GueudetFRScraper()
        assert s._extract("<html><body>No listings</body></html>") == []

    def test_fetch_segment_200(self) -> None:
        s = GueudetFRScraper()
        _no_backoff(s)
        session = _Session([_Resp(200, _GUEUDET_HTML)])
        urls = _run(s.fetch_segment(session, {"brand": "renault"}, 1))
        assert len(urls) == 4
        assert "marque=renault" in session.urls[0]

    def test_fetch_segment_429_retry(self) -> None:
        s = GueudetFRScraper()
        _no_backoff(s)
        session = _Session([_Resp(429), _Resp(200, _GUEUDET_HTML)])
        urls = _run(s.fetch_segment(session, {"brand": "renault"}, 1))
        assert len(urls) == 4
        assert len(session.calls) == 2

    def test_fetch_segment_all_failures(self) -> None:
        s = GueudetFRScraper()
        _no_backoff(s)
        session = _Session([_Resp(500)] * 3)
        urls = _run(s.fetch_segment(session, {"brand": "renault"}, 1))
        assert urls == []


# =========================================================================== #
# distinxion.fr — French multi-brand dealer network, Symfony SSR (T1)
# =========================================================================== #
from scrapers.portals.distinxion_fr import DistinxionFRScraper

_DISTINXION_HTML = """
<html><body>
<a href="/voitures/peugeot/208/818294">Peugeot 208</a>
<a href="/voitures/toyota/yaris-cross/818288">Toyota Yaris Cross</a>
<a href="/voitures/dacia/spring/818214">Dacia Spring</a>
<a href="/voitures/peugeot/208/818294">Peugeot 208 DUP</a>
<a href="/voitures/kia/sportage/818134">Kia Sportage</a>
</body></html>
"""


class TestDistinxionFR:
    def test_registry(self) -> None:
        s = get_scraper("distinxion.fr")
        assert s is not None
        assert isinstance(s, DistinxionFRScraper)
        assert s.DOMAIN == "distinxion.fr"
        assert s.COUNTRY == "FR"

    def test_domain_map(self) -> None:
        spec = domain_get("distinxion.fr")
        assert spec is not None
        assert spec.tier is Tier.T1
        assert spec.waf is WAF.NONE

    def test_partition_params(self) -> None:
        s = DistinxionFRScraper()
        params = s.partition_params()
        brands = [p["brand"] for p in params]
        assert "peugeot" in brands
        assert "renault" in brands
        assert "volkswagen" in brands
        assert len(params) == len(s.BRANDS)

    def test_build_url_page1(self) -> None:
        s = DistinxionFRScraper()
        url = s._build_url({"brand": "peugeot"}, 1)
        assert url == "https://www.distinxion.fr/voitures/peugeot"

    def test_build_url_page4(self) -> None:
        s = DistinxionFRScraper()
        url = s._build_url({"brand": "renault"}, 4)
        assert url == "https://www.distinxion.fr/voitures/renault?page=4"

    def test_extract_dedup(self) -> None:
        s = DistinxionFRScraper()
        urls = s._extract(_DISTINXION_HTML)
        # 818294 appears twice → dedup
        assert len(urls) == 4
        assert "https://www.distinxion.fr/voitures/peugeot/208/818294" in urls
        assert "https://www.distinxion.fr/voitures/toyota/yaris-cross/818288" in urls
        assert "https://www.distinxion.fr/voitures/dacia/spring/818214" in urls
        assert "https://www.distinxion.fr/voitures/kia/sportage/818134" in urls

    def test_extract_empty(self) -> None:
        s = DistinxionFRScraper()
        assert s._extract("<html><body>No listings</body></html>") == []

    def test_fetch_segment_200(self) -> None:
        s = DistinxionFRScraper()
        _no_backoff(s)
        session = _Session([_Resp(200, _DISTINXION_HTML)])
        urls = _run(s.fetch_segment(session, {"brand": "peugeot"}, 1))
        assert len(urls) == 4
        assert "peugeot" in session.urls[0]

    def test_fetch_segment_403_retry(self) -> None:
        s = DistinxionFRScraper()
        _no_backoff(s)
        session = _Session([_Resp(403), _Resp(200, _DISTINXION_HTML)])
        urls = _run(s.fetch_segment(session, {"brand": "peugeot"}, 1))
        assert len(urls) == 4
        assert len(session.calls) == 2

    def test_fetch_segment_all_failures(self) -> None:
        s = DistinxionFRScraper()
        _no_backoff(s)
        session = _Session([_Resp(502)] * 3)
        urls = _run(s.fetch_segment(session, {"brand": "peugeot"}, 1))
        assert urls == []

    def test_fetch_segment_transport_error(self) -> None:
        s = DistinxionFRScraper()
        _no_backoff(s)
        session = _Session([TimeoutError("conn timeout"), _Resp(200, _DISTINXION_HTML)])
        urls = _run(s.fetch_segment(session, {"brand": "peugeot"}, 1))
        assert len(urls) == 4


# =========================================================================== #
# Cross-portal: registry completeness
# =========================================================================== #
class TestPhase9RegistryCompleteness:
    """All Phase 9 portals must be in both portal registry and domain_map."""

    PHASE9_DOMAINS = ("gowago.ch", "gueudet.fr", "distinxion.fr")

    def test_all_in_portal_registry(self) -> None:
        for domain in self.PHASE9_DOMAINS:
            s = get_scraper(domain)
            assert s is not None, f"{domain} missing from PORTAL_REGISTRY"
            assert s.DOMAIN == domain

    def test_all_in_domain_map(self) -> None:
        for domain in self.PHASE9_DOMAINS:
            spec = domain_get(domain)
            assert spec is not None, f"{domain} missing from domain_map REGISTRY"
            assert spec.tier in (Tier.T0, Tier.T1)
