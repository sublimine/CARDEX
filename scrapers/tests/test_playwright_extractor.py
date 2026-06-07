"""E07 playwright_extractor — pure meta extraction + render dispatch (no browser)."""
from __future__ import annotations

import asyncio
from decimal import Decimal

import pytest

from scrapers.pipeline.generic_extractor import FetchResult
from scrapers.pipeline.playwright_extractor import (
    _split_make_model,
    extract_listing_rendered,
    parse_rendered_meta,
    record_from_rendered,
)

_PAD = "<div class='spec'><span>x</span></div>" * 400

# Real autolina.ch meta shape (CH / German labels), verified live.
_AUTOLINA_HTML = (
    "<html><head>"
    '<meta property="og:title" content="SKODA Kamiq 1.5 TSI Monte Carlo DS gebraucht '
    "für CHF 29'500,- auf AUTOLINA\">"
    '<meta name="description" content="SKODA Kamiq 1.5 TSI Monte Carlo DSG Panorama AHK '
    "in 5610 Wohlen / AG kaufen auf AUTOLINA: Occasion / Gebraucht, Benzin, Automatik, "
    "Vorderradantrieb, Kilometer: 10'600 km, Leistung: 150 PS, Preis: CHF 29'500, "
    'Erstzulassung: 01.09.2025, Farbe: Silber, Inserat-ID: 4997584">'
    '<meta property="og:image" content="https://cdn.autolina.ch/img/4997584.jpg">'
    "</head><body><h1>SKODA Kamiq</h1>" + _PAD + "</body></html>"
)

# A FR / EUR SPA shape (different labels + currency).
_FR_HTML = (
    "<html><head>"
    '<meta property="og:title" content="Renault Clio V 1.0 TCe occasion à vendre">'
    '<meta name="description" content="Renault Clio V 1.0 TCe - Kilométrage 45 000 km, '
    'Prix: 14 990 EUR, Mise en circulation 03/2021, Couleur Blanc">'
    '<meta property="og:image" content="https://cdn.fr/clio.jpg">'
    "</head><body>" + _PAD + "</body></html>"
)


@pytest.mark.unit
def test_split_make_model():
    assert _split_make_model("SKODA Kamiq 1.5 TSI gebraucht für CHF 29'500") == ("SKODA", "Kamiq")
    assert _split_make_model("Renault Clio V occasion") == ("Renault", "Clio")
    assert _split_make_model("") == (None, None)


@pytest.mark.unit
def test_parse_rendered_meta_ch_german():
    raw = parse_rendered_meta(_AUTOLINA_HTML)
    assert raw["make"] == "SKODA" and raw["model"] == "Kamiq"
    assert raw["price"] == "29500" and raw["currency"] == "CHF"
    assert raw["mileage"] == "10600"           # NOT the '600' the static heuristic grabbed
    assert raw["year"] == "2025"
    assert raw["images"] == ["https://cdn.autolina.ch/img/4997584.jpg"]


@pytest.mark.unit
def test_parse_rendered_meta_fr_eur():
    raw = parse_rendered_meta(_FR_HTML)
    assert raw["make"] == "Renault" and raw["model"] == "Clio"
    assert raw["price"] == "14990" and raw["currency"] == "EUR"
    assert raw["mileage"] == "45000"
    assert raw["year"] == "2021"


@pytest.mark.unit
def test_record_from_rendered_ch_has_critical_and_chf():
    rec, reason = record_from_rendered(
        _AUTOLINA_HTML, source_url="https://www.autolina.ch/auto/skoda-kamiq/4997584",
        source_domain="autolina.ch", country="CH",
    )
    assert reason == "ok" and rec is not None
    assert rec.make == "SKODA" and rec.model == "Kamiq" and rec.year == 2025
    assert rec.price == Decimal("29500") and rec.currency == "CHF"
    assert rec.mileage_km == 10600 and len(rec.images) >= 1
    assert rec.has_critical_fields()


