"""Entity verification harness — the deterministic, PG-side spine of the verification team.

This is NOT the old count-only gate. It verifies a finished entity end-to-end across many
INDEPENDENT dimensions, adversarially: every check tries to FAIL the entity, and anything
uncertain is a GAP, never a silent PASS (VAM doctrine: quorum or it is not trustworthy).

Split of labour:
  - THIS module owns every dimension PROVABLE from PG + the canonical source_entities, so the
    verdict has a deterministic, reproducible spine (no network, no judgement, unit-testable).
  - The LIVE/semantic dimensions (re-fetch the source today, diff each persisted field against
    a FRESH detail page, price-trap semantics, ban detection) are the agent-team's job in
    ``verify_entity_team`` — they consume this report and add the paths code can't walk.

Single-source-of-truth guardian: the SOT dimension asserts the entity is described in exactly
ONE canonical place (source_entities in main's PG). A divergent/duplicate source is a GAP whose
remediation is ELIMINATION (gap_router → AUTO_FIX/ELIMINATE), per the owner's one-truth mandate.

    python -m verification.verifier --domain suchen.mobile.de
    python -m verification.verifier --entity se_xxx --declared 1509285   # declared count from agent/live
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from dataclasses import dataclass, field, asdict
from typing import Any

import asyncpg

from scrapers.dealer_scraping.inventory_harvester import _entity_ulid

# Windows consoles default to cp1252 and choke on accented titles / arrows. Make stdout
# UTF-8 safe at import time (single point of repair) so any importer prints cleanly.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
except Exception:  # noqa: BLE001
    pass

DSN = os.environ.get("DATABASE_URL", "postgresql://cardex:cardex_dev_only@localhost:5432/cardex")

# Severity ladder — a gap's weight drives the remediation route (gap_router.py).
CRITICAL, HIGH, MEDIUM, LOW = "CRITICAL", "HIGH", "MEDIUM", "LOW"
PASS, GAP, FAIL, NEEDS_LIVE = "PASS", "GAP", "FAIL", "NEEDS_LIVE"

# Country → expected currency. A row whose currency contradicts its country is a field bug.
_CCY = {"ES": "EUR", "FR": "EUR", "DE": "EUR", "BE": "EUR", "NL": "EUR", "CH": "CHF"}
_YEAR_MIN, _YEAR_MAX = 1950, 2027
_PRICE_MIN, _PRICE_MAX = 100, 10_000_000          # cash-price sanity band (EUR/CHF)
# A price field clustered ENTIRELY in the monthly-payment band is the financing trap tell.
_MONTHLY_TRAP_HI = 2_500


@dataclass
class DimResult:
    dim: str
    status: str                # PASS | GAP | FAIL | NEEDS_LIVE
    severity: str | None = None
    detail: str = ""
    evidence: dict[str, Any] = field(default_factory=dict)


@dataclass
class Verdict:
    entity_ulid: str
    domain: str | None
    kind: str | None
    served: int = 0
    dims: list[DimResult] = field(default_factory=list)

    @property
    def verified(self) -> bool:
        return all(d.status == PASS for d in self.dims)

    @property
    def gaps(self) -> list[DimResult]:
        return [d for d in self.dims if d.status in (GAP, FAIL)]

    def add(self, d: DimResult) -> None:
        self.dims.append(d)


async def _resolve_entity(conn, *, domain: str | None, entity: str | None) -> dict | None:
    if entity:
        row = await conn.fetchrow("SELECT * FROM source_entities WHERE entity_ulid=$1", entity)
    else:
        row = await conn.fetchrow("SELECT * FROM source_entities WHERE source_key=$1 OR domain=$1", domain)
    return dict(row) if row else None


# --------------------------------------------------------------------------- dimensions
async def dim_identity(conn, ent: dict) -> DimResult:
    """Entity exists, entity_ulid is the canonical hash of its domain, kind/country valid."""
    dom = ent.get("domain") or ent.get("source_key")
    canon = _entity_ulid(dom) if dom else None
    problems = []
    if not dom:
        problems.append("domain NULL")
    if canon and canon != ent["entity_ulid"]:
        problems.append(f"entity_ulid {ent['entity_ulid'][:12]} != canonical {canon[:12]} (non-canonical id)")
    if ent.get("kind") not in ("dealer", "platform"):
        problems.append(f"kind={ent.get('kind')!r} not in dealer|platform")
    cc = (ent.get("country") or "").strip()
    if len(cc) != 2:
        problems.append(f"country={cc!r} not 2-letter")
    if problems:
        return DimResult("identity", FAIL, HIGH, "; ".join(problems), {"domain": dom, "kind": ent.get("kind")})
    return DimResult("identity", PASS, detail=f"{dom} kind={ent['kind']} {cc}", evidence={"canonical": True})


async def dim_servability(conn, ent: dict) -> DimResult:
    """The per-entity API view actually serves rows for this entity."""
    n = await conn.fetchval("SELECT count(*) FROM entity_inventory WHERE entity_ulid=$1", ent["entity_ulid"])
    if n == 0:
        return DimResult("servability", FAIL, CRITICAL, "entity_inventory serves 0 rows", {"served": 0})
    return DimResult("servability", PASS, detail=f"served={n}", evidence={"served": n})


async def dim_linkage(conn, ent: dict) -> DimResult:
    """Doctrine: every L1 row for this entity is linked (no orphans); L1 vs served consistent."""
    idx = await conn.fetchval("SELECT count(*) FROM vehicle_index WHERE entity_ulid=$1", ent["entity_ulid"])
    # Orphans = rows on this domain with NO entity link (born-orphan / backfill miss).
    orphan = await conn.fetchval(
        "SELECT count(*) FROM vehicle_index WHERE source_domain=$1 AND entity_ulid IS NULL", ent.get("domain") or ent["source_key"])
    if orphan and orphan > 0:
        return DimResult("linkage", GAP, HIGH, f"{orphan} rows on domain with NULL entity_ulid (servability leak)",
                         {"linked": idx, "orphan": orphan})
    return DimResult("linkage", PASS, detail=f"linked={idx} orphan=0", evidence={"linked": idx})


async def dim_fields(conn, ent: dict) -> DimResult:
    """Field integrity: coverage of price/year/title, sanity bands, currency-vs-country,
    and the financing-trap tell (price field entirely in the monthly-payment band)."""
    e = ent["entity_ulid"]
    row = await conn.fetchrow(
        """SELECT count(*) n,
                  count(price) np, count(year) ny, count(NULLIF(title,'')) nt,
                  count(*) FILTER (WHERE price IS NOT NULL AND (price<$2 OR price>$3)) bad_price,
                  count(*) FILTER (WHERE year IS NOT NULL AND (year<$4 OR year>$5)) bad_year,
                  count(*) FILTER (WHERE price IS NOT NULL AND price>0 AND price<=$6) cheap,
                  count(price) tot_price
           FROM entity_inventory WHERE entity_ulid=$1""",
        e, _PRICE_MIN, _PRICE_MAX, _YEAR_MIN, _YEAR_MAX, _MONTHLY_TRAP_HI)
    n = row["n"] or 0
    if n == 0:
        return DimResult("fields", FAIL, CRITICAL, "no rows", {})
    pct = lambda c: round(100 * (c or 0) / n, 1)
    ev = {"n": n, "price%": pct(row["np"]), "year%": pct(row["ny"]), "title%": pct(row["nt"]),
          "bad_price": row["bad_price"], "bad_year": row["bad_year"]}
    problems, sev = [], MEDIUM
    if row["np"] == 0:
        problems.append("price 100% NULL (extraction broken)"); sev = CRITICAL
    if row["nt"] == 0:
        problems.append("title 100% NULL"); sev = CRITICAL
    if row["bad_price"]:
        problems.append(f"{row['bad_price']} prices out of sane band"); sev = max(sev, HIGH, key=_sev_rank)
    if row["bad_year"]:
        problems.append(f"{row['bad_year']} years out of [{_YEAR_MIN},{_YEAR_MAX}]")
    # Financing-trap tell: every priced row sits in the monthly-payment band → likely /mois, not cash.
    if row["tot_price"] and row["tot_price"] >= 10 and row["cheap"] == row["tot_price"]:
        problems.append(f"ALL {row['tot_price']} prices <= {_MONTHLY_TRAP_HI} — possible monthly-payment trap, not cash"); sev = CRITICAL
    if problems:
        return DimResult("fields", GAP, sev, "; ".join(problems), ev)
    # Thin coverage is a soft gap (price/year should be largely present on a real used-car set).
    if pct(row["np"]) < 60 or pct(row["ny"]) < 50:
        return DimResult("fields", GAP, MEDIUM, f"thin coverage price={pct(row['np'])}% year={pct(row['ny'])}%", ev)
    return DimResult("fields", PASS, detail=f"price={ev['price%']}% year={ev['year%']}% title={ev['title%']}%", evidence=ev)


async def dim_dedup(conn, ent: dict) -> DimResult:
    """No duplicate source_url within the entity; no source_url served under >1 entity."""
    e = ent["entity_ulid"]
    dups = await conn.fetchval(
        "SELECT count(*) FROM (SELECT source_url FROM entity_inventory WHERE entity_ulid=$1 "
        "GROUP BY source_url HAVING count(*)>1) d", e)
    # Cross-entity collision: same listing url served under another entity too (inflation/mis-attribution).
    collide = await conn.fetchval(
        "SELECT count(*) FROM entity_inventory a JOIN entity_inventory b USING(source_url) "
        "WHERE a.entity_ulid=$1 AND b.entity_ulid<>$1", e)
    if dups:
        return DimResult("dedup", FAIL, HIGH, f"{dups} duplicate source_url within entity", {"dups": dups})
    if collide:
        return DimResult("dedup", GAP, HIGH, f"{collide} listings also served under another entity (collision)", {"collide": collide})
    return DimResult("dedup", PASS, detail="no dups, no collision")


async def dim_delta(conn, ent: dict) -> DimResult:
    """The living layer: SEEN events fired; GONE machinery present; freshness of last event."""
    dom = ent.get("domain") or ent["source_key"]
    row = await conn.fetchrow(
        """SELECT count(*) FILTER (WHERE event_type='SEEN') seen,
                  count(*) FILTER (WHERE event_type='GONE') gone,
                  max(ts) last_ts, now()-max(ts) age
           FROM vehicle_events WHERE source_domain=$1""", dom)
    if (row["seen"] or 0) == 0:
        return DimResult("delta", GAP, MEDIUM, "no SEEN events recorded (delta layer never ran)", {"seen": 0})
    ev = {"seen": row["seen"], "gone": row["gone"], "last": str(row["last_ts"]), "age": str(row["age"])}
    return DimResult("delta", PASS, detail=f"seen={row['seen']} gone={row['gone']} last={row['last_ts']}", evidence=ev)


async def dim_staleness(conn, ent: dict) -> DimResult:
    """Served rows not re-seen in a long time may be sold/stale (delta should have GONE-marked)."""
    e = ent["entity_ulid"]
    row = await conn.fetchrow(
        "SELECT count(*) n, count(*) FILTER (WHERE seen_at < now()-interval '14 days') stale FROM entity_inventory WHERE entity_ulid=$1", e)
    if row["n"] and row["stale"] and row["stale"] == row["n"]:
        return DimResult("staleness", GAP, MEDIUM, f"ALL {row['n']} rows not re-seen in 14d (delta stalled?)",
                         {"stale": row["stale"]})
    return DimResult("staleness", PASS, detail=f"stale_14d={row['stale']}/{row['n']}")


async def dim_count_coverage(conn, ent: dict, declared: int | None) -> DimResult:
    """Served-deduped vs the source's own declared total = real coverage. NEEDS_LIVE without a
    declared figure (the agent-team supplies it from the live count oracle, 2 ways)."""
    served = await conn.fetchval("SELECT count(DISTINCT source_url) FROM entity_inventory WHERE entity_ulid=$1", ent["entity_ulid"])
    if not declared:
        return DimResult("count_coverage", NEEDS_LIVE, None, f"served={served}; declared not provided (agent must supply 2-way live count)",
                         {"served": served})
    cov = round(100 * served / declared, 1) if declared else 0
    ev = {"served": served, "declared": declared, "coverage%": cov}
    if cov < 90:
        sev = HIGH if cov < 70 else MEDIUM
        return DimResult("count_coverage", GAP, sev, f"coverage {cov}% (served {served} / declared {declared})", ev)
    return DimResult("count_coverage", PASS, detail=f"coverage={cov}%", evidence=ev)


async def verify_entity(domain: str | None = None, entity: str | None = None,
                        declared: int | None = None, dsn: str = DSN) -> Verdict:
    pool = await asyncpg.create_pool(dsn, min_size=1, max_size=4)
    try:
        async with pool.acquire() as conn:
            await conn.execute("SET max_parallel_workers_per_gather=0")  # shm-safe on the big UNION view
            ent = await _resolve_entity(conn, domain=domain, entity=entity)
            if not ent:
                v = Verdict(entity or domain or "?", domain, None)
                v.add(DimResult("identity", FAIL, CRITICAL, "entity not found in source_entities", {}))
                return v
            v = Verdict(ent["entity_ulid"], ent.get("domain") or ent.get("source_key"), ent.get("kind"))
            v.add(await dim_identity(conn, ent))
            v.add(await dim_servability(conn, ent))
            v.add(await dim_linkage(conn, ent))
            v.add(await dim_fields(conn, ent))
            v.add(await dim_dedup(conn, ent))
            v.add(await dim_delta(conn, ent))
            v.add(await dim_staleness(conn, ent))
            v.add(await dim_count_coverage(conn, ent, declared))
            v.served = await conn.fetchval("SELECT count(*) FROM entity_inventory WHERE entity_ulid=$1", ent["entity_ulid"])
            return v
    finally:
        await pool.close()


def _sev_rank(s: str | None) -> int:
    return {None: 0, LOW: 1, MEDIUM: 2, HIGH: 3, CRITICAL: 4}.get(s, 0)


def render(v: Verdict) -> str:
    icon = {PASS: "PASS", GAP: "GAP ", FAIL: "FAIL", NEEDS_LIVE: "LIVE"}
    head = f"\n===== VERIFY {v.domain}  ({v.entity_ulid[:16]}, kind={v.kind}, served={v.served}) ====="
    lines = [head]
    for d in v.dims:
        sev = f" [{d.severity}]" if d.severity else ""
        lines.append(f"  [{icon.get(d.status, d.status)}] {d.dim:<15}{sev:<11} {d.detail}")
    verdict = "VERIFIED ✓ (all dimensions PASS)" if v.verified else f"NOT VERIFIED — {len(v.gaps)} gap(s) → gap_router"
    lines.append(f"  ----> {verdict}")
    return "\n".join(lines)


async def _main() -> None:
    ap = argparse.ArgumentParser(description="Deterministic entity verification spine")
    ap.add_argument("--domain")
    ap.add_argument("--entity")
    ap.add_argument("--declared", type=int, default=None)
    a = ap.parse_args()
    v = await verify_entity(domain=a.domain, entity=a.entity, declared=a.declared)
    print(render(v))


if __name__ == "__main__":
    asyncio.run(_main())
