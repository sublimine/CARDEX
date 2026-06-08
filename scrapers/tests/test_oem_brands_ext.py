"""OEM brands extension parsers — pure transforms over verified sample shapes.

Fixtures sourced from live API responses verified 2026-06-07:
  - Cupra DE: cupraofficial.de SNW XML (curl + python urllib, 98 total / 59 cupra_specialized)
  - Cupra BE: D'Ieteren workLocations templateId=202 (69 dealers, CUPRA brand)

No network calls.  All test inputs are minimal faithful reproductions of real
API payloads (only keys that the parsers actually read are included).
"""
from __future__ import annotations

import xml.etree.ElementTree as ET

import pytest

from scrapers.discovery.sources import oem_brands_ext as ext


# ── helpers ──────────────────────────────────────────────────────────────────

def _xml_partner(**fields: str) -> ET.Element:
    """Build a minimal <partner> element from keyword arguments."""
    root = ET.Element("partner")
    for tag, text in fields.items():
        el = ET.SubElement(root, tag)
        el.text = text
    return root


# ── parse_cupra_snw_dealer ────────────────────────────────────────────────────

@pytest.mark.unit
def test_parse_cupra_snw_with_url():
    """cupra_specialized=true with URL → domain extracted, all fields mapped.

    Fixture from: cupraofficial.de SNW XML, partner DEN21MS (DE, verified live).
    """
    el = _xml_partner(
        partner_id="DEN21MS",
        name="Autohaus Ostmann Melsungen GmbH",
        street="Nürnberger Str., 52-54",
        city="Melsungen",
        zip_code="34212",
        phone1="05661-7055-0",
        email="d41023@seatpartner.de",
        url="www.autohaus-ostmann.de",
        cupra_specialized="true",
        installation_code_kvps="81023",
    )
    c = ext.parse_cupra_snw_dealer(el, "DE")
    assert c is not None
    assert c["source"] == "oem:cupra"
    assert c["source_layer"] == 1
    assert c["country"] == "DE"
    assert c["domain"] == "autohaus-ostmann.de"
    assert c["url"] == "https://www.autohaus-ostmann.de"
    assert c["name"] == "Autohaus Ostmann Melsungen GmbH"
    assert c["address"] == "Nürnberger Str., 52-54"
    assert c["city"] == "Melsungen"
    assert c["postcode"] == "34212"
    assert c["phone"] == "05661-7055-0"
    assert c["email"] == "d41023@seatpartner.de"
    assert c["registry_id"] == "DEN21MS"
    assert c["lat"] is None   # SNW does not embed coordinates
    assert c["lng"] is None
    assert c["external_refs"]["partner_id"] == "DEN21MS"
    assert c["external_refs"]["installation_code_kvps"] == "81023"


@pytest.mark.unit
def test_parse_cupra_snw_without_url():
    """cupra_specialized=true without URL → domain=None, identity row still valid.

    Fixture from: cupraofficial.de SNW XML, partner DEO15MS (DE, verified live).
    """
    el = _xml_partner(
        partner_id="DEO15MS",
        name="Ehrhardt AG NL Eisenach",
        street="Neue Wiese, 1",
        city="Eisenach",
        zip_code="99817",
        phone1="03691-724489-0",
        email="03691-724489-0",
        url="",
        cupra_specialized="true",
        installation_code_kvps="81039",
    )
    c = ext.parse_cupra_snw_dealer(el, "DE")
    assert c is not None
    assert c["domain"] is None
    assert c["url"] is None
    assert c["registry_id"] == "DEO15MS"
    assert c["city"] == "Eisenach"


@pytest.mark.unit
def test_parse_cupra_snw_not_specialized_rejected():
    """cupra_specialized=false → returns None (not a Cupra dealer).

    Fixture from: cupraofficial.de SNW XML, partner DES55CG (DE, verified live).
    """
    el = _xml_partner(
        partner_id="DES55CG",
        name="Ehrhardt AG NL Eisenach",
        cupra_specialized="false",
    )
    assert ext.parse_cupra_snw_dealer(el, "DE") is None


@pytest.mark.unit
def test_parse_cupra_snw_missing_field_rejected():
    """Missing cupra_specialized field → returns None (treated as not specialized)."""
    el = _xml_partner(
        partner_id="DEN99XX",
        name="Some Dealer",
    )
    assert ext.parse_cupra_snw_dealer(el, "DE") is None


@pytest.mark.unit
def test_parse_cupra_snw_missing_name_rejected():
    """cupra_specialized=true but no name → returns None."""
    el = _xml_partner(
        partner_id="DEN99YY",
        cupra_specialized="true",
        url="www.somedealer.de",
    )
    assert ext.parse_cupra_snw_dealer(el, "DE") is None


@pytest.mark.unit
def test_parse_cupra_snw_url_with_leading_space():
    """URL with surrounding whitespace (seen in live data) is normalized."""
    el = _xml_partner(
        partner_id="DEO16D",
        name="Some Dealer Eisenach",
        url=" https://eisenach.seat.de/ ",
        cupra_specialized="true",
    )
    c = ext.parse_cupra_snw_dealer(el, "DE")
    assert c is not None
    assert c["url"] == "https://eisenach.seat.de"
    assert c["domain"] == "eisenach.seat.de"


