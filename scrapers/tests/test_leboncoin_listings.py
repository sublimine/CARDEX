"""
leboncoin listing extractor tests — vehicles from __NEXT_DATA__.searchData.ads.

Fixture mirrors the REAL ad shape captured live 2026-06-09 (ad.{url,list_id,price[0],attributes[]}).
"""
from __future__ import annotations

import pytest

from scrapers.portals import leboncoin_listings as lbc

NEXT_DATA = {"props": {"pageProps": {"searchData": {
    "total": 777636,
    "ads": [
        {"list_id": 3207439382, "url": "https://www.leboncoin.fr/ad/voitures/3207439382",
         "subject": "RENAULT Clio 1.5 DCI 90ch Business - 2019", "price": [10990],
         "attributes": [
             {"key": "brand", "value": "Renault", "value_label": "Renault"},
             {"key": "model", "value": "Clio", "value_label": "Clio"},
             {"key": "regdate", "value": "2019", "value_label": "2019"},
             {"key": "mileage", "value": "91000", "value_label": "91000 km"},
             {"key": "fuel", "value": "2", "value_label": "Diesel"},
             {"key": "gearbox", "value": "1", "value_label": "Manuelle"},
             {"key": "u_car_version", "value": "Clio 1.5 dCi", "value_label": "Clio 1.5 dCi 90ch Business"},
             {"key": "vehicule_color", "value": "gris", "value_label": "Gris"},
         ]},
        {"list_id": 2, "url": "/ad/voitures/2", "price": [],
         "attributes": [
             {"key": "brand", "value": "Peugeot", "value_label": "Peugeot"},
             {"key": "model", "value": "208", "value_label": "208"},
             {"key": "regdate", "value": "2021"},
             {"key": "mileage", "value": "30000"},
         ]},
    ]}}}}


@pytest.mark.unit
def test_number_of_results():
    assert lbc.number_of_results(NEXT_DATA) == 777636
    assert lbc.number_of_results({}) is None


@pytest.mark.unit
def test_parse_listings_full_fields():
    rows = lbc.parse_listings(NEXT_DATA)
    assert len(rows) == 2
    r0 = rows[0]
    assert r0["source_url"] == "https://www.leboncoin.fr/ad/voitures/3207439382"
    assert r0["source_listing_id"] == "3207439382"
    assert r0["make"] == "Renault" and r0["model"] == "Clio"
    assert r0["year"] == 2019
    assert r0["mileage_km"] == 91000
    assert r0["price_raw"] == 10990                 # price[0]
    assert r0["fuel_type"] == "Diesel"              # attribute value_label
    assert r0["transmission"] == "Manuelle"


@pytest.mark.unit
def test_parse_listings_relative_url_and_missing_price():
    rows = lbc.parse_listings(NEXT_DATA, base_url="https://www.leboncoin.fr")
    r1 = rows[1]
    assert r1["source_url"] == "https://www.leboncoin.fr/ad/voitures/2"  # relative resolved
    assert r1["price_raw"] is None                   # empty price list
    assert r1["make"] == "Peugeot" and r1["year"] == 2021


@pytest.mark.unit
def test_parse_listings_empty_and_malformed():
    assert lbc.parse_listings({}) == []
    assert lbc.parse_listings({"props": {"pageProps": {"searchData": {"ads": "no"}}}}) == []
    # ad without url is skipped
    nd = {"props": {"pageProps": {"searchData": {"ads": [{"attributes": [{"key": "brand", "value": "X"}]}]}}}}
    assert lbc.parse_listings(nd) == []
