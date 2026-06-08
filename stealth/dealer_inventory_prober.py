#!/usr/bin/env python3
"""Dealer domain inventory prober — stratified async HTTP sample.

Probes 1000 randomly sampled dealer domains (proportional by country) to
classify each as T1/T2/T3/DEAD for inventory yield estimation.

Probe strategy (cheap → expensive):
  1. HEAD https:// → liveness, redirect, WAF headers
  2. GET homepage (30KB limit) → WAF body, JSON-LD Vehicle, inventory URL patterns
  3. GET /sitemap.xml (100KB limit) → vehicle URL patterns, count estimate

Classification:
  T1  = inventory signals + WAF detected (needs Camoufox / proxy)
  T2  = inventory signals, no serious WAF (cost-zero harvestable)
  T3  = alive, no inventory signals
  DEAD = timeout / NXDOMAIN / parked / refused

Usage:
    python dealer_inventory_prober.py [--concurrency 25] [--sample 1000] [--dry-run]
"""
from __future__ import annotations

import argparse
import asyncio
import json
import re
import ssl
import sys
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional

import aiohttp
import psycopg2

# ── DB ────────────────────────────────────────────────────────────────────────

DB_URL = "postgresql://cardex:cardex_dev_only@127.0.0.1:5432/cardex"

# ── Signals & patterns ────────────────────────────────────────────────────────

VEHICLE_URL_RE = re.compile(
    r'(?:'
    # German
    r'/gebrauchtwagen|/occasionen?|/neuwagen?|/angebote?|/fahrzeuge?|/gebraucht'
    r'|/auto(?:s)?/'
    # French
    r'|/voitures?|/occasions?|/vehicules?|/nos-vehicules?|/occasion-'
    r'|/annonce'
    # Spanish
    r'|/coches?|/vehiculos?|/segunda-mano|/ocasion'
    # English / neutral
    r'|/stock|/inventory|/used-cars?|/pre-owned|/vehicles?'
    r'|/cars?/|/listings?'
    # Short slugs common in DMS URLs
    r'|/vo/|/vn/|/vd/'
    r')',
    re.I,
)

VEHICLE_JSONLD_TYPES = frozenset({
    'car', 'vehicle', 'motorizedvehicle', 'automobile',
    'product', 'offercatalog', 'itemlist',
})

WAF_CF_HEADERS = frozenset({'cf-ray', 'cf-cache-status', 'cf-request-id'})
WAF_DD_HEADERS = frozenset({'x-datadome', 'x-datadome-cid'})
WAF_AK_HEADERS = frozenset({'x-akamai-transformed', 'x-akamai-request-id', 'akamai-grn'})

PARKED_RE = re.compile(
    r'domain.{0,20}(?:for sale|zu verkaufen|à vendre|te koop)'
    r'|sedoparking|hugedomains|namecheap\.com/domains'
    r'|godaddy\.com/domain|dan\.com/domain|register\.com/domain'
    r'|parking(?:page|service)|this domain(?:\s+is)?\s+(?:available|parked)',
    re.I,
)

DMS_RE = re.compile(
    r'mobile\.de[\-\s/]widget|autoscout24[\-\s]widget'
    r'|dealersocket|cdkglobal|cdk\s+global'
    r'|dealer\.com|dealer-socket|dealerfire'
    r'|eDealer|motortrak|autofusion|autotrader\.com/dealer'
    r'|autowebbi|autobiz|carsales\.com\.au/dealer'
    r'|autobinaire|autovista|incadea|automaster'
    r'|car\.gr/dealer|automobile-propre',
    re.I,
)

INVENTORY_COUNT_RE = re.compile(
    r'(\d+)\s*(?:fahrzeuge?|voitures?|coches?|vehicles?|cars?|véhicules?'
    r'|occasions?|gebrauchtwagen|annonces?|angebote?)',
    re.I,
)

# ── Data classes ──────────────────────────────────────────────────────────────

