"""
Tests for the local-LLM fuzzy decision layer (scrapers/llm).

Unit tests use a FakeClient (records calls, returns canned JSON) to prove the
routing contract deterministically: the heuristic decides the clear cases with
ZERO LLM calls, the LLM is consulted ONLY in the ambiguous band, and every LLM
path is fail-open (LLM down / garbled ⇒ heuristic verdict stands).

One integration test exercises a live Ollama if one is reachable, else skips.
"""
from __future__ import annotations

import os
import urllib.error

import pytest

from scrapers.llm import decisions as d
from scrapers.llm.ollama_client import OllamaClient


class FakeClient:
    """Duck-typed OllamaClient double: records calls, returns a canned object."""

    def __init__(self, *, available: bool = True, result: dict | None = None):
        self._available = available
        self._result = result
        self.calls: list[dict] = []

    def available(self) -> bool:
        return self._available

    def generate_json(self, prompt, *, system=None, schema=None, max_tokens=256):
        self.calls.append({"prompt": prompt, "system": system, "schema": schema})
        return self._result


def _page(title: str, body: str) -> str:
    # >=200 chars so confirms_dealer doesn't short-circuit on "empty_page".
    return f"<html><head><title>{title}</title></head><body>{'x' * 250} {body}</body></html>"


# ── classify_is_car_dealer routing ────────────────────────────────────────────────
@pytest.mark.unit
def test_clear_dealer_strong_signal_no_llm():
    """Strong auto word + name on page → heuristic accepts, LLM never called."""
    fake = FakeClient(result={"is_car_dealer": False, "kind": "x", "confidence": 1})
    html = _page("Garage Koch", "Garage Koch Gebrauchtwagen Neuwagen Probefahrt")
    v = d.classify_is_car_dealer(html, "Garage Koch", "Eiken", client=fake)
    assert v.is_dealer is True and v.source == "heuristic" and not v.consulted_llm
    assert fake.calls == []


@pytest.mark.unit
def test_hard_reject_non_dealer_title_no_llm():
    """A declared non-dealer (driving school) is rejected by heuristic, no LLM."""
    fake = FakeClient(result={"is_car_dealer": True, "kind": "x", "confidence": 1})
    html = _page("Fahrschule Marty", "auto fahrzeug showroom cars")
    v = d.classify_is_car_dealer(html, "Fahrschule Marty", "Zurich", client=fake)
    assert v.is_dealer is False and v.source == "heuristic" and v.reason == "non_dealer_category"
    assert fake.calls == []


@pytest.mark.unit
def test_ambiguous_body_shop_consults_llm_and_downgrades():
    """Only-strong-word 'carrosserie' passes heuristic but LLM downgrades the FP."""
    fake = FakeClient(result={"is_car_dealer": False, "kind": "body_paint", "confidence": 0.95})
    html = _page("Carrosserie Muller", "Carrosserie Muller Karosserie Lackiererei Unfallreparatur")
    v = d.classify_is_car_dealer(html, "Carrosserie Muller", "Bern", client=fake)
    assert len(fake.calls) == 1                      # LLM consulted (ambiguous band)
    assert v.is_dealer is False and v.source == "llm" and v.kind == "body_paint"
    assert v.confidence == pytest.approx(0.95)


@pytest.mark.unit
def test_ambiguous_rescue_real_dealer_name_mismatch():
    """Heuristic FALSE on name_not_on_page + automotive page → LLM can rescue."""
    fake = FakeClient(result={"is_car_dealer": True, "kind": "dealer", "confidence": 0.9})
    # Strong auto signal, but the distinctive name token is absent from the text.
    html = _page("Welcome", "Gebrauchtwagen Neuwagen Autohaus Probefahrt im Angebot")
    v = d.classify_is_car_dealer(html, "Zxqvy Motors", "Köln", client=fake)
    assert len(fake.calls) == 1 and v.source == "llm" and v.is_dealer is True


@pytest.mark.unit
def test_llm_unavailable_falls_back_to_heuristic():
    """Ollama down → ambiguous case keeps the heuristic verdict, flagged."""
    fake = FakeClient(available=False)
    html = _page("Carrosserie Muller", "Carrosserie Muller Karosserie Lackiererei")
    v = d.classify_is_car_dealer(html, "Carrosserie Muller", "Bern", client=fake)
    assert fake.calls == [] and v.source == "heuristic" and v.reason.endswith("llm_unavailable")


@pytest.mark.unit
def test_llm_garbled_falls_back_to_heuristic():
    """Ollama returns no usable JSON → heuristic verdict stands."""
    fake = FakeClient(result=None)
    html = _page("Carrosserie Muller", "Carrosserie Muller Karosserie Lackiererei")
    v = d.classify_is_car_dealer(html, "Carrosserie Muller", "Bern", client=fake)
    assert len(fake.calls) == 1 and v.source == "heuristic" and v.reason.endswith("llm_nores")


@pytest.mark.unit
def test_consistency_guard_rejects_contradictory_downgrade():
    """LLM says is_car_dealer=False but kind='car dealership' → contradiction ignored."""
    fake = FakeClient(result={"is_car_dealer": False, "kind": "car dealership", "confidence": 0.95})
    html = _page("Generic Motors", "auto cars showroom dealership vehicles")  # weak-only → ambiguous
    v = d.classify_is_car_dealer(html, "Generic Motors", "Town", client=fake, require_name=False)
    assert fake.calls and v.source == "heuristic" and v.reason.endswith("llm_inconsistent")
    assert v.is_dealer is True   # well-founded heuristic positive preserved


