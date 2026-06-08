#!/usr/bin/env python3
"""T1 Harvest Worker — mobile.de end-to-end validation.

Pipeline (§3.1 Blueprint):
  1. Warm Camoufox past Akamai (one homepage visit + 16s settle)
  2. Load makes via svc/r/ ref endpoint (in-page fetch)
  3. Pick target make (default: Caterham id=5300, count=21 — fits in 2 pages)
  4. Enumerate svc/s/ pages -> normalize records (price/year/mileage)
  5. Dump JSONL to evidence/dumps/mobilede_harvest.jsonl
  6. CLOSE browser (§D.7: never overlap browser + seam write on 600MB host)
  7. Invoke seam_writer -> vehicle_index + SEEN events + stream:enrich_pending
  8. Report BEFORE/AFTER counts from PG

Usage:
    python t1_harvest_worker.py [--make-id 5300] [--make-name Caterham] [--limit 25]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
STEALTH = Path(__file__).resolve().parent
CONFIGS_DIR = REPO / "configs" / "portals"
EVID = STEALTH / "evidence"
DUMPS = EVID / "dumps"
DUMPS.mkdir(parents=True, exist_ok=True)

PORTAL = "mobile.de"
JSONL_OUT = DUMPS / "mobilede_harvest.jsonl"

# ---------- helpers ---------------------------------------------------------

def uhash(u: str) -> str:
    return hashlib.sha256(u.encode("utf-8")).hexdigest()[:32]


def extract_price(raw) -> float | None:
    """Extract EUR gross amount from multiple price shapes including German-format strings."""
    if isinstance(raw, (int, float)):
        # svc/s/ x.p is a float in kEUR (e.g., 18.8 = €18,800)
        v = float(raw)
        return v * 1000.0 if v > 0 else None
    if isinstance(raw, dict):
        for k in ("grossAmount", "amount", "value", "brutto", "gross"):
            v = raw.get(k)
            if isinstance(v, (int, float)):
                return float(v)
            if isinstance(v, str):
                raw = v  # fall through to string parser below
                break
    if isinstance(raw, str):
        # German format strings: "12.500 €", "1\xa0€", "12.500,50 €" — already in EUR
        import re as _re
        s = _re.sub(r"[^\d,.]", "", raw)  # keep digits, comma, dot
        if not s:
            return None
        # if comma present as decimal separator: "12.500,50" -> remove dots, replace comma
        if "," in s:
            s = s.replace(".", "").replace(",", ".")
        else:
            # dots only: either thousands ("12.500") or decimal ("12.5")
            parts = s.split(".")
            if len(parts) > 1 and len(parts[-1]) == 3:
                s = s.replace(".", "")
        try:
            v = float(s)
            return v if v > 0 else None
        except ValueError:
            return None
    return None


def extract_year(item: dict) -> int | None:
    attr = item.get("attr") or {}
    if isinstance(attr, dict):
        for k in ("year", "constructionYear", "firstRegistration", "fr"):
            v = attr.get(k)
            if isinstance(v, int) and 1970 <= v <= 2030:
                return v
            if isinstance(v, str):
                # "MM/YYYY" (mobile.de svc/s/ attr.fr) or "YYYY-MM-DD" or "YYYY"
                import re as _re
                m = _re.search(r"\b(19[7-9]\d|20[012]\d)\b", v)
                if m:
                    return int(m.group(1))
    return None


def extract_mileage(item: dict) -> int | None:
    attr = item.get("attr") or {}
    if isinstance(attr, dict):
        for k in ("mileage", "km", "kilometers", "kilometerstand", "ml"):
            v = attr.get(k)
            if isinstance(v, int) and v >= 0:
                return v
            if isinstance(v, str):
                # "115 400\xa0km" or "115.400 km" — strip all non-digits
                import re as _re
                digits = _re.sub(r"\D", "", v)
                if digits:
                    km = int(digits)
                    if 0 <= km <= 2_000_000:
                        return km
    return None


def normalize(item: dict, source_domain: str, country: str) -> dict:
    raw_url = item.get("url") or ""
    # ensure absolute URL
    if raw_url.startswith("/"):
        raw_url = "https://suchen.mobile.de" + raw_url
    elif not raw_url.startswith("http"):
        raw_url = f"https://suchen.mobile.de/fahrzeuge/details.html?id={item.get('id', '')}"
    # make/model: may be string or {"localized": "..."} object
    def localized(v):
        if isinstance(v, dict):
            return v.get("localized") or v.get("n") or str(v)
        return str(v) if v else ""
    make_str = localized(item.get("make"))
    model_str = localized(item.get("model"))
    title = item.get("title") or item.get("shortTitle") or f"{make_str} {model_str}".strip()
    return {
        "source_url": raw_url,
        "url_hash": uhash(raw_url),
        "source_domain": source_domain,
        "country": country,
        "ext_id": item.get("id"),
        "make": make_str,
        "model": model_str,
        "title": title[:300],
        "price_eur": extract_price(item.get("rawPrice")),
        "year": extract_year(item),
        "mileage_km": extract_mileage(item),
    }


# ---------- Camoufox session ------------------------------------------------

FETCH_JS = """
async (url) => { try {
  const r = await fetch(url, {headers:{'accept':'application/json'}, credentials:'include'});
  const t = await r.text(); let j=null; try{j=JSON.parse(t)}catch(e){}
  return JSON.stringify({status:r.status, total: j&&j.numResultsTotal,
    items: j&&(j.items||[]).map(x=>({id:x.id, makeId:x.makeId, modelId:x.modelId,
      make:x.make, model:x.model, title:x.shortTitle||x.title,
      rawPrice:x.p, url:x.url, attr:x.attr})) });
} catch(e){ return JSON.stringify({error:String(e)}); } }
"""

REF_JS = "async (url)=>{try{const r=await fetch(url,{headers:{'accept':'application/json'},credentials:'include'});return await r.text();}catch(e){return JSON.stringify({error:String(e)})}}"


def warm_and_enumerate(cfg: dict, make_id: str, make_name: str, limit: int) -> list[dict]:
    from camoufox.sync_api import Camoufox

    def search_url(make_id: str, page: int) -> str:
        import re as _re
        fmt = cfg["facet_axes"][0]["format"].replace("{makeId}", str(make_id))
        # api_url template ends with &p=1 — strip it, append actual page
        base = cfg["endpoints"]["api_url"].replace("{filters}", f"&ms={fmt}")
        base = _re.sub(r"[&?]p=\d+$", "", base)
        return f"{base}&p={page}"

    warm_urls = cfg["access"]["warm"]
    page_size = cfg["pagination"]["page_size"]

    records = {}
    print(f"[warm] launching Camoufox headless ...", flush=True)
    t0 = time.time()
    with Camoufox(headless=True, humanize=True, geoip=True) as browser:
        page = browser.new_page()
        for wu in warm_urls:
            print(f"[warm] goto {wu}", flush=True)
            page.goto(wu, wait_until="domcontentloaded", timeout=90000)
            page.wait_for_timeout(16000)
        print(f"[warm] done in {time.time()-t0:.0f}s — querying make {make_name} (id={make_id})", flush=True)

        for pg in range(1, 4):
            url = search_url(make_id, pg)
            print(f"  [page {pg}] {url[:100]}", flush=True)
            try:
                raw = page.evaluate(FETCH_JS, url)
                rec = json.loads(raw)
            except Exception as e:
                print(f"  [page {pg}] ERROR {e}", flush=True)
                break
            items = rec.get("items") or []
            total = rec.get("total")
            print(f"  [page {pg}] status={rec.get('status')} total={total} items_returned={len(items)}", flush=True)
            if not items:
                break
            for it in items:
                nr = normalize(it, PORTAL, cfg["country"])
                records[nr["url_hash"]] = nr
                # show first 3
                if len(records) <= 3:
                    print(f"    sample: {nr['title']!r} price={nr['price_eur']} url={nr['source_url'][:80]}", flush=True)
            if len(records) >= limit:
                break
            time.sleep(0.5)
        print(f"[enumerate] {len(records)} unique records in {time.time()-t0:.0f}s", flush=True)
        page.close()
    return list(records.values())


# ---------- seam writer (subprocess) ----------------------------------------

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


# ---------- DB helpers -------------------------------------------------------

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


# ---------- main ------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--make-id", default="5300", help="mobile.de make id (default: Caterham=5300)")
    ap.add_argument("--make-name", default="Caterham", help="make name for logging")
    ap.add_argument("--limit", type=int, default=25, help="max listings to harvest")
    args = ap.parse_args()

    cfg_path = CONFIGS_DIR / f"{PORTAL}.json"
    if not cfg_path.exists():
        print(f"ERROR: config not found at {cfg_path}"); return 1
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    print(f"[config] loaded {PORTAL} v{cfg.get('version')} strategy={cfg.get('strategy')}", flush=True)

    # BEFORE count
    before = psql_count("mobile")
    print(f"\n=== BEFORE: vehicle_index[mobile.de] = {before} ===\n", flush=True)

    # 1. Warm + enumerate (browser session closed before seam write)
    records = warm_and_enumerate(cfg, args.make_id, args.make_name, args.limit)
    if not records:
        print("ERROR: no records enumerated"); return 1

    # 2. Dump JSONL (browser is already closed)
    JSONL_OUT.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in records),
        encoding="utf-8"
    )
    print(f"\n[dump] wrote {len(records)} records -> {JSONL_OUT}", flush=True)

    # 3. Seam write
    rc = run_seam_writer(JSONL_OUT, PORTAL, cfg["country"], args.limit)
    if rc != 0:
        print(f"ERROR: seam_writer returned {rc}"); return rc

    # 4. AFTER count + samples
    after = psql_count("mobile")
    print(f"\n=== AFTER: vehicle_index[mobile.de] = {after} ===", flush=True)
    samples = psql_samples("mobile")
    print(f"\n--- 5 sample rows ---\n{samples}\n", flush=True)

    # 5. Summary
    print("=" * 60, flush=True)
    print(f"BEFORE : {before}", flush=True)
    print(f"AFTER  : {after}", flush=True)
    print(f"DELTA  : +{int(after or 0) - int(before or 0)}", flush=True)
    result = "SUCCESS" if int(after or 0) > 0 else "FAIL"
    print(f"VERDICT: pipeline T1 end-to-end = {result}", flush=True)
    print("=" * 60, flush=True)
    return 0 if result == "SUCCESS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