@dataclass
class ProbeResult:
    domain: str
    country: str
    alive: bool = False
    final_url: Optional[str] = None
    http_status: Optional[int] = None
    waf: Optional[str] = None         # cloudflare|datadome|akamai|perimeter_x|other
    parked: bool = False
    has_inventory: bool = False
    signals: list = field(default_factory=list)
    vehicle_count_est: Optional[int] = None
    tier: str = "DEAD"
    error: Optional[str] = None
    probe_ms: int = 0

# ── Async prober ──────────────────────────────────────────────────────────────

SSL_CTX = ssl.create_default_context()
SSL_CTX.check_hostname = False
SSL_CTX.verify_mode = ssl.CERT_NONE


async def _read_limited(resp: aiohttp.ClientResponse, max_bytes: int) -> bytes:
    body = b""
    async for chunk in resp.content.iter_chunked(4096):
        body += chunk
        if len(body) >= max_bytes:
            break
    return body


def _detect_waf_headers(headers: dict) -> Optional[str]:
    low = {k.lower() for k in headers}
    if low & WAF_CF_HEADERS or headers.get("server", "").lower() == "cloudflare":
        return "cloudflare"
    if low & WAF_DD_HEADERS:
        return "datadome"
    if low & WAF_AK_HEADERS:
        return "akamai"
    return None


def _detect_waf_body(text: str) -> Optional[str]:
    if "datadome" in text or "ddcaptcha" in text or "jshandler" in text:
        return "datadome"
    if "__cf_chl" in text or "cf-challenge" in text:
        return "cloudflare"
    if "_pxhd" in text or "perimeterx" in text or "px_block_page" in text:
        return "perimeter_x"
    if "akamai" in text and ("reference #" in text or "access denied" in text):
        return "akamai"
    return None


def _parse_homepage(text_raw: str, signals: list, result: ProbeResult) -> None:
    text = text_raw.lower()

    if PARKED_RE.search(text_raw):
        result.parked = True
        return

    # WAF from body
    if not result.waf:
        result.waf = _detect_waf_body(text)

    # Inventory URL patterns in page links
    if VEHICLE_URL_RE.search(text):
        signals.append("url_pattern")

    # DMS fingerprint
    m = DMS_RE.search(text_raw)
    if m:
        signals.append(f"dms:{m.group()[:30]}")

    # Vehicle count estimate from text
    cm = INVENTORY_COUNT_RE.search(text_raw)
    if cm:
        try:
            n = int(cm.group(1).replace(".", "").replace(",", ""))
            if 1 <= n <= 50000:
                result.vehicle_count_est = n
                signals.append(f"count_text:{n}")
        except ValueError:
            pass

    # JSON-LD @type check (up to 5 blocks)
    for jld_raw in re.findall(
        r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        text_raw, re.DOTALL | re.I
    )[:5]:
        try:
            data = json.loads(jld_raw)
            graphs = data.get("@graph", [data]) if isinstance(data, dict) else [data]
            for node in (graphs if isinstance(graphs, list) else [graphs]):
                t = node.get("@type", "")
                types = [t] if isinstance(t, str) else (t if isinstance(t, list) else [])
                if any(x.lower() in VEHICLE_JSONLD_TYPES for x in types):
                    signals.append("jsonld_vehicle")
                    break
        except Exception:
            pass


def _parse_sitemap(sm_raw: str, signals: list, result: ProbeResult) -> None:
    if VEHICLE_URL_RE.search(sm_raw):
        signals.append("sitemap_vehicle_urls")
    url_count = sm_raw.count("<url>") or sm_raw.count("<sitemap>")
    if url_count > 5 and VEHICLE_URL_RE.search(sm_raw):
        result.vehicle_count_est = max(result.vehicle_count_est or 0, url_count)
        signals.append(f"sitemap_urls:{url_count}")


