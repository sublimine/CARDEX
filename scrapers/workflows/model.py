"""Pure data types for the orchestration army — frozen, no I/O, fully unit-testable.

These are the contracts the pipeline / general / inquisition exchange. Keeping them
pure means the orchestration LOGIC (coverage %, isolation, trust scoring, the
re-verification triggers) is testable against in-memory fakes with zero network/DB.
"""
from __future__ import annotations

from dataclasses import dataclass, field

# The five workflow gate keys, in order.
GATES = ("W1", "W2", "W3", "W4", "W5")


@dataclass(frozen=True)
class GateVerdict:
    """One workflow gate's binary verdict + the INDEPENDENT method that decided it."""

    gate: str            # "W1".."W5"
    pasa: bool
    detail: str
    method: str          # the path that produced the verdict (for the audit trail)


@dataclass(frozen=True)
class DealerResult:
    """A dealer's full pass through W1-W5. ``blocked_reason`` set ⇒ isolated, the line
    continues without it (never blocks)."""

    domain: str
    country: str
    cdx_code: str
    gates: tuple[GateVerdict, ...] = ()
    served: int = 0
    visible_independent: int = 0
    blocked_reason: str | None = None
    elapsed_ms: int = 0

    @property
    def all_pasa(self) -> bool:
        return self.blocked_reason is None and len(self.gates) == len(GATES) \
            and all(g.pasa for g in self.gates)

    @property
    def gates_passed(self) -> int:
        return sum(1 for g in self.gates if g.pasa)

    def gate(self, key: str) -> GateVerdict | None:
        return next((g for g in self.gates if g.gate.startswith(key)), None)


@dataclass(frozen=True)
class GeneralReport:
    """A country General's aggregate after fanning out soldiers over its queue."""

    country: str
    claimed: int                       # dealers pulled from the queue this run
    closed_5of5: int                   # dealers that passed all 5 gates
    blocked: int                       # isolated dealers (recorded, not fatal)
    gate_failures: dict[str, int] = field(default_factory=dict)  # W1..W5 → count NO PASA
    served_total: int = 0              # sum of served inventory across closed dealers
    results: tuple[DealerResult, ...] = ()

    @property
    def closure_rate(self) -> float:
        return round(self.closed_5of5 / self.claimed, 4) if self.claimed else 0.0

    @property
    def worst_gate(self) -> str | None:
        """The gate that blocked the most dealers — where to send reinforcements."""
        if not self.gate_failures:
            return None
        return max(self.gate_failures.items(), key=lambda kv: kv[1])[0]


# ── the Inquisition (separate chain) ─────────────────────────────────────────────
# Re-verification is ALWAYS triggered on these (lesson 2026-06-10: a "0 stock"
# epidemic was a transport bug, not reality). A clean count is not enough — these
# patterns demand an orthogonal re-count before the number is trusted.
def reverify_triggers(count: int, peer_counts: tuple[int, ...] = ()) -> tuple[str, ...]:
    """Return the suspicion flags that force an orthogonal re-count."""
    flags: list[str] = []
    if count == 0:
        flags.append("zero")
    if count > 0 and count % 100 == 0:
        flags.append("round_number")
    if count > 0 and peer_counts.count(count) >= 2:
        flags.append("identical_to_peers")  # shared-bug signature
    return tuple(flags)


@dataclass(frozen=True)
class InquisitionVerdict:
    """Independent re-certification of ONE dealer's count, by a path orthogonal to
    the one the producer used. ``trustworthy`` ⇒ the number survives the second view."""

    domain: str
    producer_count: int       # what W3 served
    inquisitor_count: int     # what the orthogonal path saw
    method: str               # the orthogonal method (e.g. "listing_pagination")
    flags: tuple[str, ...] = ()
    tolerance: int = 2

    @property
    def trustworthy(self) -> bool:
        # A zero that the inquisitor also confirms as zero is honestly dead; a zero the
        # producer reports but the inquisitor refutes (>0) is the false-DEAD signature.
        if self.inquisitor_count == 0 and self.producer_count == 0:
            return True
        return self.inquisitor_count > 0 and \
            abs(self.producer_count - self.inquisitor_count) <= self.tolerance


@dataclass(frozen=True)
class InquisitionReport:
    """The Inquisition's trust verdict over a General's sample."""

    country: str
    sampled: int
    trustworthy: int
    refuted: tuple[InquisitionVerdict, ...] = ()

    @property
    def trust_rate(self) -> float:
        return round(self.trustworthy / self.sampled, 4) if self.sampled else 0.0
