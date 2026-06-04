"""
Tests for Phase 13 portal scrapers — truckscout24.com, classic-trader.com.

Coroutines run synchronously via asyncio.run() (engine convention).
"""
from __future__ import annotations

import asyncio
from typing import Any


# ── test fakes ───────────────────────────────────────────────────────────────

class _Resp:
    def __init__(self, status_code: int = 200, text: str = ""):
        self.status_code = status_code
        self.text = text


class _Session:
    def __init__(self, responses: list[_Resp] | None = None):
        self._responses = list(responses or [])
        self._idx = 0
        self.urls_called: list[str] = []

    async def get(self, url: str, **kw: Any) -> _Resp:
        self.urls_called.append(url)
        if self._idx < len(self._responses):
            resp = self._responses[self._idx]
            self._idx += 1
            return resp
        return _Resp(200, "")


def _run(coro: Any) -> Any:
    return asyncio.run(coro)


# ═══════════════════════════════════════════════════════════════════════════════
# truckscout24.com
# ═══════════════════════════════════════════════════════════════════════════════

class TestTruckScout24DE:

    def test_domain_country(self):
        from scrapers.portals.truckscout24_com import TruckScout24DEScraper
        s = TruckScout24DEScraper()
        assert s.DOMAIN == "truckscout24.com"
        assert s.COUNTRY == "DE"

    def test_partition_produces_categories(self):
        from scrapers.portals.truckscout24_com import TruckScout24DEScraper
        s = TruckScout24DEScraper()
        params = s.partition_params()
        assert len(params) >= 5
        cats = [p["category"] for p in params]
        assert "trucks" in cats
        assert "vans-up-to-7-5-t" in cats
        assert "trailers" in cats

    def test_fetch_extracts_relative_urls(self):
        from scrapers.portals.truckscout24_com import TruckScout24DEScraper
        s = TruckScout24DEScraper()
        html = '''
        <div class="listing">
            <a href="/tsp/ts-12345-man-tgx">MAN TGX</a>
            <a href="/tsp/ts-67890-mercedes-actros">Mercedes Actros</a>
        </div>
        '''
        sess = _Session([_Resp(200, html)])
        urls = _run(s.fetch_segment(sess, {"category": "trucks"}, 1))
        assert len(urls) == 2
        assert all("/tsp/ts-" in u for u in urls)

    def test_fetch_extracts_absolute_urls(self):
        from scrapers.portals.truckscout24_com import TruckScout24DEScraper
        s = TruckScout24DEScraper()
        html = '<a href="https://www.truckscout24.com/tsp/ts-99999-daf-xf">DAF XF</a>'
        sess = _Session([_Resp(200, html)])
        urls = _run(s.fetch_segment(sess, {"category": "trucks"}, 1))
        assert len(urls) == 1
        assert "ts-99999" in urls[0]

    def test_non_200_returns_empty(self):
        from scrapers.portals.truckscout24_com import TruckScout24DEScraper
        s = TruckScout24DEScraper()
        sess = _Session([_Resp(503, "Service Unavailable")])
        urls = _run(s.fetch_segment(sess, {"category": "trucks"}, 1))
        assert urls == []

    def test_subdivide_returns_empty(self):
        from scrapers.portals.truckscout24_com import TruckScout24DEScraper
        s = TruckScout24DEScraper()
        assert s.subdivide_segment({"category": "trucks"}) == []

    def test_url_format_with_category(self):
        from scrapers.portals.truckscout24_com import TruckScout24DEScraper
        s = TruckScout24DEScraper()
        html = '<a href="/tsp/ts-111">Test</a>'
        sess = _Session([_Resp(200, html)])
        _run(s.fetch_segment(sess, {"category": "vans-up-to-7-5-t"}, 3))
        assert "vans-up-to-7-5-t/used?page=3" in sess.urls_called[0]

    def test_dedup_urls(self):
        from scrapers.portals.truckscout24_com import TruckScout24DEScraper
        s = TruckScout24DEScraper()
        html = '''
        <a href="/tsp/ts-same">Link 1</a>
        <a href="/tsp/ts-same">Link 2</a>
        <a href="https://www.truckscout24.com/tsp/ts-same">Absolute</a>
        '''
        sess = _Session([_Resp(200, html)])
        urls = _run(s.fetch_segment(sess, {"category": "trucks"}, 1))
        assert len(urls) == 1

    def test_empty_page(self):
        from scrapers.portals.truckscout24_com import TruckScout24DEScraper
        s = TruckScout24DEScraper()
        sess = _Session([_Resp(200, "<html><body>No results</body></html>")])
        urls = _run(s.fetch_segment(sess, {"category": "trucks"}, 1))
        assert urls == []

    def test_sleep_respects_crawl_delay(self):
        from scrapers.portals.truckscout24_com import TruckScout24DEScraper
        s = TruckScout24DEScraper()
        assert s.SLEEP_BASE >= 5.0  # robots.txt specifies 5s crawl-delay


