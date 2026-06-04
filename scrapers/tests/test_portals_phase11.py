"""Tests for Phase 11 T2/T3 portal scrapers — gocar.be, milanuncios.com, zoomcar.fr, coches.com."""
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
# gocar.be
# ═══════════════════════════════════════════════════════════════════════════════

class TestGocarBE:
    def test_domain_country(self):
        from scrapers.portals.gocar_be import GocarBEScraper
        s = GocarBEScraper()
        assert s.DOMAIN == "gocar.be"
        assert s.COUNTRY == "BE"

    def test_partition_produces_brand_lang_pairs(self):
        from scrapers.portals.gocar_be import GocarBEScraper
        s = GocarBEScraper()
        params = s.partition_params()
        assert len(params) > 0
        # Every param has lang and brand
        for p in params:
            assert "lang" in p
            assert "brand" in p
        # Both languages present
        langs = {p["lang"] for p in params}
        assert "nl" in langs
        assert "fr" in langs

    def test_fetch_sitemap_extracts_urls(self):
        from scrapers.portals.gocar_be import GocarBEScraper
        xml = """<?xml version="1.0" encoding="UTF-8"?>
        <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
            <url><loc>https://www.gocar.be/nl/tweedehands/audi/a3-123456</loc></url>
            <url><loc>https://www.gocar.be/nl/tweedehands/audi/a4-789012</loc></url>
            <url><loc>https://www.gocar.be/nl/merken/audi</loc></url>
        </urlset>"""
        sess = _Session([_Resp(200, xml)])
        s = GocarBEScraper()
        urls = _run(s.fetch_segment(sess, {"lang": "nl", "brand": "audi"}, 1))
        # Only listing URLs (containing /tweedehands/), not the brand index page
        assert len(urls) == 2
        assert all("/tweedehands/" in u for u in urls)

    def test_fetch_404_returns_empty(self):
        from scrapers.portals.gocar_be import GocarBEScraper
        sess = _Session([_Resp(404, "")])
        s = GocarBEScraper()
        urls = _run(s.fetch_segment(sess, {"lang": "nl", "brand": "nonexistent"}, 1))
        assert urls == []

    def test_fetch_fr_language_urls(self):
        from scrapers.portals.gocar_be import GocarBEScraper
        xml = """<?xml version="1.0"?>
        <urlset>
            <url><loc>https://www.gocar.be/fr/voitures-occasion/bmw/x3-456</loc></url>
        </urlset>"""
        sess = _Session([_Resp(200, xml)])
        s = GocarBEScraper()
        urls = _run(s.fetch_segment(sess, {"lang": "fr", "brand": "bmw"}, 1))
        assert len(urls) == 1
        assert "/voitures-occasion/" in urls[0]

    def test_subdivide_returns_empty(self):
        from scrapers.portals.gocar_be import GocarBEScraper
        s = GocarBEScraper()
        assert s.subdivide_segment({"lang": "nl", "brand": "audi"}) == []

    def test_url_format(self):
        from scrapers.portals.gocar_be import GocarBEScraper
        sess = _Session()
        s = GocarBEScraper()
        _run(s.fetch_segment(sess, {"lang": "nl", "brand": "audi"}, 1))
        assert sess.urls_called[0] == "https://www.gocar.be/sitemaps/vehicles-nl-audi.xml"

    def test_empty_sitemap(self):
        from scrapers.portals.gocar_be import GocarBEScraper
        xml = '<?xml version="1.0"?><urlset></urlset>'
        sess = _Session([_Resp(200, xml)])
        s = GocarBEScraper()
        urls = _run(s.fetch_segment(sess, {"lang": "nl", "brand": "audi"}, 1))
        assert urls == []


# ═══════════════════════════════════════════════════════════════════════════════
# milanuncios.com
# ═══════════════════════════════════════════════════════════════════════════════

def _milanuncios_page(ads: list[dict]) -> str:
    """Build a minimal Next.js SSR page with __NEXT_DATA__."""
    data = {
        "props": {
            "pageProps": {
                "listingCards": ads,
            }
        }
    }
    return f'<html><script id="__NEXT_DATA__" type="application/json">{json.dumps(data)}</script></html>'


