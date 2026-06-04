"""
Tests for Phase 12 portal scrapers — caravenue.com, simplicicar.com.

Coroutines run synchronously via asyncio.run() (engine convention).
"""
from __future__ import annotations

import asyncio
import json
from typing import Any


# ── test fakes (same pattern as all other phase tests) ───────────────────────

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
# caravenue.com
# ═══════════════════════════════════════════════════════════════════════════════

class TestCaravenueFR:

    def test_domain_country(self):
        from scrapers.portals.caravenue_com import CaravenueFRScraper
        s = CaravenueFRScraper()
        assert s.DOMAIN == "caravenue.com"
        assert s.COUNTRY == "FR"

    def test_partition_single_segment(self):
        from scrapers.portals.caravenue_com import CaravenueFRScraper
        s = CaravenueFRScraper()
        params = s.partition_params()
        assert len(params) == 1
        assert params[0] == {}

    def test_fetch_extracts_from_next_data(self):
        from scrapers.portals.caravenue_com import CaravenueFRScraper
        s = CaravenueFRScraper()
        next_data = json.dumps({
            "props": {
                "pageProps": {
                    "vehicles": [
                        {"url": "/vehicule/audi-a3-12345"},
                        {"url": "/vehicule/bmw-320d-67890"},
                        {"slug": "/vehicule/renault-clio-11111"},
                    ]
                }
            }
        })
        html = f'<html><script id="__NEXT_DATA__" type="application/json">{next_data}</script></html>'
        sess = _Session([_Resp(200, html)])
        urls = _run(s.fetch_segment(sess, {}, 1))
        assert len(urls) == 3
        assert all(u.startswith("https://www.caravenue.com/vehicule/") for u in urls)

    def test_fetch_fallback_to_html(self):
        from scrapers.portals.caravenue_com import CaravenueFRScraper
        s = CaravenueFRScraper()
        html = '''
        <div class="card">
            <a href="/vehicule-occasion/peugeot-308-abc">Peugeot 308</a>
            <a href="/vehicule-occasion/citroen-c3-def">Citroen C3</a>
        </div>
        '''
        sess = _Session([_Resp(200, html)])
        urls = _run(s.fetch_segment(sess, {}, 1))
        assert len(urls) == 2
        assert "https://www.caravenue.com/vehicule-occasion/peugeot-308-abc" in urls

    def test_fetch_with_id_fallback(self):
        from scrapers.portals.caravenue_com import CaravenueFRScraper
        s = CaravenueFRScraper()
        next_data = json.dumps({
            "props": {
                "pageProps": {
                    "vehicles": [
                        {"id": "V12345"},
                        {"vehicleId": "V67890"},
                    ]
                }
            }
        })
        html = f'<html><script id="__NEXT_DATA__" type="application/json">{next_data}</script></html>'
        sess = _Session([_Resp(200, html)])
        urls = _run(s.fetch_segment(sess, {}, 1))
        assert len(urls) == 2
        assert "https://www.caravenue.com/vehicule/V12345" in urls

    def test_non_200_returns_empty(self):
        from scrapers.portals.caravenue_com import CaravenueFRScraper
        s = CaravenueFRScraper()
        sess = _Session([_Resp(403, "Forbidden")])
        urls = _run(s.fetch_segment(sess, {}, 1))
        assert urls == []

    def test_malformed_json_falls_back_to_html(self):
        from scrapers.portals.caravenue_com import CaravenueFRScraper
        s = CaravenueFRScraper()
        html = '''<html>
        <script id="__NEXT_DATA__" type="application/json">{BROKEN JSON</script>
        <a href="/vehicule-occasion/ford-focus-xyz">Ford</a>
        </html>'''
        sess = _Session([_Resp(200, html)])
        urls = _run(s.fetch_segment(sess, {}, 1))
        assert len(urls) == 1
        assert "ford-focus-xyz" in urls[0]

    def test_subdivide_returns_empty(self):
        from scrapers.portals.caravenue_com import CaravenueFRScraper
        s = CaravenueFRScraper()
        assert s.subdivide_segment({}) == []

    def test_url_format(self):
        from scrapers.portals.caravenue_com import CaravenueFRScraper
        s = CaravenueFRScraper()
        next_data = json.dumps({
            "props": {"pageProps": {"vehicles": [{"url": "/vehicule/test-123"}]}}
        })
        html = f'<html><script id="__NEXT_DATA__" type="application/json">{next_data}</script></html>'
        sess = _Session([_Resp(200, html)])
        _run(s.fetch_segment(sess, {}, 3))
        assert "page=3" in sess.urls_called[0]

    def test_absolute_urls_in_next_data(self):
        from scrapers.portals.caravenue_com import CaravenueFRScraper
        s = CaravenueFRScraper()
        next_data = json.dumps({
            "props": {
                "pageProps": {
                    "vehicles": [
                        {"url": "https://www.caravenue.com/vehicule/full-url-test"},
                    ]
                }
            }
        })
        html = f'<html><script id="__NEXT_DATA__" type="application/json">{next_data}</script></html>'
        sess = _Session([_Resp(200, html)])
        urls = _run(s.fetch_segment(sess, {}, 1))
        assert urls == ["https://www.caravenue.com/vehicule/full-url-test"]

    def test_dedup_html_links(self):
        from scrapers.portals.caravenue_com import CaravenueFRScraper
        s = CaravenueFRScraper()
        html = '''
        <a href="/vehicule-occasion/same-car">Car</a>
        <a href="/vehicule-occasion/same-car">Car again</a>
        <a href="https://www.caravenue.com/vehicule-occasion/same-car">Same absolute</a>
        '''
        sess = _Session([_Resp(200, html)])
        urls = _run(s.fetch_segment(sess, {}, 1))
        assert len(urls) == 1


