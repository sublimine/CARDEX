"""
Tests for Phase 12 portal scrapers — caravenue.com, simplicicar.com.

Both were migrated in the multi-strategy 2026-06 pass:
  * simplicicar.com → listing-level sitemap (harvest covered in test_sitemap_listing.py);
  * caravenue.com   → internal /api/search-results JSON (the old __NEXT_DATA__ scraper
    extracted 0 — the App-Router page has no such blob).

Coroutines run synchronously via asyncio.run() (engine convention).
"""
from __future__ import annotations

import asyncio
import json
from typing import Any

import pytest

from scrapers.portals import get_scraper
from scrapers.portals.caravenue_com import CaravenueFRScraper
from scrapers.portals.simplicicar_com import SimplicicarFRScraper
from scrapers.portals.sitemap_listing_base import SitemapListingScraper


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


# ── caravenue.com — internal JSON API ────────────────────────────────────────
@pytest.mark.unit
def test_caravenue_config() -> None:
    s = get_scraper("caravenue.com")
    assert isinstance(s, CaravenueFRScraper)
    assert s.DOMAIN == "caravenue.com"
    assert s.COUNTRY == "FR"
    assert s.partition_params() == [{}]
    assert s.subdivide_segment({}) == []


@pytest.mark.unit
def test_caravenue_fetch_extracts_vehicle_slugs() -> None:
    s = CaravenueFRScraper()
    body = json.dumps({"data": {"formatedResponse": {"content": [
        {"componentType": "EventCards", "props": []},
        {"componentType": "Vehicules", "props": [
            {"slug": "audi-a3-12345"},
            {"slug": "bmw-320d-67890"},
        ]},
    ], "pagination": {"totalPages": 2}}}})
    urls = _run(s.fetch_segment(_Session([_Resp(200, body)]), {}, 1))
    assert urls == [
        "https://www.caravenue.com/fr/voiture-occasion/audi-a3-12345",
        "https://www.caravenue.com/fr/voiture-occasion/bmw-320d-67890",
    ]


@pytest.mark.unit
def test_caravenue_fetch_url_carries_page() -> None:
    s = CaravenueFRScraper()
    sess = _Session([_Resp(200, '{"data":{"formatedResponse":{"content":[]}}}')])
    _run(s.fetch_segment(sess, {}, 4))
    assert sess.urls_called[0] == "https://caravenue.com/api/search-results?page=4"


@pytest.mark.unit
def test_caravenue_non_200_returns_empty() -> None:
    s = CaravenueFRScraper()
    assert _run(s.fetch_segment(_Session([_Resp(404, "")]), {}, 1)) == []


# ── simplicicar.com — listing sitemap ────────────────────────────────────────
@pytest.mark.unit
def test_simplicicar_is_sitemap_based() -> None:
    s = get_scraper("simplicicar.com")
    assert isinstance(s, SimplicicarFRScraper)
    assert isinstance(s, SitemapListingScraper)
    assert s.COUNTRY == "FR"
    assert s.SITEMAP_URL == "https://www.simplicicar.com/sitemap.xml"
    # Product pages match; CMS/category pages do not.
    assert s.DETAIL_RE.search("/417/981-audi-q3-35-tdi-20-150-limited-s-tronic.html")
    assert not s.DETAIL_RE.search("/nous-contacter")
    assert not s.DETAIL_RE.search("/981-occasions-lorient")
    s._validate()
