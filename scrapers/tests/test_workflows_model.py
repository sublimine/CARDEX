"""Orchestration model — pure logic (coverage %, isolation, re-verify triggers, trust)."""
from __future__ import annotations

import pytest

from scrapers.workflows.model import (
    GATES,
    DealerResult,
    GateVerdict,
    GeneralReport,
    InquisitionReport,
    InquisitionVerdict,
    reverify_triggers,
)


def _gv(gate: str, pasa: bool) -> GateVerdict:
    return GateVerdict(gate=gate, pasa=pasa, detail="", method="test")


def _full(domain: str, *, all_ok: bool = True) -> DealerResult:
    gates = tuple(_gv(g, all_ok) for g in GATES)
    return DealerResult(domain=domain, country="ES", cdx_code="CDX-ES-XXXX", gates=gates)


# ── DealerResult ─────────────────────────────────────────────────────────────────
@pytest.mark.unit
def test_all_pasa_true_only_with_five_gates_all_pass():
    assert _full("a.es", all_ok=True).all_pasa is True


@pytest.mark.unit
def test_all_pasa_false_when_any_gate_fails():
    d = DealerResult("a.es", "ES", "CDX", gates=(_gv("W1", True), _gv("W2", False),
                                                 _gv("W3", True), _gv("W4", True), _gv("W5", True)))
    assert d.all_pasa is False
    assert d.gates_passed == 4


@pytest.mark.unit
def test_blocked_dealer_never_counts_as_pasa():
    d = DealerResult("a.es", "ES", "CDX", gates=tuple(_gv(g, True) for g in GATES),
                     blocked_reason="tier1_waf")
    assert d.all_pasa is False  # isolated, even if gates would pass


@pytest.mark.unit
def test_gate_lookup_by_prefix():
    d = _full("a.es")
    assert d.gate("W3").gate == "W3"
    assert d.gate("W9") is None


# ── GeneralReport aggregation ────────────────────────────────────────────────────
@pytest.mark.unit
def test_general_closure_rate_and_worst_gate():
    r = GeneralReport(country="ES", claimed=10, closed_5of5=6, blocked=1,
                      gate_failures={"W2": 1, "W3": 3, "W5": 0})
    assert r.closure_rate == 0.6
    assert r.worst_gate == "W3"  # reinforce W3


@pytest.mark.unit
def test_general_closure_rate_zero_claims_is_safe():
    assert GeneralReport(country="FR", claimed=0, closed_5of5=0, blocked=0).closure_rate == 0.0
    assert GeneralReport(country="FR", claimed=0, closed_5of5=0, blocked=0).worst_gate is None


# ── re-verify triggers (the Inquisition's paranoia) ──────────────────────────────
@pytest.mark.unit
def test_zero_always_triggers_reverify():
    assert "zero" in reverify_triggers(0)


@pytest.mark.unit
def test_round_number_triggers_reverify():
    assert "round_number" in reverify_triggers(200)
    assert "round_number" not in reverify_triggers(235)


@pytest.mark.unit
def test_identical_to_peers_triggers_reverify():
    # 3 dealers reporting the exact same non-trivial count = shared-bug signature
    assert "identical_to_peers" in reverify_triggers(47, peer_counts=(47, 47, 12))
    assert "identical_to_peers" not in reverify_triggers(47, peer_counts=(47, 12, 9))


# ── InquisitionVerdict trust ─────────────────────────────────────────────────────
@pytest.mark.unit
def test_count_within_tolerance_is_trustworthy():
    v = InquisitionVerdict("a.es", producer_count=235, inquisitor_count=235,
                           method="listing_pagination")
    assert v.trustworthy is True


@pytest.mark.unit
def test_producer_zero_refuted_by_live_inquisitor_is_false_dead():
    # the 2026-06-10 signature: producer says 0, independent path sees stock → NOT trustworthy
    v = InquisitionVerdict("a.es", producer_count=0, inquisitor_count=180,
                           method="listing_pagination")
    assert v.trustworthy is False


@pytest.mark.unit
def test_honest_zero_confirmed_by_inquisitor_is_trustworthy():
    v = InquisitionVerdict("dead.es", producer_count=0, inquisitor_count=0,
                           method="listing_pagination")
    assert v.trustworthy is True


@pytest.mark.unit
def test_large_discrepancy_is_not_trustworthy():
    v = InquisitionVerdict("a.es", producer_count=200, inquisitor_count=235,
                           method="listing_pagination")  # the cap-200 truncation signature
    assert v.trustworthy is False


@pytest.mark.unit
def test_inquisition_report_trust_rate():
    refuted = (InquisitionVerdict("x.es", 200, 235, "listing"),)
    r = InquisitionReport(country="ES", sampled=10, trustworthy=9, refuted=refuted)
    assert r.trust_rate == 0.9
