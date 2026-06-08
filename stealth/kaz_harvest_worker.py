#!/usr/bin/env python3
"""Kleinanzeigen.de Harvest Worker — SSR HTML extraction (no Next.js state).

Structure: article[data-adid][data-href] with JSON-LD ImageObject (title)
and innerText containing price/mileage/year (e.g. "37.999 €\n80.971 km\nEZ 03/2020").
No WAF detected from local IP (plain server-side PHP, no challenge).

Usage:
    python kaz_harvest_worker.py [--limit 25] [--pages 2]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
import time
from pathlib import Path

STEALTH = Path(__file__).resolve().parent
DUMPS = STEALTH / "evidence" / "dumps"
DUMPS.mkdir(parents=True, exist_ok=True)

PORTAL = "kleinanzeigen.de"
COUNTRY = "DE"
BASE_URL = "https://www.kleinanzeigen.de"
JSONL_OUT = DUMPS / "kaz_harvest.jsonl"

# JS to extract all articles from the listing page
EXTRACT_JS = r"""
() => {
  var items = [];
  var arts = document.querySelectorAll('article[data-adid]');
  for (var i = 0; i < arts.length; i++) {
    var art = arts[i];
    var jld = art.querySelector('script[type="application/ld+json"]');
    var jldData = null;
    try { jldData = JSON.parse(jld ? jld.textContent : '{}'); } catch(e) {}
    items.push({
      adid: art.getAttribute('data-adid'),
      href: art.getAttribute('data-href'),
      title: jldData ? jldData.title : null,
      fullText: art.innerText
    });
  }
  return JSON.stringify(items);
}
"""


def uhash(u: str) -> str:
    return hashlib.sha256(u.encode("utf-8")).hexdigest()[:32]


def parse_de_number(s: str) -> float | None:
    """Parse German number format: '37.999' -> 37999, '1.350,50' -> 1350.5"""
    s = s.strip()
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    else:
        parts = s.split(".")
        if len(parts) > 1 and len(parts[-1]) == 3:
            s = s.replace(".", "")
    try:
        return float(s)
    except ValueError:
        return None


def parse_article(it: dict) -> dict:
    """Parse title/price/mileage/year from article data."""
    txt = it.get("fullText") or ""
    title = it.get("title") or ""
    href = it.get("href") or ""
    adid = it.get("adid") or ""

    url = BASE_URL + href if href.startswith("/") else href

    # Price: first "N.NNN €" or "NNN €" pattern in text
    price_eur = None
    m = re.search(r"(\d[\d.]*(?:,\d{2})?)\s*€", txt)
    if m:
        price_eur = parse_de_number(m.group(1))

    # Mileage: "N.NNN km" or "NNN km"
    mileage_km = None
    m2 = re.search(r"(\d[\d.]*)\s*km\b", txt, re.IGNORECASE)
    if m2:
        v = parse_de_number(m2.group(1))
        if v is not None and 0 <= v <= 2_000_000:
            mileage_km = int(v)

    # Year: "EZ MM/YYYY" or "EZ YYYY" (Erstzulassung)
    year = None
    m3 = re.search(r"\bEZ\s+(?:\d{2}/)?((?:19|20)\d{2})\b", txt)
    if m3:
        year = int(m3.group(1))

    # Make/model: try to extract from title (first 2 words)
    parts = title.split()
    make = parts[0] if parts else None
    model = " ".join(parts[1:3]) if len(parts) > 1 else None

    return {
        "source_url": url,
        "url_hash": uhash(url),
        "source_domain": PORTAL,
        "country": COUNTRY,
        "ext_id": adid,
        "title": title[:300],
        "make": make,
        "model": model,
        "price_eur": price_eur,
        "mileage_km": mileage_km,
        "year": year,
    }


# ---------- DB helpers ---------------------------------------------------------

def psql_count(src: str) -> str:
    p = subprocess.run(
        ["docker", "exec", "cardex-pg", "psql", "-U", "cardex", "-d", "cardex",
         "-t", "-A", "-c",
         f"SELECT count(*) FROM vehicle_index WHERE source_domain ILIKE '%{src}%';"],
        capture_output=True, text=True)
    return p.stdout.strip()


def psql_samples(src: str) -> str:
    p = subprocess.run(
        ["docker", "exec", "cardex-pg", "psql", "-U", "cardex", "-d", "cardex",
         "-c",
         f"SELECT url_original, titulo_modelo, precio, anio, country "
         f"FROM vehicle_index WHERE source_domain ILIKE '%{src}%' "
         f"ORDER BY created_at DESC LIMIT 5;"],
        capture_output=True, text=True)
    return p.stdout.strip()


def run_seam_writer(jsonl: Path, limit: int) -> int:
    seam = STEALTH / "seam_writer.py"
    cmd = [sys.executable, str(seam),
           "--records", str(jsonl),
           "--source", PORTAL, "--country", COUNTRY, "--limit", str(limit)]
    print(f"\n[seam_writer] {' '.join(cmd)}", flush=True)
    return subprocess.run(cmd, capture_output=False, text=True).returncode


# ---------- Camoufox extraction -----------------------------------------------

def warm_and_extract(limit: int, pages: int) -> list[dict]:
    from camoufox.sync_api import Camoufox

    records: dict[str, dict] = {}
    print("[warm] launching Camoufox ...", flush=True)
    t0 = time.time()

    with Camoufox(headless=True, humanize=True, geoip=True) as browser:
        page = browser.new_page()
        page.goto("https://www.kleinanzeigen.de/", wait_until="domcontentloaded", timeout=90000)
        page.wait_for_timeout(16000)
        print(f"[warm] done in {time.time() - t0:.0f}s", flush=True)

        for pg in range(1, pages + 1):
            if pg == 1:
                url = "https://www.kleinanzeigen.de/s-autos/c216"
            else:
                url = f"https://www.kleinanzeigen.de/s-autos/c216/seite:{pg}"
            print(f"  [page {pg}] {url}", flush=True)
            resp = page.goto(url, wait_until="domcontentloaded", timeout=90000)
            page.wait_for_timeout(7000)
            status = resp.status if resp else None
            raw = page.evaluate(EXTRACT_JS)
            items = json.loads(raw)
            print(f"  [page {pg}] status={status} articles={len(items)}", flush=True)
            if not items:
                print(f"  [page {pg}] no articles — stop", flush=True)
                break
            new = 0
            for it in items:
                r = parse_article(it)
                if not r["source_url"] or r["url_hash"] in records:
                    continue
                records[r["url_hash"]] = r
                new += 1
                if len(records) <= 3:
                    print(f"    sample: {r['title']!r} price={r['price_eur']} "
                          f"year={r['year']} km={r['mileage_km']}", flush=True)
                if len(records) >= limit:
                    break
            print(f"  [page {pg}] new={new} total={len(records)}", flush=True)
            if len(records) >= limit:
                break
            page.wait_for_timeout(1200)
        page.close()

    print(f"[extract] {len(records)} unique records in {time.time() - t0:.0f}s", flush=True)
    return list(records.values())


# ---------- main ---------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=25)
    ap.add_argument("--pages", type=int, default=2)
    args = ap.parse_args()

    before = psql_count("kleinanzeigen")
    print(f"\n=== BEFORE: vehicle_index[{PORTAL}] = {before} ===\n", flush=True)

    records = warm_and_extract(args.limit, args.pages)
    if not records:
        print("RESULT: 0 records — no items extracted")
        print("VERDICT: kleinanzeigen.de = FAIL")
        return 1

    JSONL_OUT.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in records),
        encoding="utf-8")
    print(f"\n[dump] wrote {len(records)} records -> {JSONL_OUT}", flush=True)

    rc = run_seam_writer(JSONL_OUT, args.limit)
    if rc != 0:
        return rc

    after = psql_count("kleinanzeigen")
    print(f"\n=== AFTER: vehicle_index[{PORTAL}] = {after} ===", flush=True)
    samples = psql_samples("kleinanzeigen")
    print(f"\n--- 5 sample rows ---\n{samples}\n", flush=True)

    delta = int(after or 0) - int(before or 0)
    verdict = "SUCCESS" if delta > 0 else "FAIL"
    print("=" * 60, flush=True)
    print(f"BEFORE : {before}", flush=True)
    print(f"AFTER  : {after}", flush=True)
    print(f"DELTA  : +{delta}", flush=True)
    print(f"VERDICT: {PORTAL} = {verdict}", flush=True)
    print("=" * 60, flush=True)
    return 0 if verdict == "SUCCESS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
