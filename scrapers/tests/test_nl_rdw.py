"""nl_rdw discovery source — pure transform tests (no network)."""
from __future__ import annotations

import pytest

from scrapers.discovery.sources.nl_rdw import _DEALER_ERKENNINGEN, to_candidate


@pytest.mark.unit
def test_to_candidate_maps_rdw_row():
    company = {
        "volgnummer": "12345", "naam_bedrijf": "Autobedrijf De Jong B.V.",
        "gevelnaam": "De Jong Auto's", "straat": "DORPSSTRAAT", "huisnummer": "12",
        "postcode_numeriek": "1234", "postcode_alfanumeriek": "AB", "plaats": "UTRECHT",
    }
    c = to_candidate(company, ["Bedrijfsvoorraad"])
    assert c["domain"] is None                       # identity row (resolved later)
    assert c["country"] == "NL" and c["source"] == "rdw_erkende_bedrijven"
    assert c["source_layer"] == 3
    assert c["registry_id"] == "12345"               # dedup key
    assert c["name"] == "Autobedrijf De Jong B.V."
    assert c["address"] == "DORPSSTRAAT 12"
    assert c["postcode"] == "1234AB"
    assert c["city"] == "UTRECHT"
    assert c["external_refs"]["erkenningen"] == ["Bedrijfsvoorraad"]
    assert c["external_refs"]["gevelnaam"] == "De Jong Auto's"


@pytest.mark.unit
def test_to_candidate_falls_back_to_gevelnaam_for_name():
    c = to_candidate({"volgnummer": "9", "gevelnaam": "Garage X"}, [])
    assert c["name"] == "Garage X"
    assert c["registry_id"] == "9"


@pytest.mark.unit
def test_dealer_filter_is_stock_and_plate():
    # The filter must target vehicle-stock / dealer-plate holders, not all RDW companies.
    assert "Bedrijfsvoorraad" in _DEALER_ERKENNINGEN
    assert "Handelaarskenteken" in _DEALER_ERKENNINGEN
    assert "Fotograaf Bemand" not in _DEALER_ERKENNINGEN
