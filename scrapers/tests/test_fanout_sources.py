"""Fan-out discovery sources — pure transforms + dialect dictionary (no network)."""
from __future__ import annotations

import pytest

from scrapers.discovery import dealer_terms
from scrapers.discovery.sources.ch_zefix_bs import to_candidate as ch_cand
from scrapers.discovery.sources.es_openmercantil import to_candidate as es_cand
from scrapers.discovery.sources.fr_recherche_entreprises import _coords, to_candidate as fr_cand


# ── dealer_terms (dialects) ─────────────────────────────────────────────────────
@pytest.mark.unit
def test_dealer_terms_correct_dialect_per_country():
    assert "autohaus" in dealer_terms.terms_for("DE")
    assert "concessionnaire" in dealer_terms.terms_for("FR")
    assert "concesionario" in dealer_terms.terms_for("ES")
    assert "autobedrijf" in dealer_terms.terms_for("NL")
    # BE is bilingual (nl + fr); CH is trilingual (de + fr + it)
    be = dealer_terms.terms_for("BE")
    assert "autobedrijf" in be and "concessionnaire" in be
    ch = dealer_terms.terms_for("CH")
    assert "autohaus" in ch and "carrosserie" in ch and "autofficina" in ch  # de+fr+it


@pytest.mark.unit
def test_name_matches_accent_and_case_insensitive():
    assert dealer_terms.name_matches("Garage Müller AG", "CH")
    assert dealer_terms.name_matches("AUTOHAUS Schmidt GmbH", "DE")
    assert dealer_terms.name_matches("Concesionario Automóviles SL", "ES")
    assert dealer_terms.name_matches("Carrozzeria Rossi Sagl", "CH")  # Italian (Ticino)
    assert not dealer_terms.name_matches("Boulangerie Dupont", "FR")
    assert not dealer_terms.name_matches("", "DE")


# ── FR ──────────────────────────────────────────────────────────────────────────
@pytest.mark.unit
def test_fr_to_candidate():
    result = {
        "siren": "552032534", "nom_complet": "GARAGE DUPONT AUTOMOBILES",
        "etat_administratif": "A", "activite_principale": "45.11Z",
        "siege": {"adresse": "12 RUE DE PARIS 75011 PARIS", "commune": "PARIS",
                  "code_postal": "75011", "departement": "75", "coordonnees": "48.85,2.35"},
    }
    c = fr_cand(result)
    assert c["country"] == "FR" and c["source"] == "recherche_entreprises"
    assert c["registry_id"] == "552032534" and c["domain"] is None
    assert c["name"] == "GARAGE DUPONT AUTOMOBILES"
    assert c["postcode"] == "75011" and c["city"] == "PARIS"
    assert c["lat"] == 48.85 and c["lng"] == 2.35
    assert c["external_refs"]["naf"] == "45.11Z"


@pytest.mark.unit
def test_fr_coords_parsing_robust():
    assert _coords({"coordonnees": "48.85,2.35"}) == (48.85, 2.35)
    assert _coords({"coordonnees": None}) == (None, None)
    assert _coords({}) == (None, None)
    assert _coords({"coordonnees": "garbage"}) == (None, None)


# ── ES ──────────────────────────────────────────────────────────────────────────
@pytest.mark.unit
def test_es_to_candidate():
    item = {"slug": "garaje-x-mad", "name": "GARAJE X SL", "cif": "B12345678",
            "province": "Madrid", "cnae_code": "4511"}
    c = es_cand(item, "4511")
    assert c["country"] == "ES" and c["source"] == "openmercantil"
    assert c["registry_id"] == "B12345678" and c["city"] == "Madrid"
    assert c["external_refs"]["cnae"] == "4511"


# ── CH ──────────────────────────────────────────────────────────────────────────
@pytest.mark.unit
def test_ch_to_candidate_and_coords():
    rec = {"company_legal_name": "Garage Müller AG", "company_uid": "CHE-123.456.789",
           "municipality": "Basel", "street": "Hauptstrasse 1", "plz": "4051",
           "locality": "Basel", "coordinates": {"lat": 47.55, "lon": 7.58}}
    c = ch_cand(rec)
    assert c["country"] == "CH" and c["source"] == "zefix_bs"
    assert c["registry_id"] == "CHE-123.456.789"
    assert c["postcode"] == "4051" and c["city"] == "Basel"
    assert c["lat"] == 47.55 and c["lng"] == 7.58
    assert c["external_refs"]["canton"] == "BS"


@pytest.mark.unit
def test_ch_coords_geojson_list_order():
    from scrapers.discovery.sources.ch_zefix_bs import _coords as ch_coords
    # geojson [lon, lat] → (lat, lng)
    assert ch_coords({"coordinates": [7.58, 47.55]}) == (47.55, 7.58)
    assert ch_coords({"coordinates": None}) == (None, None)


# ── DE (OffeneRegister) — transform + blocked-load ─────────────────────────────
@pytest.mark.unit
def test_de_to_candidate():
    from scrapers.discovery.sources.de_offeneregister import to_candidate as de_cand
    row = {"company_number": "HRB12345", "name": "Autohaus Schmidt GmbH",
           "registered_office": "München"}
    c = de_cand(row)
    assert c["country"] == "DE" and c["source"] == "offeneregister"
    assert c["registry_id"] == "HRB12345" and c["name"] == "Autohaus Schmidt GmbH"
    assert c["city"] == "München"


@pytest.mark.unit
def test_de_run_blocked_returns_zero_no_invented_data(monkeypatch):
    # SQL API is 502 → run() must return 0 (blocked), never fabricate rows.
    import asyncio
    from scrapers.discovery.sources import de_offeneregister as de

    class _Boom:
        async def __aenter__(self_):
            class _C:
                async def get(self__, *a, **k):
                    raise __import__("httpx").ConnectError("down")
            return _C()
        async def __aexit__(self_, *a):
            return False

    async def _fake_pool(*a, **k):
        class _P:
            async def execute(self_, *a, **k):
                raise AssertionError("must not insert when blocked")
            async def close(self_):
                pass
        return _P()

    monkeypatch.setattr(de.asyncpg, "create_pool", _fake_pool)
    monkeypatch.setattr(de.httpx, "AsyncClient", lambda *a, **k: _Boom())
    assert asyncio.run(de.run(per_term=5)) == 0


# ── BE (KBO) — NACE filter + transform + blocked-load ──────────────────────────
@pytest.mark.unit
def test_be_nace_filter_and_candidate():
    from scrapers.discovery.sources.be_kbo import is_auto_nace, to_candidate as be_cand
    assert is_auto_nace("45110") and is_auto_nace("45.20.1") and is_auto_nace("45191")
    assert not is_auto_nace("47.11") and not is_auto_nace("")
    c = be_cand({"EnterpriseNumber": "0123.456.789", "Denomination": "Garage Vroom BVBA",
                 "Zipcode": "1000", "MunicipalityNL": "Brussel", "StreetNL": "Wetstraat",
                 "HouseNumber": "16", "NaceCode": "45110"})
    assert c["country"] == "BE" and c["registry_id"] == "0123.456.789"
    assert c["address"] == "Wetstraat 16" and c["postcode"] == "1000"


@pytest.mark.unit
def test_be_run_blocked_without_data_dir(monkeypatch):
    import asyncio
    from scrapers.discovery.sources import be_kbo
    monkeypatch.delenv("KBO_DATA_DIR", raising=False)
    assert asyncio.run(be_kbo.run(data_dir=None)) == 0  # blocked, no invented data