async def probe(session: aiohttp.ClientSession, domain: str, country: str,
                timeout: int = 6) -> ProbeResult:
    t0 = time.monotonic()
    result = ProbeResult(domain=domain, country=country)
    signals: list[str] = []

    base_https = f"https://{domain}"
    base_http = f"http://{domain}"

    try:
        # ── Step 1: HEAD (https first) ─────────────────────────────────────
        try:
            head = await session.head(
                base_https,
                timeout=aiohttp.ClientTimeout(total=timeout),
                ssl=SSL_CTX,
                allow_redirects=True,
            )
            result.alive = True
            result.http_status = head.status
            result.final_url = str(head.url)
            result.waf = _detect_waf_headers(dict(head.headers))
        except Exception:
            # HTTP fallback
            head = await session.head(
                base_http,
                timeout=aiohttp.ClientTimeout(total=timeout),
                ssl=SSL_CTX,
                allow_redirects=True,
            )
            result.alive = True
            result.http_status = head.status
            result.final_url = str(head.url)
            result.waf = _detect_waf_headers(dict(head.headers))

        # ── Step 2: GET homepage (30 KB) ───────────────────────────────────
        base = f"https://{domain}" if result.final_url and result.final_url.startswith("https") else base_http
        try:
            get = await session.get(
                base,
                timeout=aiohttp.ClientTimeout(total=timeout + 3),
                ssl=SSL_CTX,
                allow_redirects=True,
                headers={"Accept": "text/html", "Accept-Language": "de,fr,es,nl,en;q=0.5"},
            )
            body = await _read_limited(get, 30_720)
            text = body.decode("utf-8", errors="replace")
            _parse_homepage(text, signals, result)
        except Exception:
            pass

        if result.parked:
            result.tier = "DEAD"
            result.probe_ms = int((time.monotonic() - t0) * 1000)
            return result

        # ── Step 3: /sitemap.xml (100 KB) ─────────────────────────────────
        try:
            sm = await session.get(
                f"{base}/sitemap.xml",
                timeout=aiohttp.ClientTimeout(total=timeout),
                ssl=SSL_CTX,
                allow_redirects=True,
            )
            if sm.status == 200:
                sm_body = await _read_limited(sm, 102_400)
                sm_text = sm_body.decode("utf-8", errors="replace")
                _parse_sitemap(sm_text, signals, result)
        except Exception:
            pass

    except (
        aiohttp.ClientConnectorError,
        aiohttp.ServerConnectionError,
        aiohttp.ClientOSError,
        asyncio.TimeoutError,
        Exception,
    ) as exc:
        result.error = type(exc).__name__

    result.signals = signals
    result.has_inventory = bool(signals)

    # ── Classify ───────────────────────────────────────────────────────────
    if not result.alive or result.parked:
        result.tier = "DEAD"
    elif result.has_inventory:
        result.tier = "T1" if result.waf else "T2"
    else:
        result.tier = "T3"

    result.probe_ms = int((time.monotonic() - t0) * 1000)
    return result


# ── DB helpers ────────────────────────────────────────────────────────────────

STRATA = {"BE": 27, "CH": 91, "DE": 590, "ES": 39, "FR": 112, "NL": 141}


def fetch_sample(conn) -> list[tuple[int, str, str]]:
    rows = []
    with conn.cursor() as cur:
        for country, n in STRATA.items():
            cur.execute(
                """
                SELECT id, domain, country
                FROM discovery_candidates
                WHERE domain IS NOT NULL
                  AND sitemap_status = 'pending'
                  AND country = %s
                ORDER BY random()
                LIMIT %s
                """,
                (country, n),
            )
            rows.extend(cur.fetchall())
    return rows


def write_results(conn, results: list[ProbeResult]) -> None:
    # sitemap_status check constraint allows: pending|probing|found|none|error|deferred
    # Map: T1/T2 (has inventory) → 'found', T3/DEAD → 'none', error → 'error'
    def _sitemap_status(r: ProbeResult) -> str:
        if r.tier in ("T1", "T2"):
            return "found"
        if r.error:
            return "error"
        return "none"

    with conn.cursor() as cur:
        for r in results:
            signals_json = json.dumps({
                "signals": r.signals,
                "waf": r.waf,
                "http_status": r.http_status,
                "vehicle_count_est": r.vehicle_count_est,
                "parked": r.parked,
                "final_url": r.final_url,
                "probe_ms": r.probe_ms,
                "error": r.error,
            })
            cur.execute(
                """
                UPDATE discovery_candidates
                SET inventory_tier = %s,
                    inventory_probed_at = NOW(),
                    inventory_signals = %s::jsonb,
                    sitemap_status = %s,
                    sitemap_probed_at = NOW()
                WHERE domain = %s AND country = %s
                """,
                (r.tier, signals_json, _sitemap_status(r), r.domain, r.country),
            )
    conn.commit()