@pytest.mark.unit
def test_parse_cupra_snw_country_propagated():
    """country parameter is stored as-is in the candidate dict."""
    el = _xml_partner(
        partner_id="NL001",
        name="Dealer NL",
        cupra_specialized="true",
        url="www.dealer.nl",
    )
    c = ext.parse_cupra_snw_dealer(el, "NL")
    assert c is not None
    assert c["country"] == "NL"


# ── parse_cupra_be_dealer ─────────────────────────────────────────────────────

@pytest.mark.unit
def test_parse_cupra_be_with_url():
    """D'Ieteren dealer with URL → domain extracted, lat/lng parsed as floats.

    Fixture from: D'Ieteren workLocations templateId=202, WOLO000174 (BE, verified live).
    """
    d = {
        "WorkLocationId": "WOLO000174",
        "NAME": "D'Ieteren Mobility Center Antwerpen",
        "ADDRESS": "Groenendaallaan, 397",
        "ZIP": "2030",
        "CITY": "ANTWERPEN",
        "TEL": "+3232315930",
        "MAIL": "Service.antwerpen@dieterenmobilitycompany.be",
        "URL": "www.dieterenmobilitycompany.be",
        "GPSLAT": "51.244506",
        "GPSLONG": "4.416354",
        "BRANDNAME": "CUPRA",
    }
    c = ext.parse_cupra_be_dealer(d)
    assert c is not None
    assert c["source"] == "oem:cupra"
    assert c["source_layer"] == 1
    assert c["country"] == "BE"
    assert c["domain"] == "dieterenmobilitycompany.be"
    assert c["url"] == "https://www.dieterenmobilitycompany.be"
    assert c["name"] == "D'Ieteren Mobility Center Antwerpen"
    assert c["address"] == "Groenendaallaan, 397"
    assert c["postcode"] == "2030"
    assert c["city"] == "ANTWERPEN"
    assert c["phone"] == "+3232315930"
    assert c["email"] == "Service.antwerpen@dieterenmobilitycompany.be"
    assert c["lat"] == pytest.approx(51.244506)
    assert c["lng"] == pytest.approx(4.416354)
    assert c["registry_id"] == "WOLO000174"
    assert c["external_refs"]["work_location_id"] == "WOLO000174"


@pytest.mark.unit
def test_parse_cupra_be_without_url():
    """D'Ieteren dealer without URL → domain=None, identity row.

    Fixture from: D'Ieteren workLocations templateId=202, WOLO000274 (BE, verified live).
    """
    d = {
        "WorkLocationId": "WOLO000274",
        "NAME": "Steveny Namur",
        "ADDRESS": "Rue Des Phlox, 1",
        "ZIP": "5100",
        "CITY": "Naninne",
        "TEL": "+3281408530",
        "MAIL": None,
        "URL": "",
        "GPSLAT": "50.425785",
        "GPSLONG": "4.921438",
        "BRANDNAME": "CUPRA",
    }
    c = ext.parse_cupra_be_dealer(d)
    assert c is not None
    assert c["domain"] is None
    assert c["url"] is None
    assert c["registry_id"] == "WOLO000274"
    assert c["lat"] == pytest.approx(50.425785)
    assert c["lng"] == pytest.approx(4.921438)
    assert c["city"] == "Naninne"
    assert c["email"] is None


@pytest.mark.unit
def test_parse_cupra_be_missing_name_rejected():
    """Dealer with empty/missing NAME → returns None."""
    assert ext.parse_cupra_be_dealer({"WorkLocationId": "WOLO999", "NAME": ""}) is None
    assert ext.parse_cupra_be_dealer({"WorkLocationId": "WOLO999"}) is None


@pytest.mark.unit
def test_parse_cupra_be_invalid_gps_tolerant():
    """Non-numeric GPSLAT/GPSLONG → lat/lng = None (no crash)."""
    d = {
        "WorkLocationId": "WOLO001",
        "NAME": "Test Dealer",
        "GPSLAT": "N/A",
        "GPSLONG": "",
        "URL": "",
    }
    c = ext.parse_cupra_be_dealer(d)
    assert c is not None
    assert c["lat"] is None
    assert c["lng"] is None


# ── helper function tests ─────────────────────────────────────────────────────

@pytest.mark.unit
def test_normalize_url_bare_domain():
    assert ext._normalize_url("www.autohaus-ostmann.de") == "https://www.autohaus-ostmann.de"


@pytest.mark.unit
def test_normalize_url_strips_trailing_slash():
    assert ext._normalize_url("https://www.example.de/") == "https://www.example.de"


@pytest.mark.unit
def test_normalize_url_none_returns_none():
    assert ext._normalize_url(None) is None
    assert ext._normalize_url("") is None
    assert ext._normalize_url("  ") is None


@pytest.mark.unit
def test_domain_strips_www():
    assert ext._domain("https://www.autohaus-ostmann.de") == "autohaus-ostmann.de"


@pytest.mark.unit
def test_domain_none_url_returns_none():
    assert ext._domain(None) is None


@pytest.mark.unit
def test_f_converts_string_float():
    assert ext._f("51.244506") == pytest.approx(51.244506)
    assert ext._f(None) is None
    assert ext._f("") is None
    assert ext._f("N/A") is None