# ═══════════════════════════════════════════════════════════════════════════════
# simplicicar.com
# ═══════════════════════════════════════════════════════════════════════════════

class TestSimplicicarFR:

    def test_domain_country(self):
        from scrapers.portals.simplicicar_com import SimplicicarFRScraper
        s = SimplicicarFRScraper()
        assert s.DOMAIN == "simplicicar.com"
        assert s.COUNTRY == "FR"

    def test_partition_single_segment(self):
        from scrapers.portals.simplicicar_com import SimplicicarFRScraper
        s = SimplicicarFRScraper()
        params = s.partition_params()
        assert len(params) == 1
        assert params[0] == {}

    def test_fetch_extracts_relative_urls(self):
        from scrapers.portals.simplicicar_com import SimplicicarFRScraper
        s = SimplicicarFRScraper()
        html = '''
        <div class="product-card">
            <a href="/vehicule-occasion/peugeot-308-style-12345">Peugeot 308</a>
            <a href="/vehicule-occasion/renault-clio-zen-67890">Renault Clio</a>
        </div>
        '''
        sess = _Session([_Resp(200, html)])
        urls = _run(s.fetch_segment(sess, {}, 1))
        assert len(urls) == 2
        assert all(u.startswith("https://www.simplicicar.com/vehicule-occasion/") for u in urls)

    def test_fetch_extracts_absolute_urls(self):
        from scrapers.portals.simplicicar_com import SimplicicarFRScraper
        s = SimplicicarFRScraper()
        html = '<a href="https://www.simplicicar.com/vehicule-occasion/bmw-serie3-abc">BMW</a>'
        sess = _Session([_Resp(200, html)])
        urls = _run(s.fetch_segment(sess, {}, 1))
        assert len(urls) == 1
        assert "bmw-serie3-abc" in urls[0]

    def test_fetch_occasion_pattern(self):
        from scrapers.portals.simplicicar_com import SimplicicarFRScraper
        s = SimplicicarFRScraper()
        html = '<a href="/occasion/ford-fiesta-xyz">Ford Fiesta</a>'
        sess = _Session([_Resp(200, html)])
        urls = _run(s.fetch_segment(sess, {}, 1))
        assert len(urls) == 1
        assert "ford-fiesta-xyz" in urls[0]

    def test_non_200_returns_empty(self):
        from scrapers.portals.simplicicar_com import SimplicicarFRScraper
        s = SimplicicarFRScraper()
        sess = _Session([_Resp(500, "Server Error")])
        urls = _run(s.fetch_segment(sess, {}, 1))
        assert urls == []

    def test_subdivide_returns_empty(self):
        from scrapers.portals.simplicicar_com import SimplicicarFRScraper
        s = SimplicicarFRScraper()
        assert s.subdivide_segment({}) == []

    def test_url_format(self):
        from scrapers.portals.simplicicar_com import SimplicicarFRScraper
        s = SimplicicarFRScraper()
        html = '<a href="/vehicule-occasion/test">Test</a>'
        sess = _Session([_Resp(200, html)])
        _run(s.fetch_segment(sess, {}, 5))
        assert "page=5" in sess.urls_called[0]

    def test_dedup_same_url(self):
        from scrapers.portals.simplicicar_com import SimplicicarFRScraper
        s = SimplicicarFRScraper()
        html = '''
        <a href="/vehicule-occasion/same-car">Link 1</a>
        <a href="/vehicule-occasion/same-car">Link 2</a>
        <a href="https://www.simplicicar.com/vehicule-occasion/same-car">Link 3</a>
        '''
        sess = _Session([_Resp(200, html)])
        urls = _run(s.fetch_segment(sess, {}, 1))
        assert len(urls) == 1

    def test_voiture_occasion_pattern(self):
        from scrapers.portals.simplicicar_com import SimplicicarFRScraper
        s = SimplicicarFRScraper()
        html = '<a href="/voiture-occasion/audi-a4-premium">Audi A4</a>'
        sess = _Session([_Resp(200, html)])
        urls = _run(s.fetch_segment(sess, {}, 1))
        assert len(urls) == 1
        assert "audi-a4-premium" in urls[0]

    def test_empty_page_returns_empty(self):
        from scrapers.portals.simplicicar_com import SimplicicarFRScraper
        s = SimplicicarFRScraper()
        sess = _Session([_Resp(200, "<html><body>No results</body></html>")])
        urls = _run(s.fetch_segment(sess, {}, 1))
        assert urls == []