# ── Runner ────────────────────────────────────────────────────────────────────

async def run_probes(rows: list[tuple], concurrency: int, dry_run: bool) -> list[ProbeResult]:
    sem = asyncio.Semaphore(concurrency)
    results: list[ProbeResult] = []

    connector = aiohttp.TCPConnector(limit=concurrency + 5, ssl=False)
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }

    async with aiohttp.ClientSession(connector=connector, headers=headers) as session:
        t_start = time.monotonic()
        done = 0

        async def probe_one(row):
            nonlocal done
            _id, domain, country = row
            async with sem:
                if dry_run:
                    return ProbeResult(domain=domain, country=country, tier="T3", alive=True)
                return await probe(session, domain, country)

        tasks = [asyncio.create_task(probe_one(row)) for row in rows]

        for coro in asyncio.as_completed(tasks):
            r = await coro
            results.append(r)
            done += 1
            if done % 50 == 0 or done == len(rows):
                elapsed = time.monotonic() - t_start
                rps = done / elapsed if elapsed > 0 else 0
                alive = sum(1 for x in results if x.alive)
                inv = sum(1 for x in results if x.has_inventory)
                print(
                    f"  [{done}/{len(rows)}] alive={alive} inv={inv} "
                    f"elapsed={elapsed:.0f}s rps={rps:.1f}",
                    flush=True,
                )

    return results


