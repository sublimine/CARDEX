"""
Marktplaats listing extractor tests — vehicles from __NEXT_DATA__.searchRequestAndResponse.listings.

Fixture mirrors the REAL shape captured live 2026-06-09 (priceInfo.priceCents, attributes[],
make from the vipUrl category segment).
"""
from __future__ import annotations

import pytest

from scrapers.portals import marktplaats_listings as mp

NEXT_DATA = {"props": {"pageProps": {"searchRequestAndResponse": {
    "totalResultCount": 264907,
    "listings": [
        {"itemId": "m2401933879",
         "vipUrl": "/v/auto-s/citroen/m2401933879-citroen-c3-aircross-1-2-feel-2020",
         "priceInfo": {"priceCents": 899900, "priceType": "FIXED"},
         "attributes": [
             {"key": "constructionYear", "value": "2020"},
             {"key": "mileage", "value": "166967", "unit": "km"},
             {"key": "fuel", "value": "Benzine"},
             {"key": "transmission", "value": "Handgeschakeld"},
             {"key": "model", "value": "C3 Aircross"},
         ]},
        {"itemId": "m999",
         "vipUrl": "/v/auto-s/mercedes-benz/m999-mercedes-c200",
         "priceInfo": {"priceCents": 0},
         "attributes": [{"key": "constructionYear", "value": "2018"}, {"key": "model", "value": "C200"}]},
    ]}}}}


@pytest.mark.unit
def test_number_of_results():
    assert mp.number_of_results(NEXT_DATA) == 264907
    assert mp.number_of_results({}) is None


@pytest.mark.unit
def test_parse_listings_full_fields():
    rows = mp.parse_listings(NEXT_DATA)
    assert len(rows) == 2
    r0 = rows[0]
    assert r0["source_url"] == "https://www.marktplaats.nl/v/auto-s/citroen/m2401933879-citroen-c3-aircross-1-2-feel-2020"
    assert r0["source_listing_id"] == "m2401933879"
    assert r0["make"] == "Citroen"             # from vipUrl category segment
    assert r0["model"] == "C3 Aircross"
    assert r0["year"] == 2020
    assert r0["mileage_km"] == 166967
    assert r0["price_raw"] == 8999             # priceCents / 100
    assert r0["fuel_type"] == "Benzine"
    assert r0["transmission"] == "Handgeschakeld"


@pytest.mark.unit
def test_parse_listings_make_with_hyphen_and_zero_price():
    rows = mp.parse_listings(NEXT_DATA)
    r1 = rows[1]
    assert r1["make"] == "Mercedes Benz"       # hyphenated make slug title-cased
    assert r1["price_raw"] is None             # priceCents 0 -> no price


@pytest.mark.unit
def test_parse_listings_empty_and_malformed():
    assert mp.parse_listings({}) == []
    assert mp.parse_listings({"props": {"pageProps": {"searchRequestAndResponse": {"listings": 1}}}}) == []
    nd = {"props": {"pageProps": {"searchRequestAndResponse": {"listings": [{"attributes": []}]}}}}
    assert mp.parse_listings(nd) == []          # no vipUrl -> skipped
