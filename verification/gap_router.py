"""Gap → remediation router — "once a gap is detected, what happens?".

The verifier (verifier.py) + the agent-team produce GAP/FAIL dimensions. This module is the
deterministic triage that turns each gap into a concrete REMEDIATION with a route, an action,
and whether it BLOCKS the entity from being marked done. The loop is: verify → gaps → route →
execute → RE-VERIFY → repeat until clean or a declared blocker. No entity is "done" with an
open gap (puerta de finalización); a blocked entity is QUARANTINED, never silently shipped.

Routes
  AUTO_FIX        reversible code/data fix the orchestrator runs now, then re-verify.
  ELIMINATE       a duplicate / divergent / non-additive source — delete it (one-truth mandate).
  RESEARCH        connector dead or a new wall → spawn a rebuild/recon agent (F-TIER1 pattern).
  ESCALATE_GASTO  physically needs spending (residential IP / Akamai sensor) → owner order.
  ESCALATE_OWNER  structural/ambiguous (e.g. aggregator collision) → surface, don't guess.

Coverage gaps branch on the entity's WAF: a proxy-free source under-covered = AUTO_FIX
(multi-pass / per-dealer enumeration); a DataDome/PerimeterX-active source = ESCALATE_GASTO
(the datacenter-IP wall no tool defeats — see ANTIDETECT_ARSENAL).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from verification.verifier import (Verdict, DimResult, CRITICAL, HIGH, MEDIUM, LOW,
                                   GAP, FAIL, NEEDS_LIVE)

AUTO_FIX, ELIMINATE, RESEARCH, ESCALATE_GASTO, ESCALATE_OWNER = (
    "AUTO_FIX", "ELIMINATE", "RESEARCH", "ESCALATE_GASTO", "ESCALATE_OWNER")

# WAFs that gate the datacenter IP itself — coverage there is not a code problem, it's egress.
_GASTO_WAF = ("datadome", "perimeterx", "human", "kasada")


@dataclass
class Remediation:
    dim: str
    route: str
    action: str               # concrete next step (command / agent brief / sql)
    blocks_done: bool         # does this keep the entity quarantined?
    severity: str | None = None


@dataclass
class RemediationPlan:
    entity_ulid: str
    domain: str | None
    remediations: list[Remediation] = field(default_factory=list)

    @property
    def blocked(self) -> bool:
        return any(r.blocks_done for r in self.remediations)

    @property
    def auto(self) -> list[Remediation]:
        return [r for r in self.remediations if r.route in (AUTO_FIX, ELIMINATE)]

    @property
    def needs_owner(self) -> list[Remediation]:
        return [r for r in self.remediations if r.route in (ESCALATE_GASTO, ESCALATE_OWNER)]


def _route_gap(d: DimResult, *, domain: str | None, kind: str | None, waf: str | None) -> Remediation:
    waf_l = (waf or "").lower()
    gasto_walled = any(w in waf_l for w in _GASTO_WAF)

    if d.dim == "identity":
        return Remediation(d.dim, AUTO_FIX,
                           "re-canonicalize entity_ulid=_entity_ulid(domain); fix kind/country in source_entities",
                           blocks_done=True, severity=d.severity)

    if d.dim == "servability":      # 0 rows served
        return Remediation(d.dim, RESEARCH,
                           f"connector produced 0 served rows for {domain}: re-verify the connector is alive vs live "
                           f"source (endpoints rot); if dead, rebuild (F-TIER1 recon). If alive, re-harvest.",
                           blocks_done=True, severity=d.severity)

    if d.dim == "linkage":          # orphan rows, NULL entity_ulid
        return Remediation(d.dim, AUTO_FIX,
                           f"backfill: UPDATE vehicle_index SET entity_ulid=_entity_ulid('{domain}') "
                           f"WHERE source_domain='{domain}' AND entity_ulid IS NULL (idempotent, like the AS24 fix)",
                           blocks_done=True, severity=d.severity)

    if d.dim == "fields":
        trap = "monthly-payment" in d.detail or "100% NULL" in d.detail
        return Remediation(d.dim, AUTO_FIX if not trap else RESEARCH,
                           ("PRICE-TRAP/extraction-break: re-inspect the live detail DOM, fix the field_map to the "
                            "CASH price node, re-harvest" if trap else
                            "fix parser field_map for the thin/out-of-band field, re-harvest the entity"),
                           blocks_done=(d.severity in (CRITICAL, HIGH)), severity=d.severity)

    if d.dim == "dedup":
        if "collision" in d.detail:
            return Remediation(d.dim, ESCALATE_OWNER,
                               "same listing under >1 entity — is the source an aggregator re-listing? "
                               "Decide canonical owner or exclude from served (anti-inflation).",
                               blocks_done=True, severity=d.severity)
        return Remediation(d.dim, AUTO_FIX, "DELETE duplicate source_url rows within entity (keep newest seen_at)",
                           blocks_done=True, severity=d.severity)

    if d.dim == "delta":
        return Remediation(d.dim, AUTO_FIX,
                           "run a full reconcile cycle (complete=True) so SEEN/GONE fire; verify the delta seam wiring",
                           blocks_done=False, severity=d.severity)

    if d.dim == "staleness":
        return Remediation(d.dim, AUTO_FIX,
                           "re-run the entity harvest+reconcile; if rows truly gone from source they must GONE-mark",
                           blocks_done=False, severity=d.severity)

    if d.dim == "count_coverage":
        if gasto_walled:
            return Remediation(d.dim, ESCALATE_GASTO,
                               f"{domain} is {waf}-walled: under-coverage from a datacenter IP is the egress wall "
                               f"(residential/mobile IP, or Hyper/Capsolver sensor) — needs owner gasto order.",
                               blocks_done=True, severity=d.severity)
        if kind == "platform":
            return Remediation(d.dim, AUTO_FIX,
                               f"proxy-free coverage gap: multi-pass union (--passes) to beat list drift, OR pivot to "
                               f"per-dealer API enumeration (each dealer < cap, no drift) — close to ~98% like AS24-FR",
                               blocks_done=True, severity=d.severity)
        return Remediation(d.dim, AUTO_FIX,
                           "dealer under-coverage: re-walk pagination to the true tail; check the cap is not truncating",
                           blocks_done=True, severity=d.severity)

    # default — unknown gap, do not guess
    return Remediation(d.dim, ESCALATE_OWNER, f"unclassified gap: {d.detail}", blocks_done=True, severity=d.severity)


def route(v: Verdict, *, waf: str | None = None) -> RemediationPlan:
    """Turn a verdict's gaps into a remediation plan. NEEDS_LIVE is not a gap (it asks the
    agent-team for the live count) — it routes to the team, not to remediation."""
    plan = RemediationPlan(v.entity_ulid, v.domain)
    for d in v.dims:
        if d.status in (GAP, FAIL):
            plan.remediations.append(_route_gap(d, domain=v.domain, kind=v.kind, waf=waf))
    return plan


def render_plan(plan: RemediationPlan) -> str:
    if not plan.remediations:
        return f"  no gaps → entity VERIFIED, eligible to mark done"
    lines = [f"\n----- REMEDIATION PLAN {plan.domain} ({len(plan.remediations)} gap(s), "
             f"{'QUARANTINED' if plan.blocked else 'fixable-non-blocking'}) -----"]
    for r in plan.remediations:
        block = "BLOCKS" if r.blocks_done else "non-block"
        lines.append(f"  [{r.route:<14}] {r.dim:<15} ({block}) {r.action}")
    if plan.needs_owner:
        lines.append(f"  ==> {len(plan.needs_owner)} item(s) need OWNER (gasto/structural) before this entity can close")
    return "\n".join(lines)