class TestMilanunciosES:
    def test_domain_country(self):
        from scrapers.portals.milanuncios_com import MilanunciosESScraper
        s = MilanunciosESScraper()
        assert s.DOMAIN == "milanuncios.com"
        assert s.COUNTRY == "ES"

    def test_partition_produces_price_bands(self):
        from scrapers.portals.milanuncios_com import MilanunciosESScraper
        s = MilanunciosESScraper()
        params = s.partition_params()
        assert len(params) >= 10
        for p in params:
            assert "price_from" in p
            assert "price_to" in p or p.get("price_to") is None

    def test_fetch_extracts_urls_from_next_data(self):
        from scrapers.portals.milanuncios_com import MilanunciosESScraper
        ads = [
            {"id": "123", "url": "/coches-de-segunda-mano/audi-a3-123"},
            {"id": "456", "url": "/coches-de-segunda-mano/bmw-320-456"},
        ]
        html = _milanuncios_page(ads)
        sess = _Session([_Resp(200, html)])
        s = MilanunciosESScraper()
        urls = _run(s.fetch_segment(sess, {"price_from": 0, "price_to": 2000}, 1))
        assert len(urls) == 2
        assert all("milanuncios.com" in u for u in urls)

    def test_fetch_with_detail_url_field(self):
        from scrapers.portals.milanuncios_com import MilanunciosESScraper
        ads = [{"id": "789", "detailUrl": "https://www.milanuncios.com/789"}]
        html = _milanuncios_page(ads)
        sess = _Session([_Resp(200, html)])
        s = MilanunciosESScraper()
        urls = _run(s.fetch_segment(sess, {"price_from": 0, "price_to": 2000}, 1))
        assert len(urls) == 1
        assert "789" in urls[0]

    def test_fetch_fallback_to_id(self):
        from scrapers.portals.milanuncios_com import MilanunciosESScraper
        ads = [{"id": "abc123"}]
        html = _milanuncios_page(ads)
        sess = _Session([_Resp(200, html)])
        s = MilanunciosESScraper()
        urls = _run(s.fetch_segment(sess, {"price_from": 0, "price_to": 2000}, 1))
        assert len(urls) == 1
        assert "abc123" in urls[0]

    def test_datadome_challenge_returns_empty(self):
        from scrapers.portals.milanuncios_com import MilanunciosESScraper
        html = '<html><body>DataDome challenge <iframe src="geo.captcha-delivery.com"></iframe></body></html>'
        sess = _Session([_Resp(200, html)])
        s = MilanunciosESScraper()
        urls = _run(s.fetch_segment(sess, {"price_from": 0, "price_to": 2000}, 1))
        assert urls == []

    def test_non_200_returns_empty(self):
        from scrapers.portals.milanuncios_com import MilanunciosESScraper
        sess = _Session([_Resp(403, "Forbidden")])
        s = MilanunciosESScraper()
        urls = _run(s.fetch_segment(sess, {"price_from": 0, "price_to": 2000}, 1))
        assert urls == []

    def test_no_next_data_returns_empty(self):
        from scrapers.portals.milanuncios_com import MilanunciosESScraper
        sess = _Session([_Resp(200, "<html><body>No data</body></html>")])
        s = MilanunciosESScraper()
        urls = _run(s.fetch_segment(sess, {"price_from": 0, "price_to": 2000}, 1))
        assert urls == []

    def test_subdivide_splits_price_band(self):
        from scrapers.portals.milanuncios_com import MilanunciosESScraper
        s = MilanunciosESScraper()
        subs = s.subdivide_segment({"price_from": 0, "price_to": 10_000})
        assert len(subs) == 2
        assert subs[0]["price_from"] == 0
        assert subs[0]["price_to"] == 5_000
        assert subs[1]["price_from"] == 5_000
        assert subs[1]["price_to"] == 10_000

    def test_subdivide_narrow_band_returns_empty(self):
        from scrapers.portals.milanuncios_com import MilanunciosESScraper
        s = MilanunciosESScraper()
        subs = s.subdivide_segment({"price_from": 5000, "price_to": 5500})
        assert subs == []

    def test_url_format_with_price(self):
        from scrapers.portals.milanuncios_com import MilanunciosESScraper
        sess = _Session([_Resp(200, "")])
        s = MilanunciosESScraper()
        _run(s.fetch_segment(sess, {"price_from": 5000, "price_to": 10000}, 3))
        url = sess.urls_called[0]
        assert "pagina=3" in url
        assert "desde=5000" in url
        assert "hasta=10000" in url

    def test_relative_urls_get_prefix(self):
        from scrapers.portals.milanuncios_com import MilanunciosESScraper
        ads = [{"url": "/coches/test-123"}]
        html = _milanuncios_page(ads)
        sess = _Session([_Resp(200, html)])
        s = MilanunciosESScraper()
        urls = _run(s.fetch_segment(sess, {"price_from": 0, "price_to": 2000}, 1))
        assert urls[0].startswith("https://www.milanuncios.com/")

    def test_ads_list_alternative_field(self):
        from scrapers.portals.milanuncios_com import MilanunciosESScraper
        data = {"props": {"pageProps": {"adsList": [{"url": "/test-ad"}]}}}
        html = f'<html><script id="__NEXT_DATA__" type="application/json">{json.dumps(data)}</script></html>'
        sess = _Session([_Resp(200, html)])
        s = MilanunciosESScraper()
        urls = _run(s.fetch_segment(sess, {"price_from": 0, "price_to": 2000}, 1))
        assert len(urls) == 1


