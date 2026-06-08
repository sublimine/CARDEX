#!/usr/bin/env python3
"""Generic harvest runner — wraps dump_worker.run() + seam_writer for any PORTALS key.

Usage:
    python portal_harvest_runner.py as24_de --limit 20 --pages 1
    python portal_harvest_runner.py coches  --limit 30 --pages 1

Enforces §D.7: browser session closes before seam_writer call.
Reports BEFORE/AFTER counts and 5 sample rows from vehicle_index.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from dump_worker import PORTALS  # noqa: E402

STEALTH = Path(__file__).resolve().parent
DUMPS = STEALTH / "evidence" / "dumps"

PG = "cardex-pg"


def psql_count(pattern: str) -> str:
    p = subprocess.run(
        ["docker", "exec", PG, "psql", "-U", "cardex", "-d", "cardex",
         "-t", "-A", "-c",
         f"SELECT count(*) FROM vehicle_index WHERE source_domain ILIKE '%{pattern}%';"],
        capture_output=True, text=True)
    return p.stdout.strip()


def psql_samples(pattern: str) -> str:
    p = subprocess.run(
        ["docker", "exec", PG, "psql", "-U", "cardex", "-d", "cardex",
         "-c",
         f"SELECT url_original, titulo_modelo, precio, anio, country "
         f"FROM vehicle_index WHERE source_domain ILIKE '%{pattern}%' "
         f"ORDER BY created_at DESC LIMIT 5;"],
        capture_output=True, text=True)
    return p.stdout.strip()


def run_seam_writer(jsonl_path: Path, source: str, country: str, limit: int) -> int:
    seam = STEALTH / "seam_writer.py"
    cmd = [sys.executable, str(seam),
           "--records", str(jsonl_path),
           "--source", source, "--country", country, "--limit", str(limit)]
    print(f"\n[seam_writer] {' '.join(cmd)}", flush=True)
    return subprocess.run(cmd, capture_output=False, text=True).returncode


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("portal", choices=list(PORTALS.keys()))
    ap.add_argument("--limit", type=int, default=20)
    ap.add_argument("--pages", type=int, default=1)
    args = ap.parse_args()

    cfg = PORTALS[args.portal]
    domain = cfg["domain"]
    country = cfg["country"]
    jsonl = DUMPS / f"{args.portal}_harvest.jsonl"
    # pattern for ILIKE query (strip TLD)
    pattern = domain.split(".")[0]

    # BEFORE
    before = psql_count(pattern)
    print(f"\n=== BEFORE: vehicle_index[{domain}] = {before} ===\n", flush=True)

    # Run dump_worker extraction (browser closes after this)
    from dump_worker import run as dw_run
    t0 = time.time()
    rc = dw_run(args.portal, args.limit, purge=False, max_pages=args.pages)
    elapsed = time.time() - t0
    print(f"[dump_worker] rc={rc} elapsed={elapsed:.0f}s", flush=True)

    if not jsonl.exists() or jsonl.stat().st_size < 10:
        print(f"\nRESULT: no harvest file produced — portal likely BLOCKED or no items")
        print(f"VERDICT: {domain} = BLOCKED/FAIL (proxy/VPS may be required)")
        return 1

    # Seam write (browser already closed)
    rc2 = run_seam_writer(jsonl, domain, country, args.limit)
    if rc2 != 0:
        print(f"ERROR: seam_writer returned {rc2}"); return rc2

    # AFTER
    after = psql_count(pattern)
    print(f"\n=== AFTER: vehicle_index[{domain}] = {after} ===", flush=True)
    samples = psql_samples(pattern)
    print(f"\n--- 5 sample rows ---\n{samples}\n", flush=True)

    delta = int(after or 0) - int(before or 0)
    verdict = "SUCCESS" if delta > 0 else "FAIL"
    print("=" * 60, flush=True)
    print(f"BEFORE : {before}", flush=True)
    print(f"AFTER  : {after}", flush=True)
    print(f"DELTA  : +{delta}", flush=True)
    print(f"VERDICT: {domain} = {verdict}", flush=True)
    print("=" * 60, flush=True)
    return 0 if verdict == "SUCCESS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