# ═══════════════════════════════════════════════════════════════════════════════
# classic-trader.com
# ═══════════════════════════════════════════════════════════════════════════════

class TestClassicTraderDE:

    def test_domain_country(self):
        from scrapers.portals.classic_trader_com import ClassicTraderDEScraper
        s = ClassicTraderDEScraper()
        assert s.DOMAIN == "classic-trader.com"
        assert s.COUNTRY == "DE"

    def test_partition_single_segment(self):
        from scrapers.portals.classic_trader_com import ClassicTraderDEScraper
        s = ClassicTraderDEScraper()
        params = s.partition_params()
        assert len(params) == 1
        assert params[0] == {}

    def test_fetch_extracts_relative_urls(self):
        from scrapers.portals.classic_trader_com import ClassicTraderDEScraper
        s = ClassicTraderDEScraper()
        html = '''
        <div class="listing-card">
            <a href="/de/automobile/angebote/porsche-911-carrera-12345">Porsche 911</a>
            <a href="/de/automobile/angebote/mercedes-300sl-67890">Mercedes 300SL</a>
        </div>
        '''
        sess = _Session([_Resp(200, html)])
        urls = _run(s.fetch_segment(sess, {}, 1))
        assert len(urls) == 2
        assert all("/de/automobile/angebote/" in u for u in urls)

    def test_fetch_extracts_absolute_urls(self):
        from scrapers.portals.classic_trader_com import ClassicTraderDEScraper
        s = ClassicTraderDEScraper()
        html = '<a href="https://www.classic-trader.com/de/automobile/angebote/ferrari-250-gto">Ferrari</a>'
        sess = _Session([_Resp(200, html)])
        urls = _run(s.fetch_segment(sess, {}, 1))
        assert len(urls) == 1
        assert "ferrari-250-gto" in urls[0]

    def test_non_200_returns_empty(self):
        from scrapers.portals.classic_trader_com import ClassicTraderDEScraper
        s = ClassicTraderDEScraper()
        sess = _Session([_Resp(404, "Not Found")])
        urls = _run(s.fetch_segment(sess, {}, 1))
        assert urls == []

    def test_subdivide_returns_empty(self):
        from scrapers.portals.classic_trader_com import ClassicTraderDEScraper
        s = ClassicTraderDEScraper()
        assert s.subdivide_segment({}) == []

    def test_url_format(self):
        from scrapers.portals.classic_trader_com import ClassicTraderDEScraper
        s = ClassicTraderDEScraper()
        html = '<a href="/de/automobile/angebote/test">T</a>'
        sess = _Session([_Resp(200, html)])
        _run(s.fetch_segment(sess, {}, 7))
        assert "page=7" in sess.urls_called[0]

    def test_dedup_urls(self):
        from scrapers.portals.classic_trader_com import ClassicTraderDEScraper
        s = ClassicTraderDEScraper()
        html = '''
        <a href="/de/automobile/angebote/same-car">L1</a>
        <a href="/de/automobile/angebote/same-car">L2</a>
        '''
        sess = _Session([_Resp(200, html)])
        urls = _run(s.fetch_segment(sess, {}, 1))
        assert len(urls) == 1

    def test_empty_page(self):
        from scrapers.portals.classic_trader_com import ClassicTraderDEScraper
        s = ClassicTraderDEScraper()
        sess = _Session([_Resp(200, "<html>No vehicles</html>")])
        urls = _run(s.fetch_segment(sess, {}, 1))
        assert urls == []