# ═══════════════════════════════════════════════════════════════════════════════
# zoomcar.fr
# ═══════════════════════════════════════════════════════════════════════════════

class TestZoomcarFR:
    def test_domain_country(self):
        from scrapers.portals.zoomcar_fr import ZoomcarFRScraper
        s = ZoomcarFRScraper()
        assert s.DOMAIN == "zoomcar.fr"
        assert s.COUNTRY == "FR"

    def test_partition_produces_price_bands(self):
        from scrapers.portals.zoomcar_fr import ZoomcarFRScraper
        s = ZoomcarFRScraper()
        params = s.partition_params()
        assert len(params) >= 8
        for p in params:
            assert "price_min" in p

    def test_fetch_extracts_relative_urls(self):
        from scrapers.portals.zoomcar_fr import ZoomcarFRScraper
        html = '''<div class="results">
            <a href="/occasion/annonce/audi-a3-12345">Audi A3</a>
            <a href="/occasion/annonce/bmw-320-67890">BMW 320</a>
        </div>'''
        sess = _Session([_Resp(200, html)])
        s = ZoomcarFRScraper()
        urls = _run(s.fetch_segment(sess, {"price_min": 0, "price_max": 3000}, 1))
        assert len(urls) == 2
        assert all("zoomcar.fr" in u for u in urls)

    def test_fetch_extracts_absolute_urls(self):
        from scrapers.portals.zoomcar_fr import ZoomcarFRScraper
        html = '<a href="https://www.zoomcar.fr/voiture/annonce/peugeot-208-111">Peugeot</a>'
        sess = _Session([_Resp(200, html)])
        s = ZoomcarFRScraper()
        urls = _run(s.fetch_segment(sess, {"price_min": 0, "price_max": 3000}, 1))
        assert len(urls) == 1

    def test_cf_challenge_returns_empty(self):
        from scrapers.portals.zoomcar_fr import ZoomcarFRScraper
        html = '<html><body>Just a moment... challenge-platform</body></html>'
        sess = _Session([_Resp(200, html)])
        s = ZoomcarFRScraper()
        urls = _run(s.fetch_segment(sess, {"price_min": 0, "price_max": 3000}, 1))
        assert urls == []

    def test_non_200_returns_empty(self):
        from scrapers.portals.zoomcar_fr import ZoomcarFRScraper
        sess = _Session([_Resp(403, "")])
        s = ZoomcarFRScraper()
        urls = _run(s.fetch_segment(sess, {"price_min": 0, "price_max": 3000}, 1))
        assert urls == []

    def test_subdivide_splits_band(self):
        from scrapers.portals.zoomcar_fr import ZoomcarFRScraper
        s = ZoomcarFRScraper()
        subs = s.subdivide_segment({"price_min": 0, "price_max": 10_000})
        assert len(subs) == 2
        assert subs[0]["price_min"] == 0
        assert subs[0]["price_max"] == 5_000

    def test_subdivide_narrow_returns_empty(self):
        from scrapers.portals.zoomcar_fr import ZoomcarFRScraper
        s = ZoomcarFRScraper()
        assert s.subdivide_segment({"price_min": 5000, "price_max": 5500}) == []

    def test_url_format(self):
        from scrapers.portals.zoomcar_fr import ZoomcarFRScraper
        sess = _Session([_Resp(200, "")])
        s = ZoomcarFRScraper()
        _run(s.fetch_segment(sess, {"price_min": 5000, "price_max": 10000}, 2))
        url = sess.urls_called[0]
        assert "page=2" in url
        assert "prix_min=5000" in url
        assert "prix_max=10000" in url

    def test_dedup_same_url(self):
        from scrapers.portals.zoomcar_fr import ZoomcarFRScraper
        html = '''
            <a href="/occasion/annonce/audi-a3-123">Audi</a>
            <a href="https://www.zoomcar.fr/occasion/annonce/audi-a3-123">Audi dup</a>
        '''
        sess = _Session([_Resp(200, html)])
        s = ZoomcarFRScraper()
        urls = _run(s.fetch_segment(sess, {"price_min": 0, "price_max": 3000}, 1))
        assert len(urls) == 1


