"""
Tests for Phase 14 — autoweek.nl (safety-net scraper, syndication mirror).

Coroutines run synchronously via asyncio.run() (engine convention).
"""
from __future__ import annotations

import asyncio
from typing import Any


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


class TestAutoweekNL:

    def test_domain_country(self):
        from scrapers.portals.autoweek_nl import AutoweekNLScraper
        s = AutoweekNLScraper()
        assert s.DOMAIN == "autoweek.nl"
        assert s.COUNTRY == "NL"

    def test_partition_produces_price_bands(self):
        from scrapers.portals.autoweek_nl import AutoweekNLScraper
        s = AutoweekNLScraper()
        params = s.partition_params()
        assert len(params) >= 8
        assert params[0]["price_from"] == 0
        assert params[-1].get("price_to") is None

    def test_fetch_extracts_relative_urls(self):
        from scrapers.portals.autoweek_nl import AutoweekNLScraper
        s = AutoweekNLScraper()
        html = '''
        <div class="listing">
            <a href="/occasions/volkswagen/golf/12345-tdi-comfortline">VW Golf</a>
            <a href="/occasions/bmw/3-serie/67890-320d-m-sport">BMW 3</a>
        </div>
        '''
        sess = _Session([_Resp(200, html)])
        urls = _run(s.fetch_segment(sess, {"price_from": 0, "price_to": 3000}, 1))
        assert len(urls) == 2
        assert all(u.startswith("https://www.autoweek.nl/occasions/") for u in urls)

    def test_fetch_extracts_absolute_urls(self):
        from scrapers.portals.autoweek_nl import AutoweekNLScraper
        s = AutoweekNLScraper()
        html = '<a href="https://www.autoweek.nl/occasions/audi/a4/99999-tfsi">Audi A4</a>'
        sess = _Session([_Resp(200, html)])
        urls = _run(s.fetch_segment(sess, {"price_from": 0, "price_to": 3000}, 1))
        assert len(urls) == 1
        assert "99999" in urls[0]

    def test_akamai_challenge_returns_empty(self):
        from scrapers.portals.autoweek_nl import AutoweekNLScraper
        s = AutoweekNLScraper()
        html = '<html><script>var _abck="challenge";</script></html>'
        sess = _Session([_Resp(200, html)])
        urls = _run(s.fetch_segment(sess, {"price_from": 0, "price_to": 3000}, 1))
        assert urls == []

    def test_non_200_returns_empty(self):
        from scrapers.portals.autoweek_nl import AutoweekNLScraper
        s = AutoweekNLScraper()
        sess = _Session([_Resp(403, "Forbidden")])
        urls = _run(s.fetch_segment(sess, {"price_from": 0, "price_to": 3000}, 1))
        assert urls == []

    def test_subdivide_splits_band(self):
        from scrapers.portals.autoweek_nl import AutoweekNLScraper
        s = AutoweekNLScraper()
        subs = s.subdivide_segment({"price_from": 0, "price_to": 10_000})
        assert len(subs) == 2
        assert subs[0] == {"price_from": 0, "price_to": 5_000}
        assert subs[1] == {"price_from": 5_000, "price_to": 10_000}

    def test_subdivide_narrow_returns_empty(self):
        from scrapers.portals.autoweek_nl import AutoweekNLScraper
        s = AutoweekNLScraper()
        assert s.subdivide_segment({"price_from": 5000, "price_to": 5500}) == []

    def test_subdivide_no_ceiling_returns_empty(self):
        from scrapers.portals.autoweek_nl import AutoweekNLScraper
        s = AutoweekNLScraper()
        assert s.subdivide_segment({"price_from": 50000}) == []

    def test_url_format_with_price(self):
        from scrapers.portals.autoweek_nl import AutoweekNLScraper
        s = AutoweekNLScraper()
        html = '<a href="/occasions/test/car/123">T</a>'
        sess = _Session([_Resp(200, html)])
        _run(s.fetch_segment(sess, {"price_from": 5000, "price_to": 10000}, 3))
        url = sess.urls_called[0]
        assert "pagina=3" in url
        assert "prijsvan=5000" in url
        assert "prijstot=10000" in url

    def test_dedup_same_url(self):
        from scrapers.portals.autoweek_nl import AutoweekNLScraper
        s = AutoweekNLScraper()
        html = '''
        <a href="/occasions/vw/golf/123-tdi">L1</a>
        <a href="/occasions/vw/golf/123-tdi">L2</a>
        <a href="https://www.autoweek.nl/occasions/vw/golf/123-tdi">L3</a>
        '''
        sess = _Session([_Resp(200, html)])
        urls = _run(s.fetch_segment(sess, {"price_from": 0, "price_to": 3000}, 1))
        assert len(urls) == 1

    def test_empty_page(self):
        from scrapers.portals.autoweek_nl import AutoweekNLScraper
        s = AutoweekNLScraper()
        sess = _Session([_Resp(200, "<html>Geen resultaten</html>")])
        urls = _run(s.fetch_segment(sess, {"price_from": 0, "price_to": 3000}, 1))
        assert urls == []
