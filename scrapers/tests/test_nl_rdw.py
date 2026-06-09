"""nl_rdw discovery source — pure transform tests (no network)."""
from __future__ import annotations

import asyncio

import pytest

from scrapers.discovery.sources.nl_rdw import NLRDWSource, _DEALER_ERKENNINGEN, to_candidate


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


# ── NLRDWSource (orchestrator adapter): yields candidates for NL, skips others ──
class _FakeResp:
    def __init__(self, data):
        self._data = data

    def raise_for_status(self):
        pass

    def json(self):
        return self._data


class _FakeClient:
    """httpx-shaped double: routes by RDW dataset id; paginates erkenningen once."""

    def __init__(self, erkenningen, companies):
        self._erk, self._comp = erkenningen, companies

    async def get(self, url, params=None, headers=None):
        if "nmwb-dqkz" in url:                        # erkenningen (paginated)
            return _FakeResp(self._erk if (params or {}).get("$offset", 0) == 0 else [])
        if "5k74-3jha" in url:                        # companies
            return _FakeResp(self._comp)
        return _FakeResp([])


async def _collect(agen):
    return [x async for x in agen]


@pytest.mark.unit
def test_nlrdw_source_yields_nl_candidates():
    erk = [{"volgnummer": "1", "erkenning": "Bedrijfsvoorraad"},
           {"volgnummer": "2", "erkenning": "Handelaarskenteken"}]
    comp = [{"volgnummer": "1", "naam_bedrijf": "Auto Uno B.V.", "plaats": "AMSTERDAM"},
            {"volgnummer": "2", "naam_bedrijf": "Garage Dos", "plaats": "ROTTERDAM"}]
    cands = asyncio.run(_collect(NLRDWSource(_FakeClient(erk, comp)).discover("NL")))
    assert len(cands) == 2
    assert {c["registry_id"] for c in cands} == {"1", "2"}
    assert all(c["country"] == "NL" and c["source"] == "rdw_erkende_bedrijven" for c in cands)
    assert all(c["domain"] is None for c in cands)     # identity rows (domain resolved later)


@pytest.mark.unit
def test_nlrdw_source_skips_non_nl():
    assert asyncio.run(_collect(NLRDWSource(_FakeClient([], [])).discover("DE"))) == []