# ═══════════════════════════════════════════════════════════════════════════════
# coches.com
# ═══════════════════════════════════════════════════════════════════════════════

class TestCochesComES:
    def test_domain_country(self):
        from scrapers.portals.coches_com import CochesComESScraper
        s = CochesComESScraper()
        assert s.DOMAIN == "coches.com"
        assert s.COUNTRY == "ES"

    def test_partition_produces_price_bands(self):
        from scrapers.portals.coches_com import CochesComESScraper
        s = CochesComESScraper()
        params = s.partition_params()
        assert len(params) >= 5
        for p in params:
            assert "price_from" in p

    def test_fetch_extracts_urls(self):
        from scrapers.portals.coches_com import CochesComESScraper
        html = '''<div>
            <a href="/coches/oferta/audi-a3-12345">Audi A3</a>
            <a href="/coches/anuncio/bmw-320-67890">BMW 320</a>
        </div>'''
        sess = _Session([_Resp(200, html)])
        s = CochesComESScraper()
        urls = _run(s.fetch_segment(sess, {"price_from": 0, "price_to": 3000}, 1))
        assert len(urls) == 2
        assert all("coches.com" in u for u in urls)

    def test_cf_challenge_returns_empty(self):
        from scrapers.portals.coches_com import CochesComESScraper
        html = '<html>Just a moment... challenge-platform</html>'
        sess = _Session([_Resp(200, html)])
        s = CochesComESScraper()
        urls = _run(s.fetch_segment(sess, {"price_from": 0, "price_to": 3000}, 1))
        assert urls == []

    def test_non_200_returns_empty(self):
        from scrapers.portals.coches_com import CochesComESScraper
        sess = _Session([_Resp(403, "")])
        s = CochesComESScraper()
        urls = _run(s.fetch_segment(sess, {"price_from": 0, "price_to": 3000}, 1))
        assert urls == []

    def test_subdivide_splits_band(self):
        from scrapers.portals.coches_com import CochesComESScraper
        s = CochesComESScraper()
        subs = s.subdivide_segment({"price_from": 0, "price_to": 10_000})
        assert len(subs) == 2

    def test_url_format(self):
        from scrapers.portals.coches_com import CochesComESScraper
        sess = _Session([_Resp(200, "")])
        s = CochesComESScraper()
        _run(s.fetch_segment(sess, {"price_from": 5000, "price_to": 10000}, 2))
        url = sess.urls_called[0]
        assert "pg=2" in url
        assert "precio_desde=5000" in url
        assert "precio_hasta=10000" in url

    def test_no_listings_returns_empty(self):
        from scrapers.portals.coches_com import CochesComESScraper
        sess = _Session([_Resp(200, "<html><body>No results</body></html>")])
        s = CochesComESScraper()
        urls = _run(s.fetch_segment(sess, {"price_from": 0, "price_to": 3000}, 1))
        assert urls == []