def print_report(results: list[ProbeResult], sample_rows: list) -> None:
    total = len(results)
    countries = {}
    for r in results:
        countries.setdefault(r.country, []).append(r)

    alive = [r for r in results if r.alive]
    t1 = [r for r in results if r.tier == "T1"]
    t2 = [r for r in results if r.tier == "T2"]
    t3 = [r for r in results if r.tier == "T3"]
    dead = [r for r in results if r.tier == "DEAD"]
    waf = [r for r in results if r.waf]
    inv = [r for r in results if r.has_inventory]

    print("\n" + "=" * 68)
    print("DEALER INVENTORY PROBE — RESULTS")
    print("=" * 68)
    print(f"\nSample: {total} domains  |  Concurrency probed async")
    print(f"\nReparto por país:")
    for c, rows_c in sorted(countries.items()):
        n = len(rows_c)
        a = sum(1 for r in rows_c if r.alive)
        i = sum(1 for r in rows_c if r.has_inventory)
        print(f"  {c}: {n:4d}  alive={a:4d}({a*100//n:2d}%)  inv={i:3d}({i*100//n:2d}%)")

    print(f"""
TABLA RENDIMIENTO (n={total}):
  Vivos       : {len(alive):4d}  ({len(alive)*100//total:.1f}%)
  Con inventario : {len(inv):4d}  ({len(inv)*100//total:.1f}%)
  Con WAF     : {len(waf):4d}  ({len(waf)*100//total:.1f}%)
  Muertos     : {len(dead):4d}  ({len(dead)*100//total:.1f}%)

  T1 (inv+WAF)  : {len(t1):4d}  ({len(t1)*100//total:.1f}%)
  T2 (inv+noWAF): {len(t2):4d}  ({len(t2)*100//total:.1f}%)
  T3 (vivo+noinv): {len(t3):4d}  ({len(t3)*100//total:.1f}%)
  DEAD          : {len(dead):4d}  ({len(dead)*100//total:.1f}%)""")

    # WAF breakdown
    waf_counts: dict[str, int] = {}
    for r in waf:
        waf_counts[r.waf or "other"] = waf_counts.get(r.waf or "other", 0) + 1
    print(f"\n  WAF breakdown: {dict(sorted(waf_counts.items(), key=lambda x: -x[1]))}")

    # Extrapolation to 49390
    universe = 49390
    p_inv = len(inv) / total
    p_t2 = len(t2) / total
    p_t1 = len(t1) / total
    p_dead = len(dead) / total

    # 95% CI using normal approx
    import math
    def ci95(p, n):
        margin = 1.96 * math.sqrt(p * (1 - p) / n)
        return max(0, p - margin), min(1, p + margin)

    ci_inv = ci95(p_inv, total)
    ci_t2 = ci95(p_t2, total)

    est_inv = int(p_inv * universe)
    est_inv_lo = int(ci_inv[0] * universe)
    est_inv_hi = int(ci_inv[1] * universe)
    est_t2 = int(p_t2 * universe)
    est_t2_lo = int(ci_t2[0] * universe)
    est_t2_hi = int(ci_t2[1] * universe)

    print(f"""
EXTRAPOLACIÓN a {universe:,} dominios (IC 95%):
  Con inventario : {est_inv:6,}  [{est_inv_lo:,} – {est_inv_hi:,}]
  T2 (cos-cero)  : {est_t2:6,}  [{est_t2_lo:,} – {est_t2_hi:,}]
  T1 (WAF)       : {int(p_t1*universe):6,}
  DEAD           : {int(p_dead*universe):6,}""")

    # Suelo 2M assessment
    avg_count = 0
    counted = [r for r in results if r.vehicle_count_est and r.vehicle_count_est > 0]
    if counted:
        avg_count = sum(r.vehicle_count_est for r in counted) / len(counted)

    vehicles_from_t2 = int(est_t2 * avg_count) if avg_count > 0 else None
    print(f"""
VEREDICTO SUELO 2M:
  Dealers T2 estimados : {est_t2:,}
  Vehículos mediana por dealer (n={len(counted)}) : {avg_count:.0f}
  Proyección T2 vehículos : {"~{:,}".format(vehicles_from_t2) if vehicles_from_t2 else "sin datos suficientes"}
  Nota: vehiculos_T2_total incluye solo dominios con señal confirmada.
        Para 2M se necesita discovery name→web a ~{int(2_000_000/(avg_count if avg_count>0 else 50)):,} dealers
        (vs {universe:,} actuales con web, {est_t2:,} cosechables).""")

    # Top 10 examples with inventory
    print(f"\n10 EJEMPLOS REALES CON INVENTARIO:")
    examples = sorted(
        [r for r in results if r.has_inventory],
        key=lambda r: r.vehicle_count_est or 0,
        reverse=True,
    )[:10]
    for r in examples:
        sig = ", ".join(r.signals[:3])
        count_str = f"~{r.vehicle_count_est}" if r.vehicle_count_est else "?"
        waf_str = f" WAF={r.waf}" if r.waf else ""
        print(f"  [{r.country}] {r.domain:<45} | {r.tier} | {count_str:>6} veh | {sig}{waf_str}")

    print("=" * 68)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--concurrency", type=int, default=25)
    ap.add_argument("--sample", type=int, default=1000)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    conn = psycopg2.connect(DB_URL)

    print(f"[sample] fetching stratified sample (n={args.sample}) ...", flush=True)
    rows = fetch_sample(conn)
    print(f"[sample] got {len(rows)} rows: {dict((c, sum(1 for r in rows if r[2]==c)) for c in STRATA)}", flush=True)

    if args.dry_run:
        print("[dry-run] skipping actual HTTP probes")
        return 0

    print(f"\n[probe] launching async prober concurrency={args.concurrency} ...", flush=True)
    results = asyncio.run(run_probes(rows, args.concurrency, args.dry_run))

    # Persist to JSONL before DB write (recovery point if DB write fails)
    dump_path = Path(__file__).resolve().parent / "evidence" / "dumps" / "inventory_probe_results.jsonl"
    dump_path.parent.mkdir(parents=True, exist_ok=True)
    with dump_path.open("w", encoding="utf-8") as fh:
        for r in results:
            fh.write(json.dumps(asdict(r), ensure_ascii=False) + "\n")
    print(f"[dump] {len(results)} results -> {dump_path}", flush=True)

    print(f"\n[db] writing {len(results)} results back to discovery_candidates ...", flush=True)
    write_results(conn, results)
    conn.close()
    print("[db] done", flush=True)

    print_report(results, rows)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
