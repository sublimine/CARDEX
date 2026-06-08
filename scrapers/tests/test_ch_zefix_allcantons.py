"""CH Zefix all-cantons mirror — pure transform + dealer name filter (no network)."""
from __future__ import annotations

import pytest

from scrapers.discovery.sources.ch_zefix_allcantons import to_candidate
from scrapers.discovery.dealer_terms import name_matches


@pytest.mark.unit
def test_ch_allcantons_to_candidate_maps_mirror_columns():
    row = {
        "company_legal_name": "Garage Müller AG",
        "company_uid": "CHE-123.456.789",
        "street": "Hauptstrasse 1", "plz": "8001", "locality": "Zürich",
        "municipality": "Zürich", "short_name_canton": "ZH",
        "company_type_de": "Aktiengesellschaft",
        "url_cantonal_register": "https://register.example/zh/1",
    }
    c = to_candidate(row)
    assert c["country"] == "CH" and c["source"] == "zefix" and c["domain"] is None
    assert c["registry_id"] == "CHE-123.456.789" and c["name"] == "Garage Müller AG"
    assert c["postcode"] == "8001" and c["city"] == "Zürich" and c["address"] == "Hauptstrasse 1"
    assert c["external_refs"]["canton"] == "ZH"
    assert c["external_refs"]["legal_form"] == "Aktiengesellschaft"


@pytest.mark.unit
def test_ch_allcantons_city_falls_back_to_municipality():
    row = {"company_legal_name": "Carrozzeria Rossi Sagl", "company_uid": "CHE-9",
           "municipality": "Lugano", "plz": "6900"}
    c = to_candidate(row)
    assert c["city"] == "Lugano"  # locality absent → municipality


@pytest.mark.unit
def test_ch_allcantons_trilingual_dealer_filter():
    # The run loop keeps a row only when its legal name matches the CH (de/fr/it) lexicon.
    assert name_matches("Garage Müller AG", "CH")            # fr/de
    assert name_matches("Autohaus Zürich GmbH", "CH")        # de
    assert name_matches("Carrozzeria Rossi Sagl", "CH")      # it (Ticino)
    assert name_matches("Concessionaria Ticinese SA", "CH")  # it
    assert not name_matches("Bäckerei Keller AG", "CH")      # non-motor → dropped
