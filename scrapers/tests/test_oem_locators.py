"""OEM locator parsers — pure transforms over real verified sample shapes (no network)."""
from __future__ import annotations

import pytest

from scrapers.discovery.sources import oem_locators as oem


# ── VW / Audi (shared SDS shape) ────────────────────────────────────────────────
@pytest.mark.unit
def test_parse_vw_dealer_geojson_coords_and_domain():
    d = {
        "id": "DE000XXXX", "name": "Autohaus Beispiel GmbH",
        "address": {"city": "Berlin", "postalCode": "10115", "street": "Musterstraße 1"},
        "geoPosition": {"type": "Point", "coordinates": [13.405, 52.52]},  # [lng, lat]
        "contact": {"website": "https://www.autohaus-beispiel.de", "phoneNumber": "+49 30 123456"},
        "partner": {"partnerId": "DE000XXXX"},
    }
    c = oem.parse_vw_dealer(d, "DE", "oem:vw")
    assert c["source"] == "oem:vw" and c["country"] == "DE" and c["source_layer"] == 1
    assert c["domain"] == "autohaus-beispiel.de" and c["url"] == "https://www.autohaus-beispiel.de"
    assert c["lat"] == 52.52 and c["lng"] == 13.405  # coordinates[1]=lat, [0]=lng
    assert c["postcode"] == "10115" and c["city"] == "Berlin" and c["registry_id"] == "DE000XXXX"
    assert c["external_refs"]["sds_partner_id"] == "DE000XXXX"


@pytest.mark.unit
def test_parse_vw_dealer_missing_name_dropped_and_no_website():
    assert oem.parse_vw_dealer({"id": "x"}, "FR", "oem:audi") is None
    c = oem.parse_vw_dealer({"id": "x", "name": "Audi Zentrum", "address": {}, "geoPosition": {}}, "FR", "oem:audi")
    assert c["domain"] is None and c["url"] is None and c["lat"] is None and c["source"] == "oem:audi"


# ── Škoda ────────────────────────────────────────────────────────────────────────
@pytest.mark.unit
def test_parse_skoda_item():
    it = {"MarkerId": "107-55", "GlobalId": "G55", "Name": "Volkswagen Automobile Berlin GmbH",
          "Address": {"Street": "Franklinstr 26", "City": "Berlin", "ZIP": "10587",
                      "Latitude": 52.52, "Longitude": 13.32}}
    c = oem.parse_skoda_item(it, "DE")
    assert c["source"] == "oem:skoda" and c["registry_id"] == "107-55"
    assert c["lat"] == 52.52 and c["lng"] == 13.32 and c["postcode"] == "10587"
    assert c["domain"] is None  # identity row


# ── Toyota (string format, name may contain '=') ─────────────────────────────────
@pytest.mark.unit
def test_parse_toyota_line_basic():
    c = oem.parse_toyota_line("00CD4-0F643=ADG Assen B.V.=ASSEN=9403 AB", "NL")
    assert c["source"] == "oem:toyota" and c["name"] == "ADG Assen B.V."
    assert c["city"] == "ASSEN" and c["postcode"] == "9403 AB"
    assert c["registry_id"] == "00CD4-0F643" and c["external_refs"]["toyota_uuid"] == "00CD4-0F643"


@pytest.mark.unit
def test_parse_toyota_line_name_with_equals_and_malformed():
    # name itself contains '=' → must rejoin middle, keep uuid/city/postcode anchored at ends
    c = oem.parse_toyota_line("UUID1=A=B Motors=Lyon=69000", "FR")
    assert c["name"] == "A=B Motors" and c["city"] == "Lyon" and c["postcode"] == "69000"
    assert oem.parse_toyota_line("too=few", "FR") is None
    assert oem.parse_toyota_line("", "FR") is None