@pytest.mark.unit
def test_precision_mode_verifies_strong_positive():
    """In precision mode even a strong-word heuristic-positive consults the LLM."""
    fake = FakeClient(result={"is_car_dealer": False, "kind": "software_vendor", "confidence": 0.9})
    html = _page("AP Soft", "gebrauchtwagen neuwagen autohaus software portal for dealers")
    v = d.classify_is_car_dealer(html, "AP Soft", "Berlin", client=fake, require_name=False, mode="precision")
    assert len(fake.calls) == 1 and v.is_dealer is False and v.kind == "software_vendor"


@pytest.mark.unit
def test_off_mode_never_calls_llm():
    fake = FakeClient(result={"is_car_dealer": False, "kind": "x", "confidence": 1})
    html = _page("Carrosserie Muller", "Carrosserie Muller Karosserie Lackiererei")
    v = d.classify_is_car_dealer(html, "Carrosserie Muller", "Bern", client=fake, mode="off")
    assert fake.calls == [] and v.source == "heuristic"


@pytest.mark.unit
def test_confidence_0_100_is_normalised():
    """Models that answer confidence 0-100 are normalised to 0-1."""
    fake = FakeClient(result={"is_car_dealer": True, "kind": "dealer", "confidence": 95})
    html = _page("x", "auto cars showroom dealership vehicles")  # weak-only → ambiguous
    v = d.classify_is_car_dealer(html, "Generic", "Town", client=fake, require_name=False)
    assert v.consulted_llm and v.confidence == pytest.approx(0.95)


# ── extract_vehicle_fields ────────────────────────────────────────────────────────
@pytest.mark.unit
def test_extract_fields_complete_no_llm():
    fake = FakeClient(result={"make": "X", "model": "Y", "year": 1, "price": 1})
    partial = {"make": "BMW", "model": "X3", "year": 2020, "price": 30000}
    out = d.extract_vehicle_fields("irrelevant", partial, client=fake)
    assert out == partial and fake.calls == []


@pytest.mark.unit
def test_extract_fields_fills_missing_only():
    fake = FakeClient(result={"make": "BMW", "model": "X3", "year": 2020, "price": 30000})
    partial = {"make": "BMW", "model": "X3"}            # price/year missing
    out = d.extract_vehicle_fields("messy text", partial, client=fake)
    assert len(fake.calls) == 1
    assert out["year"] == 2020 and out["price"] == 30000
    assert out["make"] == "BMW" and set(out["_llm_filled"]) == {"year", "price"}


@pytest.mark.unit
def test_extract_fields_failopen_when_unavailable():
    fake = FakeClient(available=False)
    partial = {"make": "BMW"}
    assert d.extract_vehicle_fields("t", partial, client=fake) == partial and fake.calls == []


# ── disambiguate_domain ───────────────────────────────────────────────────────────
@pytest.mark.unit
def test_disambiguate_clear_winner_no_llm():
    fake = FakeClient(result={"domain": "wrong.com"})
    got = d.disambiguate_domain("Garage X", "Bern", [("right.ch", 0.9), ("other.ch", 0.5)], client=fake)
    assert got == "right.ch" and fake.calls == []


@pytest.mark.unit
def test_disambiguate_tie_consults_llm():
    fake = FakeClient(result={"domain": "b.ch", "confidence": 0.8})
    got = d.disambiguate_domain("Garage X", "Bern", [("a.ch", 0.81), ("b.ch", 0.80)], client=fake)
    assert len(fake.calls) == 1 and got == "b.ch"


@pytest.mark.unit
def test_disambiguate_tie_llm_invalid_choice_falls_back_to_top():
    fake = FakeClient(result={"domain": "not-in-list.com"})
    got = d.disambiguate_domain("Garage X", "Bern", [("a.ch", 0.81), ("b.ch", 0.80)], client=fake)
    assert got == "a.ch"        # LLM returned a domain outside the candidate set → top scorer


@pytest.mark.unit
def test_disambiguate_empty_returns_none():
    assert d.disambiguate_domain("X", "Y", [], client=FakeClient()) is None


# ── client fail-open (real, no mock) ──────────────────────────────────────────────
@pytest.mark.unit
def test_client_failopen_on_dead_server():
    """A client pointed at a dead port reports unavailable and yields None — never raises."""
    cl = OllamaClient(url="http://127.0.0.1:1", timeout=2)
    assert cl.available() is False
    assert cl.generate_json("hi", schema={"type": "object"}) is None


# ── live integration (skips if no Ollama) ─────────────────────────────────────────
@pytest.mark.integration
def test_live_ollama_classifies_optician_as_non_dealer():
    cl = OllamaClient()
    if not cl.available() or not cl.model_present():
        pytest.skip("ollama/model not available")
    html = _page("AP Optik GmbH", "Augenoptiker Brillen Kontaktlinsen Sehtest auto")  # weak 'auto' → ambiguous
    v = d.classify_is_car_dealer(html, "AP Optik GmbH", "Berlin", client=cl, require_name=False)
    # The live model must recognise an optician is not a car dealer.
    assert v.is_dealer is False
