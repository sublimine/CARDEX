#!/usr/bin/env python3
"""mobile.de REACHABILITY analyzer — measures what % of the 1.58M universe is
enumerable via search faceting, using ONLY the open count API (no browser).

Why this answers "do we get ALL or just 20?":
  - svc/s/ previews top-20; the DESKTOP search route paginates but HARD-CAPS at
    ~50 pages = ~1000 listings/search (CAP). To exceed it you must FACET the
    search so every leaf has <= CAP results, then paginate each leaf.
  - The open consumer count API (hit-count) accepts fr (year range) and p (price
    range), both composable. So we recursively partition year x price; a leaf is
    REACHABLE iff count <= CAP. Price is continuously subdivisible, so almost
    everything is reachable EXCEPT buckets where a single narrow price slice
    still holds > CAP cars (the "saturated" irreducible tail).
  - reachable% = sum_over_leaves(min(count, CAP)) / total. This is exact (counts
    are exact); no listings are stored. Hardware-free: curl_cffi only.

Output: evidence/facet/mobilede_reach.json
"""
from __future__ import annotations
import json, time
from pathlib import Path
from curl_cffi import requests

CAP = 1000                 # desktop pager hard cap: 50 pages x ~20 [VERIFIED mobile_de docstring]
PRICE_MIN_WIDTH = 100      # EUR; below this a >CAP slice is irreducible (saturated)
TOP_PRICE = 1_000_000      # ceiling for open-ended top band
CALL_BUDGET = 4000
SLEEP = 0.18
BASE = "https://m.mobile.de/consumer/api/search/hit-count?dam=false&vc=Car"
OUT = Path(__file__).resolve().parent / "evidence" / "facet" / "mobilede_reach.json"
OUT.parent.mkdir(parents=True, exist_ok=True)

SESS = requests.Session()
state = {"calls": 0, "reachable": 0, "leaves": 0, "saturated": [], "saturated_lost": 0,
         "years": {}, "root": None, "sum_years": 0, "null_year_reach": 0, "budget_hit": False}


def count(fr=None, p=None):
    if state["calls"] >= CALL_BUDGET:
        state["budget_hit"] = True
        return None
    q = BASE
    if fr is not None:
        q += f"&fr={fr[0]}%3A{fr[1]}"
    if p is not None:
        hi = "" if p[1] is None else p[1]
        q += f"&p={p[0]}%3A{hi}"
    for _ in range(3):
        try:
            r = SESS.get(q, impersonate="chrome", timeout=20, headers={"accept": "application/json"})
            state["calls"] += 1
            if r.status_code == 200:
                time.sleep(SLEEP)
                return r.json().get("count")
            if r.status_code in (403, 429):
                time.sleep(3.0)
        except Exception:
            time.sleep(1.0)
    return None


def facet_price(fr, lo, hi):
    """Recurse a price band; accumulate reachable. hi=None means open-ended top."""
    c = count(fr=fr, p=(lo, hi))
    if c is None or c == 0:
        return
    if c <= CAP:
        state["reachable"] += c
        state["leaves"] += 1
        return
    hi_eff = TOP_PRICE if hi is None else hi
    if hi_eff - lo <= PRICE_MIN_WIDTH:
        # irreducible saturated leaf: only CAP reachable from it
        state["reachable"] += CAP
        state["leaves"] += 1
        state["saturated"].append({"fr": fr, "price": [lo, hi], "count": c})
        state["saturated_lost"] += (c - CAP)
        return
    mid = (lo + hi_eff) // 2
    facet_price(fr, lo, mid)
    facet_price(fr, mid, hi)


def main():
    t0 = time.time()
    state["root"] = count()
    print(f"ROOT total = {state['root']:,}  CAP={CAP}", flush=True)
    # year buckets (incl pre-1990 and post-2026 catch-alls)
    buckets = [(1900, 1989)] + [(y, y) for y in range(1990, 2027)] + [(2027, 2030)]
    for fr in buckets:
        if state["budget_hit"]:
            break
        cy = count(fr=fr)
        if cy is None:
            break
        state["years"][f"{fr[0]}:{fr[1]}"] = cy
        state["sum_years"] += cy
        if cy == 0:
            continue
        if cy <= CAP:
            state["reachable"] += cy
            state["leaves"] += 1
        else:
            facet_price(fr, 0, None)
        if cy > CAP or fr[0] >= 2010:
            print(f"  yr {fr[0]}-{fr[1]}: cnt={cy:,} reachable={state['reachable']:,} "
                  f"leaves={state['leaves']} calls={state['calls']} sat={len(state['saturated'])}", flush=True)
        # incremental save
        _save(t0)
    # null/other-year remainder: cars not captured by year buckets -> facet by price only
    remainder = (state["root"] or 0) - state["sum_years"]
    state["null_year_remainder"] = remainder
    if remainder > CAP and not state["budget_hit"]:
        print(f"  null-year remainder ~{remainder:,} -> price-only faceting", flush=True)
        base_reach = state["reachable"]
        facet_price(None, 0, None)
        state["null_year_reach"] = state["reachable"] - base_reach
    elif 0 < remainder <= CAP:
        state["reachable"] += remainder
        state["leaves"] += 1
        state["null_year_reach"] = remainder
    _finalize(t0)
    _save(t0)
    pct = 100.0 * state["reachable"] / state["root"] if state["root"] else 0
    print(f"\n=== REACHABILITY ===", flush=True)
    print(f"root={state['root']:,}  reachable={state['reachable']:,}  PCT={pct:.2f}%", flush=True)
    print(f"leaves={state['leaves']}  saturated_leaves={len(state['saturated'])}  "
          f"lost_to_saturation={state['saturated_lost']:,}", flush=True)
    print(f"calls={state['calls']} budget_hit={state['budget_hit']} elapsed={time.time()-t0:.0f}s", flush=True)
    print(f"WROTE {OUT}", flush=True)


def _finalize(t0):
    state["pct_reachable"] = round(100.0 * state["reachable"] / state["root"], 3) if state["root"] else None
    state["elapsed_s"] = round(time.time() - t0, 1)


def _save(t0):
    state["elapsed_s"] = round(time.time() - t0, 1)
    if state["root"]:
        state["pct_reachable"] = round(100.0 * state["reachable"] / state["root"], 3)
    OUT.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
