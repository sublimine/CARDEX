"""
Pure-transform tests for DE/NL/ES/BE registry connectors.
No network, no DB — pure input/output verification.
"""
import pytest

# ---------------------------------------------------------------------------
# de_offeneregister
# ---------------------------------------------------------------------------
from scrapers.discovery.sources.de_offeneregister import to_candidate as or_candidate


def test_or_candidate_full():
    row = {"company_number": "HRB12345", "name": "Autohaus München GmbH", "registered_office": "München"}
    c = or_candidate(row)
    assert c["registry_id"] == "HRB12345"
    assert c["name"] == "Autohaus München GmbH"
    assert c["country"] == "DE"
    assert c["domain"] is None
    assert c["source"] == "offeneregister"


def test_or_candidate_missing_fields():
    c = or_candidate({})
    assert c["registry_id"] is None
    assert c["name"] is None
    assert c["country"] == "DE"


def test_or_candidate_strips_whitespace():
    row = {"company_number": " HRB999 ", "name": "  KFZ Handel AG  ", "registered_office": "Berlin"}
    c = or_candidate(row)
    assert c["registry_id"] == "HRB999"
    assert c["name"] == "KFZ Handel AG"


# ---------------------------------------------------------------------------
# nl_rdw
# ---------------------------------------------------------------------------
from scrapers.discovery.sources.nl_rdw import to_candidate as rdw_candidate


def test_rdw_candidate_full():
    company = {
        "volgnummer": "12345",
        "naam_bedrijf": "Auto Centrum BV",
        "gevelnaam": "AutoCentrum",
        "straat": "Hoofdstraat",
        "huisnummer": "10",
        "postcode_numeriek": "1234",
        "postcode_alfanumeriek": "AB",
        "plaats": "Amsterdam",
    }
    c = rdw_candidate(company, ["Bedrijfsvoorraad"])
    assert c["registry_id"] == "12345"
    assert c["name"] == "Auto Centrum BV"
    assert c["address"] == "Hoofdstraat 10"
    assert c["postcode"] == "1234AB"
    assert c["city"] == "Amsterdam"
    assert c["country"] == "NL"
    assert c["domain"] is None
    assert "Bedrijfsvoorraad" in c["external_refs"]["erkenningen"]


def test_rdw_candidate_missing_naam_falls_back_to_gevelnaam():
    company = {
        "volgnummer": "99",
        "naam_bedrijf": "",
        "gevelnaam": "CarShop",
        "straat": "Dorpstraat",
        "huisnummer": "1",
        "postcode_numeriek": "5000",
        "postcode_alfanumeriek": "XZ",
        "plaats": "Rotterdam",
    }
    c = rdw_candidate(company, [])
    assert c["name"] == "CarShop"


def test_rdw_candidate_empty_volgnummer():
    company = {"volgnummer": "", "naam_bedrijf": "Test"}
    c = rdw_candidate(company, [])
    assert c["registry_id"] is None


# ---------------------------------------------------------------------------
# es_openmercantil
# ---------------------------------------------------------------------------
from scrapers.discovery.sources.es_openmercantil import to_candidate as es_candidate


def test_es_candidate_full():
    item = {
        "slug": "autoabc",
        "name": "AUTO ABC, S.L.",
        "cif": "B12345678",
        "province": "Madrid",
        "cnae_code": "4511",
    }
    c = es_candidate(item, "4511")
    assert c["registry_id"] == "B12345678"
    assert c["name"] == "AUTO ABC, S.L."
    assert c["city"] == "Madrid"
    assert c["country"] == "ES"
    assert c["domain"] is None
    assert c["external_refs"]["cnae"] == "4511"


def test_es_candidate_missing_cif():
    c = es_candidate({"name": "Taller Pérez"}, "4520")
    assert c["registry_id"] is None


# ---------------------------------------------------------------------------
# be_kbo
# ---------------------------------------------------------------------------
from scrapers.discovery.sources.be_kbo import to_candidate as kbo_candidate, is_auto_nace


def test_kbo_is_auto_nace():
    assert is_auto_nace("4511") is True
    assert is_auto_nace("4519") is True
    assert is_auto_nace("4520") is True
    # _NACE_PREFIXES are exact 4-digit prefixes: 4521 does NOT start with any
    assert is_auto_nace("4521") is False
    assert is_auto_nace("45.11") is True  # with dot (stripped by impl)
    assert is_auto_nace("6201") is False
    assert is_auto_nace("") is False


def test_kbo_candidate_full():
    joined = {
        "EnterpriseNumber": "0123.456.789",
        "Denomination": "Garage Dupont SPRL",
        "StreetNL": "Kerkstraat",
        "HouseNumber": "5",
        "Zipcode": "1000",
        "MunicipalityNL": "Brussel",
        "NaceCode": "4511",
    }
    c = kbo_candidate(joined)
    assert c["registry_id"] == "0123.456.789"
    assert c["name"] == "Garage Dupont SPRL"
    assert c["address"] == "Kerkstraat 5"
    assert c["postcode"] == "1000"
    assert c["city"] == "Brussel"
    assert c["country"] == "BE"
    assert c["domain"] is None


def test_kbo_candidate_fr_fallback():
    joined = {
        "EnterpriseNumber": "0987.654.321",
        "Denomination": "Garage Martin SA",
        "StreetNL": "",
        "StreetFR": "Rue de la Paix",
        "HouseNumber": "12",
        "Zipcode": "4000",
        "MunicipalityNL": "",
        "MunicipalityFR": "Liège",
        "NaceCode": "4519",
    }
    c = kbo_candidate(joined)
    assert c["address"] == "Rue de la Paix 12"
    assert c["city"] == "Liège"


def test_kbo_candidate_empty_enterprise_number():
    c = kbo_candidate({"EnterpriseNumber": "  ", "Denomination": "X"})
    assert c["registry_id"] is None


# ---------------------------------------------------------------------------
# dealer_terms
# ---------------------------------------------------------------------------
from scrapers.discovery.dealer_terms import name_matches, terms_for


def test_terms_for_de():
    terms = terms_for("DE")
    assert "autohaus" in terms
    assert "kfz" in terms


def test_name_matches_de():
    assert name_matches("Autohaus München GmbH", "DE") is True
    assert name_matches("KFZ Meier AG", "DE") is True
    assert name_matches("Bäckerei Schmidt", "DE") is False


def test_name_matches_nl():
    assert name_matches("Autobedrijf Jansen BV", "NL") is True
    assert name_matches("Bloemist Pietersen", "NL") is False


def test_name_matches_accent_insensitive():
    # "automobil" should match even with umlauts in the term list
    assert name_matches("Automobile GmbH", "DE") is True
