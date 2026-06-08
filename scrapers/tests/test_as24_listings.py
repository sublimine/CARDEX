"""
AutoScout24 listing-page extractor tests — vehicles from __NEXT_DATA__ (faceted_ssr).

Fixture mirrors the REAL props.pageProps.listings shape captured live 2026-06-09
(vehicle.{make,model,variant,fuel,mileageInKm} + tracking.{firstRegistration,mileage,price}).
"""
from __future__ import annotations

import pytest

from scrapers.portals import as24_listings as a24

NEXT_DATA = {
    "props": {"pageProps": {
        "numberOfResults": 93523,
        "listings": [
            {"id": "abc-1", "url": "/offres/ford-ecosport-cat_ma29mo20303-",
             "vehicle": {"make": "Ford", "model": "EcoSport", "modelGroup": "EcoSport",
                         "variant": "Titanium", "modelVersionInput": "1.0 EcoBoost 125ch",
                         "fuel": "Essence", "transmission": "Manuelle", "mileageInKm": "114 135 km"},
             "tracking": {"firstRegistration": "01-2020", "mileage": 114135, "price": 10890},
             "price": {"priceFormatted": "€ 10 890"}},
            {"identifier": "xyz-2", "url": "https://www.autoscout24.fr/offres/vw-golf-2",
             "vehicle": {"make": "Volkswagen", "modelGroup": "Golf", "fuel": "Diesel"},
             "tracking": {"firstRegistration": "2019", "mileage": 80000, "price": 15500}},
        ]}}}


@pytest.mark.unit
def test_extract_next_data_and_number_of_results():
    html = ('<html><script id="__NEXT_DATA__" type="application/json">'
            '{"props":{"pageProps":{"numberOfResults":5}}}</script></html>')
    assert a24.number_of_results(a24.extract_next_data(html)) == 5


@pytest.mark.unit
def test_extract_next_data_absent():
    assert a24.extract_next_data("<html>no next data</html>") == {}
    assert a24.number_of_results({}) is None


@pytest.mark.unit
def test_parse_listings_full_fields():
    rows = a24.parse_listings(NEXT_DATA, base_url="https://www.autoscout24.fr")
    assert len(rows) == 2
    r0 = rows[0]
    assert r0["source_url"] == "https://www.autoscout24.fr/offres/ford-ecosport-cat_ma29mo20303-"
    assert r0["make"] == "Ford" and r0["model"] == "EcoSport"
    assert r0["year"] == 2020            # "01-2020" -> 2020
    assert r0["mileage_km"] == 114135    # numeric tracking field
    assert r0["price_raw"] == 10890      # numeric tracking field, not "€ 10 890"
    assert r0["currency_raw"] == "EUR"
    assert r0["fuel_type"] == "Essence"


@pytest.mark.unit
def test_parse_listings_absolute_url_and_modelgroup_fallback():
    rows = a24.parse_listings(NEXT_DATA, base_url="https://www.autoscout24.fr")
    assert rows[1]["source_url"] == "https://www.autoscout24.fr/offres/vw-golf-2"  # already absolute
    assert rows[1]["model"] == "Golf"     # falls back to modelGroup when model absent
    assert rows[1]["year"] == 2019


@pytest.mark.unit
def test_parse_listings_currency_ch_override():
    rows = a24.parse_listings(NEXT_DATA, base_url="https://www.autoscout24.ch", currency="CHF")
    assert rows[0]["currency_raw"] == "CHF"


@pytest.mark.unit
def test_parse_listings_empty_and_malformed():
    assert a24.parse_listings({}, base_url="x") == []
    assert a24.parse_listings({"props": {"pageProps": {"listings": "nope"}}}, base_url="x") == []
    # a listing with no url is skipped (can't seam it)
    nd = {"props": {"pageProps": {"listings": [{"vehicle": {"make": "X"}}]}}}
    assert a24.parse_listings(nd, base_url="https://x") == []


# ── facet-partition planner (beat the ~4000/segment cap) ──
@pytest.mark.unit
def test_plan_price_partitions_bisects_until_under_cap():
    DENSITY = 0.1  # cars per euro, uniform → 100k over [0, 1_000_000)
    def count_fn(lo, hi):
        return round((hi - lo) * DENSITY)
    segs = a24.plan_price_partitions(count_fn, lo=0, hi=1_000_000, cap=4000)
    assert segs
    assert all(c < 4000 for _, _, c in segs)                 # every leaf under the cap
    assert segs[0][0] == 0 and segs[-1][1] == 1_000_000      # full coverage
    for (a1, b1, _), (a2, b2, _) in zip(segs, segs[1:]):
        assert b1 == a2                                      # contiguous, no gaps/overlaps
    assert abs(sum(c for _, _, c in segs) - 100_000) <= len(segs)  # sum ~ total (rounding)


@pytest.mark.unit
def test_plan_price_partitions_drops_empty_and_terminates_on_dense_spike():
    def count_fn(lo, hi):
        return 0 if lo >= 500_000 else 999_999  # empty upper half; absurd spike lower half
    segs = a24.plan_price_partitions(count_fn, lo=0, hi=1_000_000, cap=4000, min_width=250)
    assert segs                                              # terminates
    assert all(b <= 500_000 for _, b, _ in segs)            # empty half dropped
    assert all((b - a) <= 250 for a, b, _ in segs)          # dense spike floored at min_width
