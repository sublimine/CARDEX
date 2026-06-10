"""General aggregation + isolation logic (pure, no network/DB)."""
from __future__ import annotations

import pytest

from scrapers.workflows.general import aggregate
from scrapers.workflows.model import GATES, DealerResult, GateVerdict


def _gv(g: str, ok: bool) -> GateVerdict:
    return GateVerdict(g, ok, "", "t")


def _dealer(domain: str, passes: int, *, blocked: str | None = None, served: int = 0) -> DealerResult:
    # first `passes` gates PASA, the rest NO PASA
    gates = tuple(_gv(g, i < passes) for i, g in enumerate(GATES))
    return DealerResult(domain, "ES", "CDX", gates if blocked is None else (), served,
                        blocked_reason=blocked)


@pytest.mark.unit
def test_aggregate_counts_closed_blocked_and_served():
    results = [
        _dealer("a.es", 5, served=235),   # closed 5/5
        _dealer("b.es", 5, served=100),   # closed 5/5
        _dealer("c.es", 3),               # partial (W4/W5 fail)
        _dealer("d.es", 0, blocked="tier1_waf"),  # isolated
    ]
    r = aggregate("ES", claimed=4, results=results)
    assert r.closed_5of5 == 2
    assert r.blocked == 1
    assert r.served_total == 335           # only closed dealers' served
    assert r.closure_rate == 0.5


@pytest.mark.unit
def test_aggregate_gate_failure_histogram_excludes_blocked():
    results = [
        _dealer("a.es", 2),                # W3,W4,W5 fail
        _dealer("b.es", 4),                # W5 fail
        _dealer("c.es", 0, blocked="dns"), # isolated → not counted in gate histogram
    ]
    r = aggregate("ES", claimed=3, results=results)
    # a fails W3,W4,W5 ; b fails W5 → W5 worst (2), W3/W4 = 1 each
    assert r.gate_failures["W5"] == 2
    assert r.gate_failures["W3"] == 1
    assert r.gate_failures["W4"] == 1
    assert r.gate_failures["W1"] == 0
    assert r.worst_gate == "W5"            # send reinforcements to W5


@pytest.mark.unit
def test_blocked_dealer_does_not_inflate_gate_failures():
    results = [_dealer("a.es", 0, blocked="boom")]
    r = aggregate("ES", claimed=1, results=results)
    assert sum(r.gate_failures.values()) == 0   # isolation is not a gate failure
    assert r.blocked == 1
    assert r.closure_rate == 0.0
