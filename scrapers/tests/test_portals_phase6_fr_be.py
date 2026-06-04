"""
Phase-6 FR/BE portal scraper tests.

Portals tested (12 total):
  2ememain.be (BE, T0, LRP API)
  cardoen.be (BE, T1, Nuxt.js SSR)
  aramisauto.com (FR, T1, Next.js SSR)
  leparking.fr (FR, T1, SSR HTML)
  autosphere.fr (FR, T0, REST API)
  reezocar.com (FR, T1, SSR HTML)
  spoticar.fr (FR, T1, SSR HTML)
  auto-selection.com (FR, T0, Meilisearch API)
  annonces-automobile.com (FR, T1, SSR HTML)
  starterre.fr (FR, T1, SSR HTML)
  carizy.com (FR, T1, Nuxt SSR)
  moniteurautomobile.be (BE, T1, SSR HTML)

Each portal is exercised against a fake duck-typed session (no curl_cffi):
partition_params grid, subdivide_segment termination, _build_url request shaping,
_extract parsing + dedup, fetch_segment retry/status handling. Registry wiring
(get_scraper + domain_map) is asserted to catch class/string/tier drift.

Coroutines run synchronously via asyncio.run() (engine convention).
fetch_segment tests stub `_retry_backoff` to no-op so suite never sleeps.
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
from scrapers.portals.deuxememain_be import DeuxememainBEScraper
from scrapers.portals.cardoen_be import CardoenBEScraper
from scrapers.portals.aramisauto_fr import AramisAutoFRScraper
from scrapers.portals.leparking_fr import LeParkingFRScraper
from scrapers.portals.autosphere_fr import AutosphereFRScraper
from scrapers.portals.reezocar_fr import ReezocarFRScraper
from scrapers.portals.spoticar_fr import SpoticarFRScraper
from scrapers.portals.auto_selection_com import AutoSelectionFRScraper
from scrapers.portals.annonces_automobile_com import AnnoncesAutomobileFRScraper
from scrapers.portals.starterre_fr import StarterreFRScraper
from scrapers.portals.carizy_com import CarizyFRScraper
from scrapers.portals.moniteur_auto_be import MoniteurAutoBEScraper


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
    """Fake AsyncSession yielding queued responses."""

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
    """Stub exponential backoff so retry tests run instantly."""

    async def _noop(attempt: int, factor: float = 1.0) -> None:
        return None

    scraper._retry_backoff = _noop  # type: ignore[method-assign]


# =========================================================================== #
# 2ememain.be -- LRP API (T0, French mirror of 2dehands.be)
# =========================================================================== #

_2EMEMAIN_JSON = _json.dumps({
    "listings": [
        {"vipUrl": "/v/autos/bmw/m1234567890-bmw-320d-2019"},
        {"vipUrl": "/v/autos/audi/m9876543210-audi-a3-2020"},
        {"vipUrl": "/v/autos/bmw/m1234567890-bmw-320d-2019"},
    ]
})

_2EMEMAIN_EXPECTED = [
    "https://www.2ememain.be/v/autos/bmw/m1234567890-bmw-320d-2019",
    "https://www.2ememain.be/v/autos/audi/m9876543210-audi-a3-2020",
]


@pytest.mark.unit
def test_2ememain_domain_and_country() -> None:
    s = DeuxememainBEScraper()
    assert s.DOMAIN == "2ememain.be"
    assert s.COUNTRY == "BE"


@pytest.mark.unit
def test_2ememain_partition_grid_shape() -> None:
    s = DeuxememainBEScraper()
    segments = s.partition_params()
    expected = len(s.YEAR_BANDS) * len(s.PRICE_BANDS)
    assert len(segments) == expected
    assert all("year_from" in p and "price_from" in p for p in segments)


@pytest.mark.unit
def test_2ememain_subdivide_terminates() -> None:
    s = DeuxememainBEScraper()
    seg = s.partition_params()[0]
    subs = s.subdivide_segment(seg)
    assert len(subs) > 0
    for sub in subs:
        assert sub.get("_fine") is True
        assert s.subdivide_segment(sub) == []


@pytest.mark.unit
def test_2ememain_build_url_contains_api_params() -> None:
    s = DeuxememainBEScraper()
    url = s._build_url({"year_from": 2020, "year_to": 2022, "price_from": 10_000, "price_to": 20_000}, offset=30)
    assert "lrp/api/search" in url
    assert "l1CategoryId=91" in url
    assert "offset=30" in url
    assert "limit=30" in url
    assert "constructionYear:2020:2022" in url
    assert "PriceCents:1000000:2000000" in url


@pytest.mark.unit
def test_2ememain_extract_dedup() -> None:
    s = DeuxememainBEScraper()
    urls = s._extract(_2EMEMAIN_JSON)
    assert urls == _2EMEMAIN_EXPECTED


@pytest.mark.unit
def test_2ememain_extract_empty_on_garbage() -> None:
    s = DeuxememainBEScraper()
    assert s._extract("") == []
    assert s._extract("not json") == []
    assert s._extract('{"listings": "bad"}') == []
    assert s._extract('{"other": []}') == []


@pytest.mark.unit
def test_2ememain_fetch_segment_retry_on_403() -> None:
    s = DeuxememainBEScraper()
    _no_backoff(s)
    sess = _Session([_Resp(403), _Resp(403), _Resp(200, _2EMEMAIN_JSON)])
    urls = _run(s.fetch_segment(sess, {"year_from": 2020, "year_to": 2022, "price_from": 0, "price_to": 5000}, 1))
    assert len(urls) == 2
    assert len(sess.calls) == 3


@pytest.mark.unit
def test_2ememain_fetch_segment_all_retries_fail() -> None:
    s = DeuxememainBEScraper()
    _no_backoff(s)
    sess = _Session([_Resp(429), _Resp(503), _Resp(403)])
    urls = _run(s.fetch_segment(sess, {"year_from": 2020, "year_to": 2022, "price_from": 0, "price_to": 5000}, 1))
    assert urls == []
    assert len(sess.calls) == 3


# =========================================================================== #
# cardoen.be -- Nuxt.js SSR (T1, Aramis Group)
# =========================================================================== #

_CARDOEN_HTML = """
<html><body>
<a href="/fr/achat/peugeot-3008-hybrid-320088/">Peugeot 3008</a>
<a href="/fr/achat/hyundai-tucson-feel-328970/">Hyundai Tucson</a>
<a href="/fr/achat/peugeot-3008-hybrid-320088/">dup Peugeot</a>
<a href="/fr/achat/occasions/">Category link</a>
</body></html>
"""

_CARDOEN_EXPECTED = [
    "https://www.cardoen.be/fr/achat/peugeot-3008-hybrid-320088/",
    "https://www.cardoen.be/fr/achat/hyundai-tucson-feel-328970/",
]


@pytest.mark.unit
def test_cardoen_domain_and_country() -> None:
    s = CardoenBEScraper()
    assert s.DOMAIN == "cardoen.be"
    assert s.COUNTRY == "BE"


@pytest.mark.unit
def test_cardoen_partition() -> None:
    s = CardoenBEScraper()
    segments = s.partition_params()
    assert len(segments) >= 1
    assert isinstance(segments[0], dict)


@pytest.mark.unit
def test_cardoen_build_url() -> None:
    s = CardoenBEScraper()
    url = s._build_url(1)
    assert "cardoen.be" in url
    assert "page=1" in url


@pytest.mark.unit
def test_cardoen_build_url_page2() -> None:
    s = CardoenBEScraper()
    url = s._build_url(2)
    assert "page=2" in url


@pytest.mark.unit
def test_cardoen_extract_dedup() -> None:
    s = CardoenBEScraper()
    urls = s._extract(_CARDOEN_HTML)
    assert len(urls) == 2
    assert urls == _CARDOEN_EXPECTED


@pytest.mark.unit
def test_cardoen_extract_filters_categories() -> None:
    s = CardoenBEScraper()
    urls = s._extract(_CARDOEN_HTML)
    assert not any("occasions/" in u for u in urls)


@pytest.mark.unit
def test_cardoen_extract_empty() -> None:
    s = CardoenBEScraper()
    assert s._extract("") == []
    assert s._extract(None) == []  # type: ignore[arg-type]


@pytest.mark.unit
def test_cardoen_fetch_segment_success() -> None:
    s = CardoenBEScraper()
    _no_backoff(s)
    sess = _Session([_Resp(200, _CARDOEN_HTML)])
    urls = _run(s.fetch_segment(sess, {"type": "occasions"}, 1))
    assert len(urls) == 2


# =========================================================================== #
# aramisauto.com -- Next.js SSR (T1, Aramis Group parent)
# =========================================================================== #

_ARAMIS_HTML = """
<html><body>
<a href="/achat/peugeot/208/my-slug-123/">Peugeot 208</a>
<a href="/achat/renault/clio-5/another-slug-456/">Renault Clio 5</a>
<a href="/achat/peugeot/208/offres/">Category link</a>
<a href="/achat/peugeot/208/my-slug-123/">dup Peugeot</a>
</body></html>
"""

_ARAMIS_EXPECTED = [
    "https://www.aramisauto.com/achat/peugeot/208/my-slug-123/",
    "https://www.aramisauto.com/achat/renault/clio-5/another-slug-456/",
]


@pytest.mark.unit
def test_aramis_domain_and_country() -> None:
    s = AramisAutoFRScraper()
    assert s.DOMAIN == "aramisauto.com"
    assert s.COUNTRY == "FR"


@pytest.mark.unit
def test_aramis_partition_single() -> None:
    s = AramisAutoFRScraper()
    assert s.partition_params() == [{}]


@pytest.mark.unit
def test_aramis_extract_filters_offres() -> None:
    s = AramisAutoFRScraper()
    urls = s._extract(_ARAMIS_HTML)
    assert urls == _ARAMIS_EXPECTED
    assert not any("offres" in u for u in urls)


@pytest.mark.unit
def test_aramis_extract_dedup() -> None:
    s = AramisAutoFRScraper()
    urls = s._extract(_ARAMIS_HTML)
    assert len(urls) == 2


# =========================================================================== #
# leparking.fr -- SSR HTML (T1, meta-aggregator)
# =========================================================================== #

_LEPARKING_HTML = """
<html><body>
<a class="linkAd" href="/voiture-occasion/peugeot-308-2019-diesel-12345.html">Peugeot 308</a>
<a class="linkAd" href="/voiture-occasion/renault-clio-2020-essence-67890.html">Renault Clio</a>
<a class="linkAd" href="/voiture-occasion/peugeot-308-2019-diesel-12345.html">dup Peugeot</a>
</body></html>
"""

_LEPARKING_EXPECTED = [
    "https://www.leparking.fr/voiture-occasion/peugeot-308-2019-diesel-12345.html",
    "https://www.leparking.fr/voiture-occasion/renault-clio-2020-essence-67890.html",
]


@pytest.mark.unit
def test_leparking_domain_and_country() -> None:
    s = LeParkingFRScraper()
    assert s.DOMAIN == "leparking.fr"
    assert s.COUNTRY == "FR"


@pytest.mark.unit
def test_leparking_partition_by_brand() -> None:
    s = LeParkingFRScraper()
    segments = s.partition_params()
    assert len(segments) == len(s.BRANDS)
    assert all("brand" in p for p in segments)


@pytest.mark.unit
def test_leparking_build_url() -> None:
    s = LeParkingFRScraper()
    url = s._build_url({"brand": "peugeot"}, 3)
    assert url == "https://www.leparking.fr/voiture-occasion/peugeot.html?p=3"


@pytest.mark.unit
def test_leparking_extract_dedup() -> None:
    s = LeParkingFRScraper()
    urls = s._extract(_LEPARKING_HTML)
    assert urls == _LEPARKING_EXPECTED
    assert len(urls) == 2


@pytest.mark.unit
def test_leparking_extract_empty() -> None:
    s = LeParkingFRScraper()
    assert s._extract("") == []
    assert s._extract(None) == []  # type: ignore[arg-type]


# =========================================================================== #
# autosphere.fr -- REST API (T0)
# =========================================================================== #

_AUTOSPHERE_JSON = _json.dumps({
    "results": [
        {"slug": "peugeot-3008-gt-hybrid-2024-12345"},
        {"slug": "renault-captur-tce-2023-67890"},
        {"slug": "peugeot-3008-gt-hybrid-2024-12345"},
    ],
    "total": 15600,
})

_AUTOSPHERE_EXPECTED = [
    "https://www.autosphere.fr/recherche/peugeot-3008-gt-hybrid-2024-12345",
    "https://www.autosphere.fr/recherche/renault-captur-tce-2023-67890",
]


@pytest.mark.unit
def test_autosphere_domain_and_country() -> None:
    s = AutosphereFRScraper()
    assert s.DOMAIN == "autosphere.fr"
    assert s.COUNTRY == "FR"


@pytest.mark.unit
def test_autosphere_partition_single() -> None:
    s = AutosphereFRScraper()
    assert s.partition_params() == [{}]


@pytest.mark.unit
def test_autosphere_build_url() -> None:
    s = AutosphereFRScraper()
    url = s._build_url(0)
    assert "/api/stock/vehicles" in url
    assert "voiture=occasion" in url
    assert "from=0" in url
    assert "size=100" in url


@pytest.mark.unit
def test_autosphere_extract_dedup() -> None:
    s = AutosphereFRScraper()
    urls = s._extract(_AUTOSPHERE_JSON)
    assert urls == _AUTOSPHERE_EXPECTED
    assert len(urls) == 2


@pytest.mark.unit
def test_autosphere_extract_empty_on_garbage() -> None:
    s = AutosphereFRScraper()
    assert s._extract("") == []
    assert s._extract("not json") == []
    assert s._extract('{"results": "bad"}') == []


@pytest.mark.unit
def test_autosphere_fetch_segment_success() -> None:
    s = AutosphereFRScraper()
    _no_backoff(s)
    sess = _Session([_Resp(200, _AUTOSPHERE_JSON)])
    urls = _run(s.fetch_segment(sess, {}, 1))
    assert len(urls) == 2


# =========================================================================== #
# reezocar.com -- SSR HTML (T1, aggregator)
# =========================================================================== #

_REEZOCAR_HTML = """
<html><body>
<a href="/fr/occasion/peugeot-208-2020-essence-paris-12345.html">Peugeot 208</a>
<a href="/fr/occasion/bmw-serie-3-2019-diesel-lyon-67890.html">BMW Serie 3</a>
<a href="/fr/occasion/peugeot-208-2020-essence-paris-12345.html">dup</a>
</body></html>
"""

_REEZOCAR_EXPECTED = [
    "https://www.reezocar.com/fr/occasion/peugeot-208-2020-essence-paris-12345.html",
    "https://www.reezocar.com/fr/occasion/bmw-serie-3-2019-diesel-lyon-67890.html",
]


@pytest.mark.unit
def test_reezocar_domain_and_country() -> None:
    s = ReezocarFRScraper()
    assert s.DOMAIN == "reezocar.com"
    assert s.COUNTRY == "FR"


@pytest.mark.unit
def test_reezocar_partition_grid() -> None:
    s = ReezocarFRScraper()
    segments = s.partition_params()
    expected = len(s.YEAR_BANDS) * len(s.PRICE_BANDS)
    assert len(segments) == expected


@pytest.mark.unit
def test_reezocar_build_url() -> None:
    s = ReezocarFRScraper()
    url = s._build_url({"year_from": 2020, "year_to": 2022, "price_from": 10_000, "price_to": 30_000}, 5)
    assert "page=5" in url
    assert "price_min=10000" in url
    assert "price_max=30000" in url
    assert "year_min=2020" in url
    assert "year_max=2022" in url


@pytest.mark.unit
def test_reezocar_extract_dedup() -> None:
    s = ReezocarFRScraper()
    urls = s._extract(_REEZOCAR_HTML)
    assert urls == _REEZOCAR_EXPECTED


# =========================================================================== #
# spoticar.fr -- SSR HTML (T1, Stellantis)
# =========================================================================== #

_SPOTICAR_HTML = """
<html><body>
<a href="/voitures-occasion/peugeot/208/like-new-2023-12345">Peugeot 208</a>
<a href="/voitures-occasion/citroen/c3/reconditioned-2022-67890">Citroen C3</a>
<a href="/voitures-occasion/peugeot/208/like-new-2023-12345">dup</a>
</body></html>
"""

_SPOTICAR_EXPECTED = [
    "https://www.spoticar.fr/voitures-occasion/peugeot/208/like-new-2023-12345",
    "https://www.spoticar.fr/voitures-occasion/citroen/c3/reconditioned-2022-67890",
]


@pytest.mark.unit
def test_spoticar_domain_and_country() -> None:
    s = SpoticarFRScraper()
    assert s.DOMAIN == "spoticar.fr"
    assert s.COUNTRY == "FR"


@pytest.mark.unit
def test_spoticar_partition_grid() -> None:
    s = SpoticarFRScraper()
    segments = s.partition_params()
    expected = len(s.YEAR_BANDS) * len(s.PRICE_BANDS)
    assert len(segments) == expected


@pytest.mark.unit
def test_spoticar_build_url() -> None:
    s = SpoticarFRScraper()
    url = s._build_url({"year_from": 2020, "year_to": 2022, "price_from": 10_000, "price_to": 30_000}, 3)
    assert "page=3" in url
    assert "prix-min=10000" in url
    assert "prix-max=30000" in url
    assert "annee-min=2020" in url
    assert "annee-max=2022" in url


@pytest.mark.unit
def test_spoticar_extract_dedup() -> None:
    s = SpoticarFRScraper()
    urls = s._extract(_SPOTICAR_HTML)
    assert urls == _SPOTICAR_EXPECTED


@pytest.mark.unit
def test_spoticar_extract_empty() -> None:
    s = SpoticarFRScraper()
    assert s._extract("") == []
    assert s._extract("<html>no cars here</html>") == []


# =========================================================================== #
# auto-selection.com -- Meilisearch API (T0, aggregator)
# =========================================================================== #

_AUTOSELECTION_JSON = _json.dumps({
    "results": [{
        "hits": [
            {"slug": "peugeot-208-allure-2023-12345"},
            {"slug": "bmw-serie-3-sport-2022-67890"},
            {"slug": "peugeot-208-allure-2023-12345"},
        ],
        "totalHits": 500,
    }]
})

_AUTOSELECTION_EXPECTED = [
    "https://www.auto-selection.com/acheter/peugeot-208-allure-2023-12345",
    "https://www.auto-selection.com/acheter/bmw-serie-3-sport-2022-67890",
]


@pytest.mark.unit
def test_autoselection_domain_and_country() -> None:
    s = AutoSelectionFRScraper()
    assert s.DOMAIN == "auto-selection.com"
    assert s.COUNTRY == "FR"


@pytest.mark.unit
def test_autoselection_partition_by_brand() -> None:
    s = AutoSelectionFRScraper()
    segments = s.partition_params()
    assert len(segments) == len(s.BRANDS)
    assert all("brand" in p for p in segments)


@pytest.mark.unit
def test_autoselection_subdivide_by_price() -> None:
    s = AutoSelectionFRScraper()
    seg = {"brand": "BMW"}
    subs = s.subdivide_segment(seg)
    assert len(subs) == len(s.PRICE_BANDS)
    for sub in subs:
        assert sub.get("_fine") is True
        assert sub["brand"] == "BMW"
        assert s.subdivide_segment(sub) == []


@pytest.mark.unit
def test_autoselection_build_filter() -> None:
    s = AutoSelectionFRScraper()
    f = s._build_filter({"brand": "BMW", "price_min": 10000, "price_max": 20000})
    assert 'brand = "BMW"' in f
    assert "price >= 10000" in f
    assert "price < 20000" in f


@pytest.mark.unit
def test_autoselection_extract_dedup() -> None:
    s = AutoSelectionFRScraper()
    urls = s._extract(_AUTOSELECTION_JSON)
    assert urls == _AUTOSELECTION_EXPECTED


@pytest.mark.unit
def test_autoselection_extract_empty() -> None:
    s = AutoSelectionFRScraper()
    assert s._extract("") == []
    assert s._extract("not json") == []
    assert s._extract('{"results": []}') == []
    assert s._extract('{"results": [{"hits": []}]}') == []


@pytest.mark.unit
def test_autoselection_fetch_segment_posts() -> None:
    s = AutoSelectionFRScraper()
    _no_backoff(s)
    sess = _Session([_Resp(200, _AUTOSELECTION_JSON)])
    urls = _run(s.fetch_segment(sess, {"brand": "BMW"}, 1))
    assert len(urls) == 2
    assert sess.calls[0]["method"] == "POST"


# =========================================================================== #
# annonces-automobile.com -- SSR HTML (T1, premium portal)
# =========================================================================== #

_ANNONCES_HTML = """
<html><body>
<a href="https://www.annonces-automobile.com/acheter/bmw-m3-competition-2023-12345">BMW M3</a>
<a href="https://www.annonces-automobile.com/acheter/porsche-911-carrera-2022-67890">Porsche 911</a>
<a href="https://www.annonces-automobile.com/acheter/bmw-m3-competition-2023-12345">dup BMW</a>
<a href="https://www.annonces-automobile.com/acheter?sort=price">Category link</a>
</body></html>
"""

_ANNONCES_EXPECTED = [
    "https://www.annonces-automobile.com/acheter/bmw-m3-competition-2023-12345",
    "https://www.annonces-automobile.com/acheter/porsche-911-carrera-2022-67890",
]


@pytest.mark.unit
def test_annonces_domain_and_country() -> None:
    s = AnnoncesAutomobileFRScraper()
    assert s.DOMAIN == "annonces-automobile.com"
    assert s.COUNTRY == "FR"


@pytest.mark.unit
def test_annonces_partition() -> None:
    s = AnnoncesAutomobileFRScraper()
    segments = s.partition_params()
    assert len(segments) == 1
    assert segments[0]["segment"] == "occasion"


@pytest.mark.unit
def test_annonces_build_url() -> None:
    s = AnnoncesAutomobileFRScraper()
    url = s._build_url({"segment": "occasion"}, 5)
    assert url == "https://www.annonces-automobile.com/l-s/occasion?pg=5"


@pytest.mark.unit
def test_annonces_extract_dedup() -> None:
    s = AnnoncesAutomobileFRScraper()
    urls = s._extract(_ANNONCES_HTML)
    assert urls == _ANNONCES_EXPECTED


@pytest.mark.unit
def test_annonces_extract_filters_search_links() -> None:
    s = AnnoncesAutomobileFRScraper()
    urls = s._extract(_ANNONCES_HTML)
    assert not any("?sort=" in u for u in urls)


@pytest.mark.unit
def test_annonces_extract_empty() -> None:
    s = AnnoncesAutomobileFRScraper()
    assert s._extract("") == []
    assert s._extract("<html>no cars</html>") == []


# =========================================================================== #
# starterre.fr -- SSR HTML (T1, mandataire)
# =========================================================================== #

_STARTERRE_HTML = """
<html><body>
<a href="/vehicule/peugeot-3008-gt-pack-2024-12345">Peugeot 3008</a>
<a href="/vehicule/dacia-sandero-stepway-2023-67890">Dacia Sandero</a>
<a href="/vehicule/peugeot-3008-gt-pack-2024-12345">dup</a>
</body></html>
"""

_STARTERRE_EXPECTED = [
    "https://www.starterre.fr/vehicule/peugeot-3008-gt-pack-2024-12345",
    "https://www.starterre.fr/vehicule/dacia-sandero-stepway-2023-67890",
]


@pytest.mark.unit
def test_starterre_domain_and_country() -> None:
    s = StarterreFRScraper()
    assert s.DOMAIN == "starterre.fr"
    assert s.COUNTRY == "FR"


@pytest.mark.unit
def test_starterre_partition_single() -> None:
    s = StarterreFRScraper()
    assert s.partition_params() == [{}]


@pytest.mark.unit
def test_starterre_build_url() -> None:
    s = StarterreFRScraper()
    url = s._build_url(3)
    assert url == "https://www.starterre.fr/recherche?page=3"


@pytest.mark.unit
def test_starterre_extract_dedup() -> None:
    s = StarterreFRScraper()
    urls = s._extract(_STARTERRE_HTML)
    assert urls == _STARTERRE_EXPECTED


@pytest.mark.unit
def test_starterre_extract_empty() -> None:
    s = StarterreFRScraper()
    assert s._extract("") == []
    assert s._extract(None) == []  # type: ignore[arg-type]


@pytest.mark.unit
def test_starterre_fetch_segment_success() -> None:
    s = StarterreFRScraper()
    _no_backoff(s)
    sess = _Session([_Resp(200, _STARTERRE_HTML)])
    urls = _run(s.fetch_segment(sess, {}, 1))
    assert len(urls) == 2


# =========================================================================== #
# carizy.com -- Nuxt SSR (T1, P2P)
# =========================================================================== #

_CARIZY_HTML = """
<html><body>
<a href="/voiture-occasion/renault-clio-2020-essence-paris">Renault Clio</a>
<a href="/voiture-occasion/peugeot-208-2021-diesel-lyon">Peugeot 208</a>
<a href="/voiture-occasion/renault-clio-2020-essence-paris">dup</a>
</body></html>
"""

_CARIZY_EXPECTED = [
    "https://www.carizy.com/voiture-occasion/renault-clio-2020-essence-paris",
    "https://www.carizy.com/voiture-occasion/peugeot-208-2021-diesel-lyon",
]


@pytest.mark.unit
def test_carizy_domain_and_country() -> None:
    s = CarizyFRScraper()
    assert s.DOMAIN == "carizy.com"
    assert s.COUNTRY == "FR"


@pytest.mark.unit
def test_carizy_partition_single() -> None:
    s = CarizyFRScraper()
    assert s.partition_params() == [{}]


@pytest.mark.unit
def test_carizy_build_url() -> None:
    s = CarizyFRScraper()
    url = s._build_url(2)
    assert url == "https://www.carizy.com/voiture-occasion?page=2"


@pytest.mark.unit
def test_carizy_extract_dedup() -> None:
    s = CarizyFRScraper()
    urls = s._extract(_CARIZY_HTML)
    assert urls == _CARIZY_EXPECTED


@pytest.mark.unit
def test_carizy_extract_empty() -> None:
    s = CarizyFRScraper()
    assert s._extract("") == []
    assert s._extract(None) == []  # type: ignore[arg-type]


@pytest.mark.unit
def test_carizy_fetch_segment_retry() -> None:
    s = CarizyFRScraper()
    _no_backoff(s)
    sess = _Session([_Resp(429), _Resp(200, _CARIZY_HTML)])
    urls = _run(s.fetch_segment(sess, {}, 1))
    assert len(urls) == 2
    assert len(sess.calls) == 2


# =========================================================================== #
# moniteurautomobile.be -- SSR HTML (T1, Belgian reference)
# =========================================================================== #

_MONITEUR_HTML = """
<html><body>
<a href="/voitures-occasion/volkswagen-golf-8-2023-12345.html">VW Golf</a>
<a href="/voitures-occasion/bmw-x3-xdrive-2022-67890.html">BMW X3</a>
<a href="/voitures-occasion/volkswagen-golf-8-2023-12345.html">dup</a>
</body></html>
"""

_MONITEUR_EXPECTED = [
    "https://www.moniteurautomobile.be/voitures-occasion/volkswagen-golf-8-2023-12345.html",
    "https://www.moniteurautomobile.be/voitures-occasion/bmw-x3-xdrive-2022-67890.html",
]


@pytest.mark.unit
def test_moniteur_domain_and_country() -> None:
    s = MoniteurAutoBEScraper()
    assert s.DOMAIN == "moniteurautomobile.be"
    assert s.COUNTRY == "BE"


@pytest.mark.unit
def test_moniteur_partition_by_brand() -> None:
    s = MoniteurAutoBEScraper()
    segments = s.partition_params()
    assert len(segments) == len(s.BRANDS)
    assert all("brand" in p for p in segments)


@pytest.mark.unit
def test_moniteur_build_url_with_brand() -> None:
    s = MoniteurAutoBEScraper()
    url = s._build_url({"brand": "volkswagen"}, 4)
    assert url == "https://www.moniteurautomobile.be/marque--volkswagen/acheter-auto/occasion.html?page=4"


@pytest.mark.unit
def test_moniteur_build_url_no_brand() -> None:
    s = MoniteurAutoBEScraper()
    url = s._build_url({}, 1)
    assert url == "https://www.moniteurautomobile.be/acheter-auto/occasion.html?page=1"


@pytest.mark.unit
def test_moniteur_extract_dedup() -> None:
    s = MoniteurAutoBEScraper()
    urls = s._extract(_MONITEUR_HTML)
    assert urls == _MONITEUR_EXPECTED


@pytest.mark.unit
def test_moniteur_extract_empty() -> None:
    s = MoniteurAutoBEScraper()
    assert s._extract("") == []
    assert s._extract(None) == []  # type: ignore[arg-type]


@pytest.mark.unit
def test_moniteur_fetch_segment_success() -> None:
    s = MoniteurAutoBEScraper()
    _no_backoff(s)
    sess = _Session([_Resp(200, _MONITEUR_HTML)])
    urls = _run(s.fetch_segment(sess, {"brand": "bmw"}, 1))
    assert len(urls) == 2


# =========================================================================== #
# Registry wiring -- PORTAL_REGISTRY + domain_map coherence
# =========================================================================== #

_FR_BE_DOMAINS = [
    ("2ememain.be",             DeuxememainBEScraper,        "BE", Tier.T0),
    ("cardoen.be",              CardoenBEScraper,            "BE", Tier.T1),
    ("aramisauto.com",          AramisAutoFRScraper,         "FR", Tier.T1),
    ("leparking.fr",            LeParkingFRScraper,          "FR", Tier.T1),
    ("autosphere.fr",           AutosphereFRScraper,         "FR", Tier.T0),
    ("reezocar.com",            ReezocarFRScraper,           "FR", Tier.T1),
    ("spoticar.fr",             SpoticarFRScraper,           "FR", Tier.T1),
    ("auto-selection.com",      AutoSelectionFRScraper,      "FR", Tier.T0),
    ("annonces-automobile.com", AnnoncesAutomobileFRScraper, "FR", Tier.T1),
    ("starterre.fr",            StarterreFRScraper,          "FR", Tier.T1),
    ("carizy.com",              CarizyFRScraper,             "FR", Tier.T1),
    ("moniteurautomobile.be",   MoniteurAutoBEScraper,       "BE", Tier.T1),
]


@pytest.mark.unit
@pytest.mark.parametrize("domain,cls,country,tier", _FR_BE_DOMAINS)
def test_portal_registry_resolves(domain: str, cls: type, country: str, tier: Tier) -> None:
    scraper = get_scraper(domain)
    assert scraper is not None, f"get_scraper('{domain}') returned None -- not registered"
    assert isinstance(scraper, cls)
    assert scraper.DOMAIN == domain
    assert scraper.COUNTRY == country


@pytest.mark.unit
@pytest.mark.parametrize("domain,cls,country,tier", _FR_BE_DOMAINS)
def test_domain_map_tier(domain: str, cls: type, country: str, tier: Tier) -> None:
    spec = domain_get(domain)
    assert spec is not None, f"domain_map.get('{domain}') returned None -- not in REGISTRY"
    assert spec.tier == tier, f"{domain}: expected {tier}, got {spec.tier}"
    assert country in spec.countries


# =========================================================================== #
# Cross-portal: every new scraper must be a BasePortalScraper subclass
# =========================================================================== #

@pytest.mark.unit
@pytest.mark.parametrize("cls", [
    DeuxememainBEScraper,
    CardoenBEScraper,
    AramisAutoFRScraper,
    LeParkingFRScraper,
    AutosphereFRScraper,
    ReezocarFRScraper,
    SpoticarFRScraper,
    AutoSelectionFRScraper,
    AnnoncesAutomobileFRScraper,
    StarterreFRScraper,
    CarizyFRScraper,
    MoniteurAutoBEScraper,
])
def test_subclass_of_base(cls: type) -> None:
    assert issubclass(cls, BasePortalScraper)
    inst = cls()
    assert inst.DOMAIN
    assert inst.COUNTRY
    assert inst.PAGE_SIZE > 0
    assert inst.MAX_PAGES > 0
