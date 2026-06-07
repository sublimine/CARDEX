"""OEM Wave 2 parsers — pure transforms over verified sample shapes (no network).

Fixtures sourced from live API responses verified 2026-06-07 (see AUDIT_SCRATCH/oem_wave2.md).
"""
from __future__ import annotations

import xml.etree.ElementTree as ET

import pytest

from scrapers.discovery.sources import oem_wave2 as w2


# ── Renault / Dacia ──────────────────────────────────────────────────────────
@pytest.mark.unit
def test_parse_renault_dealer_with_dwslink():
    """Dealer with dwsLink → domain extracted, registry_id = birId_siteId."""
    d = {
        "dealerId": "25003640_001",
        "name": "RENAULT RNLT PARIS SAINT-GERMAIN RRG",
        "birId": "25003640",
        "siteId": "001",
        "streetAddress": "Boulevard saint germain",
        "locality": "PARIS",
        "postalCode": "75006",
        "geolocalization": {"lat": 48.85128, "lon": 2.34216},
        "renault": {
            "dwsLink": "https://concessionnaire.renault.fr/rnlt-saint-germain.html",
            "withDws": True,
            "dwsActive": True,
            "telephone": {"value": "+33170992200"},
        },
    }
    c = w2.parse_renault_dealer(d, "FR", "renault")
    assert c is not None
    assert c["source"] == "oem:renault"
    assert c["country"] == "FR"
    assert c["domain"] == "concessionnaire.renault.fr"
    assert c["url"] == "https://concessionnaire.renault.fr/rnlt-saint-germain.html"
    assert c["registry_id"] == "25003640_001"
    assert c["lat"] == 48.85128
    assert c["lng"] == 2.34216
    assert c["city"] == "PARIS"
    assert c["postcode"] == "75006"
    assert c["external_refs"]["bir_id"] == "25003640"
    assert c["external_refs"]["site_id"] == "001"


@pytest.mark.unit
def test_parse_renault_dealer_no_dwslink():
    """Dealer without dwsLink → domain=None, identity row."""
    d = {
        "dealerId": "27000001_001",
        "name": "Autohaus Muster GmbH",
        "birId": "27000001",
        "siteId": "001",
        "locality": "Berlin",
        "postalCode": "10115",
        "geolocalization": {"lat": 52.52, "lon": 13.40},
        "renault": {"withDws": False},
    }
    c = w2.parse_renault_dealer(d, "DE", "renault")
    assert c is not None
    assert c["domain"] is None
    assert c["url"] is None
    assert c["registry_id"] == "27000001_001"


@pytest.mark.unit
def test_parse_renault_dealer_missing_name_returns_none():
    assert w2.parse_renault_dealer({"birId": "123", "siteId": "001"}, "DE", "renault") is None
    assert w2.parse_renault_dealer({}, "FR", "renault") is None


@pytest.mark.unit
def test_parse_dacia_dealer_dwslink():
    """Dacia uses 'dacia' sub-key, same structure as renault."""
    d = {
        "dealerId": "27623708_001",
        "name": "RRG Dacia München Milbertshofen",
        "birId": "27623708",
        "siteId": "001",
        "locality": "München",
        "postalCode": "80807",
        "geolocalization": {"lat": 48.18, "lon": 11.56},
        "dacia": {
            "dwsLink": "https://dacia-rrg-muenchen-milbertshofen.de/",
            "withDws": True,
        },
    }
    c = w2.parse_renault_dealer(d, "DE", "dacia")
    assert c is not None
    assert c["source"] == "oem:dacia"
    assert c["domain"] == "dacia-rrg-muenchen-milbertshofen.de"
    assert c["url"] == "https://dacia-rrg-muenchen-milbertshofen.de"  # trailing slash stripped


# ── SEAT SNW XML ─────────────────────────────────────────────────────────────
def _make_seat_xml_partner(**fields: str) -> ET.Element:
    """Build a minimal <partner> element from keyword arguments."""
    p = ET.Element("partner")
    for tag, text in fields.items():
        el = ET.SubElement(p, tag)
        el.text = text
    return p


@pytest.mark.unit
def test_parse_seat_xml_dealer_with_url():
    """<url> present (bare domain) → normalized and domain extracted."""
    p = _make_seat_xml_partner(
        partner_id="ESP0042R",
        name="VALDERRIBAS MOTOR",
        street="Calle del Motor 1",
        city="Madrid",
        zip_code="28001",
        phone1="915000000",
        email="info@valderribas.seat",
        url="www.valderribasmotor.seat",
        latitude="40.42",
        longitude="-3.70",
    )
    c = w2.parse_seat_xml_dealer(p, "ES")
    assert c is not None
    assert c["source"] == "oem:seat"
    assert c["country"] == "ES"
    assert c["domain"] == "valderribasmotor.seat"
    assert c["url"] == "https://www.valderribasmotor.seat"
    assert c["registry_id"] == "ESP0042R"
    assert c["lat"] == 40.42
    assert c["lng"] == -3.70
    assert c["city"] == "Madrid"
    assert c["phone"] == "915000000"


@pytest.mark.unit
def test_parse_seat_xml_dealer_no_url():
    """<url> absent → domain=None, identity row via registry_id."""
    p = _make_seat_xml_partner(
        partner_id="DEV25CG",
        name="Auto & Service PIA GmbH",
        city="München",
        zip_code="80539",
    )
    c = w2.parse_seat_xml_dealer(p, "DE")
    assert c is not None
    assert c["domain"] is None
    assert c["url"] is None
    assert c["registry_id"] == "DEV25CG"


@pytest.mark.unit
def test_parse_seat_xml_dealer_missing_name_returns_none():
    p = ET.Element("partner")
    assert w2.parse_seat_xml_dealer(p, "DE") is None


# ── SEAT BE D'Ieteren ────────────────────────────────────────────────────────
@pytest.mark.unit
def test_parse_seat_be_dealer_with_url():
    d = {
        "WorkLocationId": "BE_SEAT_001",
        "NAME": "D'Ieteren Sport Brussels",
        "ADDRESS": "Rue du Pôle Nord 7",
        "CITY": "Bruxelles",
        "ZIP": "1000",
        "TEL": "+32 2 333 00 00",
        "MAIL": "info@dieteren.be",
        "URL": "https://www.dieterenmobilitycompany.be/fr/seat/bruxelles",
        "GPSLAT": "50.8503",
        "GPSLONG": "4.3517",
    }
    c = w2.parse_seat_be_dealer(d)
    assert c is not None
    assert c["source"] == "oem:seat"
    assert c["country"] == "BE"
    assert c["domain"] == "dieterenmobilitycompany.be"
    assert c["registry_id"] == "BE_SEAT_001"
    assert c["lat"] == 50.8503
    assert c["lng"] == 4.3517


@pytest.mark.unit
def test_parse_seat_be_dealer_no_url():
    d = {
        "WorkLocationId": "BE_SEAT_002",
        "NAME": "SEAT Dealer Antwerpen",
        "CITY": "Antwerpen",
        "ZIP": "2000",
    }
    c = w2.parse_seat_be_dealer(d)
    assert c is not None
    assert c["domain"] is None
    assert c["url"] is None
    assert c["registry_id"] == "BE_SEAT_002"


@pytest.mark.unit
def test_parse_seat_be_dealer_missing_name_returns_none():
    assert w2.parse_seat_be_dealer({}) is None
    assert w2.parse_seat_be_dealer({"WorkLocationId": "x"}) is None