@pytest.mark.unit
def test_record_from_rendered_empty_page_rejected():
    rec, reason = record_from_rendered(
        "<html><head></head><body>nothing here</body></html>",
        source_url="https://x.ch/a/1", source_domain="x.ch", country="CH",
    )
    assert rec is None and reason in ("no_fields",) or reason.startswith("missing_critical")


@pytest.mark.unit
def test_extract_listing_rendered_via_injected_fetcher():
    # E07 dispatch with an in-memory "rendered HTML" fetcher (no browser).
    url = "https://www.autolina.ch/auto/skoda-kamiq/4997584"

    async def fake_fetcher(u):
        return FetchResult(url=u, status_code=200, body=_AUTOLINA_HTML.encode("utf-8"))

    rec, reason = asyncio.run(extract_listing_rendered(url, fake_fetcher, country="CH",
                                                       source_domain="autolina.ch"))
    assert reason == "ok" and rec is not None and rec.make == "SKODA"


@pytest.mark.unit
def test_extract_listing_rendered_transport_fault_is_transient():
    async def boom(u):
        raise ConnectionError("down")

    rec, reason = asyncio.run(extract_listing_rendered("https://x.ch/1", boom, country="CH"))
    assert rec is None and reason.startswith("fetch_error")


# ── config-driven dispatch in the seam (enrich_one routes by config) ───────────
@pytest.mark.unit
def test_enrich_one_routes_playwright_source_to_e07():
    # autolina.ch config selects strategy 'playwright_meta' → enrich_one must use
    # the injected e07_fetcher (rendered HTML), NOT the static fetcher.
    from scrapers import enrich_worker as ew

    async def static_fetcher(u):  # would 404 / give no JSON-LD on a SPA
        return FetchResult(url=u, status_code=200, body=b"<html><body>spa shell</body></html>")

    async def e07_fetcher(u):
        return FetchResult(url=u, status_code=200, body=_AUTOLINA_HTML.encode("utf-8"))

    fields = {"h": "H1", "u": "https://www.autolina.ch/auto/skoda-kamiq/4997584",
              "s": "autolina.ch", "c": "CH"}
    payload, reason = asyncio.run(ew.enrich_one(fields, static_fetcher, e07_fetcher=e07_fetcher))
    assert reason == "ok" and payload is not None
    assert payload["make"] == "SKODA" and payload["currency_raw"] == "CHF"
    assert payload["source_country"] == "CH"


_JSONLD_HTML = (
    "<html><head>"
    '<script type="application/ld+json">{"@context":"https://schema.org","@type":"Car",'
    '"brand":{"name":"Audi"},"model":"A3","vehicleModelDate":"2020",'
    '"mileageFromOdometer":{"value":"40000"},"image":["https://c/1.jpg"],'
    '"offers":{"@type":"Offer","price":"21950","priceCurrency":"EUR"}}</script>'
    "</head><body>" + _PAD + "</body></html>"
)


@pytest.mark.unit
def test_enrich_one_static_source_ignores_e07():
    # A source with NO playwright config stays on the static path (JSON-LD) even
    # when an e07_fetcher is available — the e07 path must NOT be taken.
    from scrapers import enrich_worker as ew

    async def static_fetcher(u):
        return FetchResult(url=u, status_code=200, body=_JSONLD_HTML.encode("utf-8"))

    async def e07_fetcher(u):  # must not be used
        raise AssertionError("e07_fetcher used for a non-playwright source")

    fields = {"h": "H2", "u": "https://x.nl/a/1", "s": "no-config-portal.nl", "c": "NL"}
    payload, reason = asyncio.run(ew.enrich_one(fields, static_fetcher, e07_fetcher=e07_fetcher))
    assert reason == "ok" and payload is not None       # static path ran (no AssertionError)
    assert payload["make"] == "Audi" and payload["currency_raw"] == "EUR"


@pytest.mark.unit
def test_is_playwright_source_reads_config():
    from scrapers.enrich_worker import _is_playwright_source
    assert _is_playwright_source("autolina.ch") is True
    assert _is_playwright_source("autotrack.nl") is False     # static config
    assert _is_playwright_source("no-such-portal.zz") is False
