#!/usr/bin/env python3
"""LBC Harvest Worker — leboncoin.fr DataDome validation.

Pipeline (same pattern as t1_harvest_worker.py §3.1 Blueprint):
  1. Warm Camoufox past DataDome (homepage 15s + settle rounds on search)
  2. Extract __NEXT_DATA__.props.pageProps.searchData.ads (SSR state)
  3. Normalize records (price/year/mileage via _lbc_norm from dump_worker)
  4. Dump JSONL to evidence/dumps/leboncoin_harvest.jsonl
  5. CLOSE browser (§D.7)
  6. Invoke seam_writer -> vehicle_index + SEEN events + stream:enrich_pending
  7. Report BEFORE/AFTER counts from PG

Usage:
    python lbc_harvest_worker.py [--limit 35] [--pages 1]
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
STEALTH = Path(__file__).resolve().parent
EVID = STEALTH / "evidence"
DUMPS = EVID / "dumps"
DUMPS.mkdir(parents=True, exist_ok=True)

PORTAL = "leboncoin.fr"
COUNTRY = "FR"
JSONL_OUT = DUMPS / "leboncoin_harvest.jsonl"


# ---------- DB helpers ---------------------------------------------------------

def psql_count(source: str) -> str:
    cmd = ["docker", "exec", "cardex-pg", "psql", "-U", "cardex", "-d", "cardex",
           "-t", "-A", "-c",
           f"SELECT count(*) FROM vehicle_index WHERE source_domain ILIKE '%{source}%';"]
    p = subprocess.run(cmd, capture_output=True, text=True)
    return p.stdout.strip()


def psql_samples(source: str) -> str:
    cmd = ["docker", "exec", "cardex-pg", "psql", "-U", "cardex", "-d", "cardex",
           "-c",
           f"SELECT url_original, titulo_modelo, precio, anio, country "
           f"FROM vehicle_index WHERE source_domain ILIKE '%{source}%' "
           f"ORDER BY created_at DESC LIMIT 5;"]
    p = subprocess.run(cmd, capture_output=True, text=True)
    return p.stdout.strip()


# ---------- seam writer (subprocess) ------------------------------------------

def run_seam_writer(jsonl_path: Path, source: str, country: str, limit: int) -> int:
    seam_script = STEALTH / "seam_writer.py"
    cmd = [
        sys.executable, str(seam_script),
        "--records", str(jsonl_path),
        "--source", source,
        "--country", country,
        "--limit", str(limit),
    ]
    print(f"\n[seam_writer] {' '.join(cmd)}", flush=True)
    result = subprocess.run(cmd, capture_output=False, text=True)
    return result.returncode


# ---------- Camoufox + extraction ---------------------------------------------

SETTLE_ROUNDS = 3   # DataDome: up to 3 settle rounds (9s each) after initial 7s wait
SETTLE_MS = 9000


def _classify_body(body: str) -> str:
    """Minimal DataDome blocker detector (no harness import needed)."""
    low = body.lower()
    if any(k in low for k in ("datadome", "please verify you are a human",
                               "jshandler", "ddcaptcha", "robot detection")):
        return "BLOCKED"
    return "OK"


def warm_and_extract(page_url: str, warm_url: str, limit: int, pages: int) -> list[dict]:
    """Returns normalized records or empty list on block."""
    # Import dump_worker normalizer + extractor
    sys.path.insert(0, str(STEALTH))
    from dump_worker import _lbc_norm, _url_lbc  # noqa: E402
    from extract_state import extract_balanced, walk_find_lists, get_path  # noqa: E402

    STATE_VARS = ["__NEXT_DATA__", "window.__INITIAL_PROPS__"]

    def _pick(html: str) -> list:
        for var in STATE_VARS:
            raw = extract_balanced(html, var)
            if not raw:
                continue
            try:
                data = json.loads(raw) if isinstance(raw, str) else raw
            except Exception:
                continue
            lists = walk_find_lists(data)
            lists.sort(key=lambda t: ("searchData.ads" in t[0], t[1]), reverse=True)
            if lists:
                try:
                    return get_path(data, lists[0][0]) or []
                except Exception:
                    continue
        return []

    import hashlib

    def uhash(u: str) -> str:
        return hashlib.sha256(u.encode("utf-8")).hexdigest()[:32]

    from camoufox.sync_api import Camoufox

    print(f"[warm] launching Camoufox headless ...", flush=True)
    t0 = time.time()
    records: dict[str, dict] = {}

    with Camoufox(headless=True, humanize=True, geoip=True) as browser:
        page = browser.new_page()
        print(f"[warm] goto {warm_url}", flush=True)
        page.goto(warm_url, wait_until="domcontentloaded", timeout=90000)
        page.wait_for_timeout(20000)   # DataDome: longer warm than Akamai
        print(f"[warm] done in {time.time() - t0:.0f}s", flush=True)

        for pg in range(1, pages + 1):
            url = page_url.format(page=pg)
            print(f"  [page {pg}] goto {url[:90]}", flush=True)
            try:
                resp = page.goto(url, wait_until="domcontentloaded", timeout=90000)
                status = resp.status if resp else None
            except Exception as e:
                print(f"  [page {pg}] goto error: {e}", flush=True)
                break

            page.wait_for_timeout(8000)
            body = page.content()
            verdict = _classify_body(body)
            print(f"  [page {pg}] status={status} verdict={verdict} body_len={len(body)}", flush=True)

            settle_left = SETTLE_ROUNDS
            while verdict == "BLOCKED" and settle_left > 0:
                settle_left -= 1
                print(f"  [settle] DataDome challenge detected — waiting {SETTLE_MS // 1000}s ...", flush=True)
                page.wait_for_timeout(SETTLE_MS)
                try:
                    page.reload(wait_until="domcontentloaded", timeout=90000)
                except Exception:
                    pass
                page.wait_for_timeout(8000)
                body = page.content()
                verdict = _classify_body(body)
                print(f"  [settle] after round={SETTLE_ROUNDS - settle_left}: verdict={verdict}", flush=True)

            if verdict == "BLOCKED":
                # Capture evidence
                title = page.title()
                print(f"  [BLOCKED] DataDome held after {SETTLE_ROUNDS} settle rounds", flush=True)
                print(f"  [BLOCKED] page title: {title!r}", flush=True)
                print(f"  [BLOCKED] body snippet: {body[:500]!r}", flush=True)
                break

            items = _pick(body)
            print(f"  [page {pg}] items extracted: {len(items)}", flush=True)
            if not items:
                print(f"  [page {pg}] no items — check structure or DataDome soft-block", flush=True)
                # print small snippet for debugging
                print(f"  body snippet: {body[:400]!r}", flush=True)
                break

            for it in items:
                if not isinstance(it, dict):
                    continue
                u = _url_lbc(it)
                if not u or uhash(u) in records:
                    continue
                h = uhash(u)
                base = {"source_url": u, "url_hash": h,
                        "source_domain": PORTAL, "country": COUNTRY}
                base.update(_lbc_norm(it))
                records[h] = base
                if len(records) <= 3:
                    print(f"    sample: {base.get('title', '')!r} "
                          f"price={base.get('price_eur')} "
                          f"url={u[:80]}", flush=True)
                if len(records) >= limit:
                    break

            print(f"  [page {pg}] unique records so far: {len(records)}", flush=True)
            if len(records) >= limit:
                break
            page.wait_for_timeout(1500)

        page.close()

    print(f"[extract] {len(records)} unique records in {time.time() - t0:.0f}s", flush=True)
    return list(records.values())


# ---------- main ---------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=35, help="max listings (default: 35 = 1 page)")
    ap.add_argument("--pages", type=int, default=1, help="max search pages (default: 1)")
    args = ap.parse_args()

    before = psql_count("leboncoin")
    print(f"\n=== BEFORE: vehicle_index[leboncoin.fr] = {before} ===\n", flush=True)

    records = warm_and_extract(
        page_url="https://www.leboncoin.fr/recherche?category=2&page={page}",
        warm_url="https://www.leboncoin.fr/",
        limit=args.limit,
        pages=args.pages,
    )

    if not records:
        print("\nRESULT: 0 records harvested — DataDome blocked or no items extracted")
        print("VERDICT: pipeline T3 DataDome = BLOCKED (proxy/VPS required)")
        return 1

    # Dump JSONL (browser already closed)
    JSONL_OUT.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in records),
        encoding="utf-8"
    )
    print(f"\n[dump] wrote {len(records)} records -> {JSONL_OUT}", flush=True)

    # Seam write
    rc = run_seam_writer(JSONL_OUT, PORTAL, COUNTRY, args.limit)
    if rc != 0:
        print(f"ERROR: seam_writer returned {rc}"); return rc

    after = psql_count("leboncoin")
    print(f"\n=== AFTER: vehicle_index[leboncoin.fr] = {after} ===", flush=True)
    samples = psql_samples("leboncoin")
    print(f"\n--- 5 sample rows ---\n{samples}\n", flush=True)

    delta = int(after or 0) - int(before or 0)
    print("=" * 60, flush=True)
    print(f"BEFORE : {before}", flush=True)
    print(f"AFTER  : {after}", flush=True)
    print(f"DELTA  : +{delta}", flush=True)
    result = "SUCCESS" if delta > 0 else "FAIL"
    print(f"VERDICT: pipeline T3 DataDome = {result}", flush=True)
    print("=" * 60, flush=True)
    return 0 if result == "SUCCESS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