# ── Hyundai (SSR + Uberall) ──────────────────────────────────────────────────────
@pytest.mark.unit
def test_parse_hyundai_ssr_website_and_phone():
    d = {"id": "C07AB02378", "fullDealerName": "A. Lemke Autohaus GmbH",
         "webSite": "https://www.autohaus-lemke.de", "addressLine1": "An der Stollenmühle 39",
         "postalCode": "06526", "city": "Sangerhausen", "phone": "3464/516181",
         "phoneCountryCode": "49", "lat": "51.46709", "lng": "11.27953"}
    c = oem.parse_hyundai_dealer(d, "DE")
    assert c["domain"] == "autohaus-lemke.de" and c["registry_id"] == "C07AB02378"
    assert c["phone"] == "+49 3464/516181" and c["lat"] == 51.46709 and c["lng"] == 11.27953


@pytest.mark.unit
def test_parse_hyundai_ssr_website_list_variant():
    d = {"id": "C19AB300578", "fullDealerName": "Alcardis Automobile AG",
         "website": [{"title": "x", "url": "https://alcardis.hyundai.ch"}],
         "addressLine1": "Worblaufenstrasse", "postalCode": "3048", "city": "Worblaufen"}
    c = oem.parse_hyundai_dealer(d, "CH")
    assert c["domain"] == "alcardis.hyundai.ch" and c["url"] == "https://alcardis.hyundai.ch"


@pytest.mark.unit
def test_parse_hyundai_uberall():
    loc = {"id": 2499352, "identifier": "C06AB00420", "name": "Hyundai Aix en Provence",
           "streetAndNumber": "130 Rue Bastide", "zip": "13290", "city": "Aix-en-Provence",
           "phone": "+33 4 42 38 13 13", "lat": 43.50867, "lng": 5.40300}
    c = oem.parse_hyundai_uberall(loc, "FR")
    assert c["source"] == "oem:hyundai" and c["registry_id"] == "C06AB00420"
    assert c["domain"] is None and c["lat"] == 43.50867 and c["external_refs"]["uberall_id"] == 2499352


# ── Kia (AEM + slapwl CH) ────────────────────────────────────────────────────────
@pytest.mark.unit
def test_parse_kia_aem():
    d = {"dealerExternalid": "D00204", "dealerName": "Autohaus am Volkspark",
         "dealerAddress": "Hasenheide 70", "dealerPostcode": "10967", "dealerResidence": "Berlin",
         "dealerPhone1": "+49 30 6953730", "dealerEmail": "info@x.de", "lat": 52.487, "lng": 13.411}
    c = oem.parse_kia_aem(d, "DE")
    assert c["source"] == "oem:kia" and c["registry_id"] == "D00204" and c["city"] == "Berlin"
    assert c["lat"] == 52.487 and c["email"] == "info@x.de" and c["domain"] is None


@pytest.mark.unit
def test_parse_kia_ch_brand_filter():
    selling = {"id": "10119", "name": "Garage Gerber AG", "street": "Wengelacher 3", "zip": "3800",
               "city": "Matten", "latitude": 46.671, "longitude": 7.856, "slug": "gerber",
               "brands": [{"name": "Kia", "sell": True, "service": True}]}
    c = oem.parse_kia_ch(selling)
    assert c["country"] == "CH" and c["registry_id"] == "10119" and c["external_refs"]["kia_slug"] == "gerber"
    # a dealer that does not sell Kia is filtered out
    not_kia = {"id": "9", "name": "Foo", "brands": [{"name": "VW", "sell": True}]}
    assert oem.parse_kia_ch(not_kia) is None


# ── value helpers ────────────────────────────────────────────────────────────────
@pytest.mark.unit
def test_domain_and_float_helpers():
    assert oem._domain("https://www.foo.de/x") == "foo.de"
    assert oem._domain(None) is None
    assert oem._f("12.5") == 12.5 and oem._f("") is None and oem._f(None) is None and oem._f("x") is None
    assert oem._normalize_url("foo.de") == "https://foo.de"


@pytest.mark.unit
def test_brands_registry_shape():
    assert set(oem.BRANDS) == {"vw", "audi", "skoda", "toyota", "hyundai", "kia"}
    # VW excludes BE (SDS 204); Audi includes it
    assert "BE" not in oem.BRANDS["vw"][1] and "BE" in oem.BRANDS["audi"][1]
