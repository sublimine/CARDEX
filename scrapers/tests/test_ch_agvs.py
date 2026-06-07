"""CH AGVS/UPSA member directory — pure parser (no network)."""
from __future__ import annotations

import html

import pytest

from scrapers.discovery.sources import ch_agvs


@pytest.mark.unit
def test_agvs_to_candidate_with_web():
    obj = {"surname": "Automobile Weiss AG", "street": "Hauptstrasse 63", "zip": "5085",
           "city": "Sulz AG", "phone": "+41 62 875 16 65", "email": "info@automobileweiss.ch",
           "url": "www.automobileweiss.ch", "latitude": 47.539, "longitude": 8.099}
    c = ch_agvs.to_candidate(obj)
    assert c["country"] == "CH" and c["source"] == "agvs" and c["source_layer"] == 2
    assert c["domain"] == "automobileweiss.ch"           # protocol-less url normalised
    assert c["url"] == "https://www.automobileweiss.ch"
    assert c["name"] == "Automobile Weiss AG" and c["postcode"] == "5085" and c["city"] == "Sulz AG"
    assert c["lat"] == 47.539 and c["lng"] == 8.099
    assert c["registry_id"] and c["registry_id"].startswith("agvs-")


@pytest.mark.unit
def test_agvs_to_candidate_without_web_still_has_identity():
    obj = {"surname": "Garage Sans Web", "zip": "1000", "city": "Lausanne"}
    c = ch_agvs.to_candidate(obj)
    assert c["domain"] is None and c["url"] is None
    assert c["registry_id"] and c["registry_id"].startswith("agvs-")  # synthesised → still dedupable


@pytest.mark.unit
def test_agvs_synth_id_deterministic_and_distinct():
    a = ch_agvs._synth_id("Garage X", "1000", "Lausanne")
    b = ch_agvs._synth_id("Garage X", "1000", "Lausanne")
    d = ch_agvs._synth_id("Garage Y", "1000", "Lausanne")
    assert a == b and a != d and ch_agvs._synth_id(None, None, None) is None


@pytest.mark.unit
def test_agvs_parse_members_from_html_encoded_block():
    raw = ('noise '
           + html.escape('{"surname":"Carrosserie Test Sàrl","street":"Rue 1","zip":"1200",'
                         '"city":"Genève","phone":"+41","email":"a@b.ch","url":"www.test.ch",'
                         '"latitude":46.2,"longitude":6.1}')
           + ' more')
    cands = ch_agvs.parse_members(raw)
    assert len(cands) == 1
    assert cands[0]["name"] == "Carrosserie Test Sàrl" and cands[0]["domain"] == "test.ch"
