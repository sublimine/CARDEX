"""
Basic tests for meili_enricher extractors. No network.
"""
from __future__ import annotations

from scrapers.discovery.meili_enricher import (
    _extract_jsonld,
    _extract_next_data,
    _extract_nuxt_data,
    _extract_microdata,
    _extract_dealerk_meta,
    _scrape_price,
    _scrape_mileage,
    _scrape_year,
    _clean_title,
    extract,
)


# ── JSON-LD ──────────────────────────────────────────────────────────────────
def test_jsonld_vehicle():
    html = """
    <html><head>
    <script type="application/ld+json">
    {
      "@context":"https://schema.org","@type":"Vehicle",
      "name":"BMW 320i 2020",
      "brand":{"@type":"Brand","name":"BMW"},
      "model":"320i",
      "vehicleModelDate":"2020",
      "mileageFromOdometer":{"@type":"QuantitativeValue","value":45000,"unitCode":"KMT"},
      "offers":{"@type":"Offer","price":"24990","priceCurrency":"EUR"},
      "image":"https://example.de/photo.jpg"
    }
    </script></head></html>
    """
    out = _extract_jsonld(html)
    assert out.get("make") == "BMW"
    assert out.get("model") == "320i"
    assert out.get("year") == 2020
    assert out.get("mileage_km") == 45000
    assert out.get("price_eur") == 24990.0
    assert "photo.jpg" in out.get("image", "")


# ── __NEXT_DATA__ ────────────────────────────────────────────────────────────
def test_next_data():
    html = """
    <script id="__NEXT_DATA__" type="application/json">
    {"props":{"pageProps":{"vehicle":{"make":"Audi","model":"A4","year":2019,"price":18500,"mileage":62000}}}}
    </script>
    """
    out = _extract_next_data(html)
    assert out.get("make") == "Audi"
    assert out.get("model") == "A4"
    assert out.get("year") == 2019
    assert out.get("price_eur") == 18500.0
    assert out.get("mileage_km") == 62000


# ── __NUXT__ ────────────────────────────────────────────────────────────────
def test_nuxt_data_json():
    html = """
    <script>window.__NUXT__={"state":{"vehicle":{"make":"Peugeot","model":"308","year":2021,"price":19990,"mileage":35000}}};</script>
    """
    out = _extract_nuxt_data(html)
    assert out.get("make") == "Peugeot"
    assert out.get("model") == "308"
    assert out.get("year") == 2021
    assert out.get("price_eur") == 19990.0


# ── microdata ──────────────────────────────────────────────────────────────
def test_microdata_vehicle():
    html = """
    <div itemscope itemtype="https://schema.org/Vehicle">
      <meta itemprop="brand" content="Renault" />
      <meta itemprop="model" content="Clio" />
      <meta itemprop="modelDate" content="2022" />
      <meta itemprop="mileageFromOdometer" content="15000" />
      <meta itemprop="price" content="16900" />
      <meta itemprop="fuelType" content="petrol" />
    </div>
    """
    out = _extract_microdata(html)
    assert out.get("make") == "Renault"
    assert out.get("model") == "Clio"
    assert out.get("year") == 2022
    assert out.get("mileage_km") == 15000
    assert out.get("price_eur") == 16900.0


# ── dealerk body class ────────────────────────────────────────────────────
def test_dealerk_body_class():
    html = """
    <body class="home single-car voitures-occasion city-paris make-peugeot model-308-ii fuel-diesel version-active id-123456">
    </body>
    """
    out = _extract_dealerk_meta(html)
    assert out.get("make")
    assert out.get("model")


# ── regex scrapers ────────────────────────────────────────────────────────
def test_scrape_price():
    for text, expected in [
        ("Prix 24 590 €", 24590),
        ("24,590 €", 24590),
        ("24.590 €", 24590),
        ("€ 18990", 18990),
        ("invalid price 99", None),
    ]:
        got = _scrape_price(text)
        if expected is None:
            assert got is None
        else:
            assert got == expected, f"{text!r} → {got} != {expected}"


def test_scrape_mileage():
    assert _scrape_mileage("45 000 km") == 45000
    assert _scrape_mileage("123,456 km") == 123456
    assert _scrape_mileage("no mileage here") is None


def test_clean_title():
    assert "BMW 320i" in _clean_title("BMW 320i | AutoHaus Müller")
    assert "Dacia Sandero ECO-G" in _clean_title("Dacia Sandero ECO-G — Occasion à Paris")


# ── end to end ────────────────────────────────────────────────────────────
def test_extract_full_pipeline():
    html = """
    <html><head>
    <meta property="og:title" content="BMW 320i 2020 - Autohaus Müller" />
    <script type="application/ld+json">
    {"@type":"Vehicle","brand":{"name":"BMW"},"model":"320i","vehicleModelDate":"2020","offers":{"price":"24990","priceCurrency":"EUR"},"mileageFromOdometer":{"value":45000}}
    </script>
    </head><body>
    <h1>BMW 320i 24 990 €</h1>
    <p>45 000 km</p>
    </body></html>
    """
    doc, sold = extract(html, "https://example.de/listing/123")
    assert not sold
    assert doc is not None
    assert doc.get("make") == "BMW"
    assert doc.get("price_eur") == 24990.0


if __name__ == "__main__":
    import sys
    funcs = [g for n, g in globals().items() if n.startswith("test_") and callable(g)]
    passed = 0
    failed = 0
    for f in funcs:
        try:
            f()
            print(f"PASS {f.__name__}")
            passed += 1
        except AssertionError as e:
            print(f"FAIL {f.__name__}: {e}")
            failed += 1
        except Exception as e:
            print(f"ERROR {f.__name__}: {type(e).__name__}: {e}")
            failed += 1
    print(f"\n{passed}/{passed+failed} passed")
    sys.exit(0 if failed == 0 else 1)
