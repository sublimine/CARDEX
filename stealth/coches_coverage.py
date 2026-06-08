#!/usr/bin/env python3
"""coches.net coverage worker (SSR route, persistent).

coches has no keyless paginating API (host 502), but every brand results page
embeds window.__INITIAL_PROPS__.initialResults.totalResults. So:
  root = totalResults on the all-used-cars page
  per make = totalResults on /{make}/segunda-mano/
  COVERAGE = Σ(make totals) vs root (+ residual = makes outside the list).

One warmed Camoufox session (DataDome bypass); brand pages navigated sequentially
(no browser per ad). RAM-safe. Writes facet/coches_coverage.json incrementally so
a DETACHED run keeps a durable record across idle.
"""
from __future__ import annotations
import json, sys, time, re
from pathlib import Path
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
sys.path.insert(0, str(Path(__file__).resolve().parent))
from extract_state import extract_balanced

EVID = Path(__file__).resolve().parent / "evidence"
OUT = EVID / "facet"; OUT.mkdir(parents=True, exist_ok=True)

# non-make slugs on the coches landing (body types / categories) — excluded
BLOCK = {"4x4", "berlina", "familiar", "monovolumen", "descapotable", "coupe", "cabrio",
         "suv", "furgoneta", "pick-up", "pickup", "todoterreno", "segunda", "ocasion",
         "electricos", "hibridos", "diesel", "gasolina", "km0", "kilometro-0", "comerciales",
         "industriales", "clasicos", "deportivos", "economicos", "familiares"}


def total_of(page) -> int | None:
    try:
        raw = extract_balanced(page.content(), "window.__INITIAL_PROPS__")
        if not raw:
            return None
        d = json.loads(raw)
        return d.get("initialResults", {}).get("totalResults")
    except Exception:
        return None


def main() -> int:
    from camoufox.sync_api import Camoufox
    brands = sorted(set(json.loads((EVID / "coches_brands.json").read_text())) - BLOCK)
    print(f"candidate make slugs: {len(brands)}", flush=True)
    report = {"portal": "coches.net", "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
              "root": None, "per_make": [], "sum_makes": 0, "coverage_pct": None}
    with Camoufox(headless=True, humanize=True, geoip=True) as b:
        page = b.new_page()
        page.goto("https://www.coches.net/", wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(14000)
        # root: all used cars
        try:
            page.goto("https://www.coches.net/segunda-mano/", wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(7000)
            report["root"] = total_of(page)
        except Exception:
            pass
        print(f"ROOT (all used cars) = {report['root']}", flush=True)
        acc = 0
        for i, slug in enumerate(brands):
            try:
                page.goto(f"https://www.coches.net/{slug}/segunda-mano/", wait_until="domcontentloaded", timeout=60000)
                page.wait_for_timeout(4500)
                t = total_of(page)
            except Exception:
                t = None
            if t:
                acc += t
                report["per_make"].append({"make": slug, "count": t})
            report["sum_makes"] = acc
            if report["root"]:
                report["coverage_pct"] = round(100 * acc / report["root"], 2)
            (OUT / "coches_coverage.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
            print(f"  [{i+1}/{len(brands)}] {slug}: {t}  sum={acc:,}  cov={report['coverage_pct']}%", flush=True)
            time.sleep(0.5)
        page.close()
    print(f"\nCOCHES COVERAGE: root={report['root']:,} sum_makes={acc:,} coverage={report['coverage_pct']}%", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
