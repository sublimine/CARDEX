#!/usr/bin/env python3
"""Re-probe ES/FR/NL domains that timed out at 6s in the initial inventory probe.

Fetches the 292 DEAD domains from those countries (all were TimeoutError),
re-probes with timeout=15s + 1 retry, and updates discovery_candidates in place.

Usage:
    python reprobe_es_fr_nl.py [--concurrency 15]
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

# ── Config ────────────────────────────────────────────────────────────────────

DB_URL = "postgresql://cardex:cardex_dev_only@127.0.0.1:5432/cardex"
TARGET_COUNTRIES = ("ES", "FR", "NL")
TIMEOUT = 15       # seconds — wider window for geographically distant sites
RETRY_ON_TIMEOUT = True

# ── Patterns (same as main prober) ───────────────────────────────────────────

VEHICLE_URL_RE = re.compile(
    r'(?:'
    r'/gebrauchtwagen|/occasionen?|/neuwagen?|/angebote?|/fahrzeuge?|/gebraucht'
    r'|/auto(?:s)?/'
    r'|/voitures?|/occasions?|/vehicules?|/nos-vehicules?|/occasion-'
    r'|/annonce'
    r'|/coches?|/vehiculos?|/segunda-mano|/ocasion'
    r'|/stock|/inventory|/used-cars?|/pre-owned|/vehicles?'
    r'|/cars?/|/listings?'
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
    r'domain.{0,20}(?:for sale|zu verkaufen|a vendre|te koop)'
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
    r'(\d+)\s*(?:fahrzeuge?|voitures?|coches?|vehicles?|cars?|vehicules?'
    r'|occasions?|gebrauchtwagen|annonces?|angebote?)',
    re.I,
)

# ── SSL ───────────────────────────────────────────────────────────────────────

SSL_CTX = ssl.create_default_context()
SSL_CTX.check_hostname = False
SSL_CTX.verify_mode = ssl.CERT_NONE

# ── Data class ────────────────────────────────────────────────────────────────

@dataclass
class ProbeResult:
    domain: str
    country: str
    alive: bool = False
    final_url: Optional[str] = None
    http_status: Optional[int] = None
    waf: Optional[str] = None
    parked: bool = False
    has_inventory: bool = False
    signals: list = field(default_factory=list)
    vehicle_count_est: Optional[int] = None
    tier: str = "DEAD"
    error: Optional[str] = None
    probe_ms: int = 0

# ── Probe helpers ─────────────────────────────────────────────────────────────

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
    if not result.waf:
        result.waf = _detect_waf_body(text)
    if VEHICLE_URL_RE.search(text):
        signals.append("url_pattern")
    m = DMS_RE.search(text_raw)
    if m:
        signals.append(f"dms:{m.group()[:30]}")
    cm = INVENTORY_COUNT_RE.search(text_raw)
    if cm:
        try:
            n = int(cm.group(1).replace(".", "").replace(",", ""))
            if 1 <= n <= 50000:
                result.vehicle_count_est = n
                signals.append(f"count_text:{n}")
        except ValueError:
            pass
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


async def _probe_once(session: aiohttp.ClientSession, domain: str, country: str,
                      timeout: int) -> ProbeResult:
    t0 = time.monotonic()
    result = ProbeResult(domain=domain, country=country)
    signals: list[str] = []
    base_https = f"https://{domain}"
    base_http = f"http://{domain}"

    try:
        try:
            head = await session.head(
                base_https, timeout=aiohttp.ClientTimeout(total=timeout),
                ssl=SSL_CTX, allow_redirects=True,
            )
            result.alive = True
            result.http_status = head.status
            result.final_url = str(head.url)
            result.waf = _detect_waf_headers(dict(head.headers))
        except Exception:
            head = await session.head(
                base_http, timeout=aiohttp.ClientTimeout(total=timeout),
                ssl=SSL_CTX, allow_redirects=True,
            )
            result.alive = True
            result.http_status = head.status
            result.final_url = str(head.url)
            result.waf = _detect_waf_headers(dict(head.headers))

        base = base_https if (result.final_url or "").startswith("https") else base_http
        try:
            get = await session.get(
                base, timeout=aiohttp.ClientTimeout(total=timeout + 3),
                ssl=SSL_CTX, allow_redirects=True,
                headers={"Accept": "text/html",
                         "Accept-Language": "fr,es,nl,de,en;q=0.5"},
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

        try:
            sm = await session.get(
                f"{base}/sitemap.xml",
                timeout=aiohttp.ClientTimeout(total=timeout),
                ssl=SSL_CTX, allow_redirects=True,
            )
            if sm.status == 200:
                sm_body = await _read_limited(sm, 102_400)
                _parse_sitemap(sm_body.decode("utf-8", errors="replace"), signals, result)
        except Exception:
            pass

    except (aiohttp.ClientConnectorError, aiohttp.ServerConnectionError,
            aiohttp.ClientOSError, asyncio.TimeoutError, Exception) as exc:
        result.error = type(exc).__name__

    result.signals = signals
    result.has_inventory = bool(signals)
    if not result.alive or result.parked:
        result.tier = "DEAD"
    elif result.has_inventory:
        result.tier = "T1" if result.waf else "T2"
    else:
        result.tier = "T3"

    result.probe_ms = int((time.monotonic() - t0) * 1000)
    return result


async def probe(session: aiohttp.ClientSession, domain: str, country: str,
                timeout: int = TIMEOUT) -> ProbeResult:
    r = await _probe_once(session, domain, country, timeout)
    if RETRY_ON_TIMEOUT and r.error == "TimeoutError":
        r = await _probe_once(session, domain, country, timeout)
    return r

# ── DB helpers ────────────────────────────────────────────────────────────────

def fetch_dead_es_fr_nl(conn) -> list[tuple[int, str, str]]:
    with conn.cursor() as cur:
        cur.execute("""
            SELECT id, domain, country
            FROM discovery_candidates
            WHERE inventory_tier = 'DEAD'
              AND inventory_probed_at IS NOT NULL
              AND country = ANY(%s)
            ORDER BY country, domain
        """, (list(TARGET_COUNTRIES),))
        return cur.fetchall()


def write_results(conn, results: list[ProbeResult]) -> None:
    def _sitemap_status(r: ProbeResult) -> str:
        if r.tier in ("T1", "T2"):
            return "found"
        if r.error:
            return "error"
        return "none"

    with conn.cursor() as cur:
        for r in results:
            signals_json = json.dumps({
                "waf": r.waf,
                "error": r.error,
                "parked": r.parked,
                "signals": r.signals,
                "probe_ms": r.probe_ms,
                "final_url": r.final_url,
                "http_status": r.http_status,
                "sitemap_urls": next(
                    (int(s.split(":")[1]) for s in r.signals if s.startswith("sitemap_urls:")),
                    None,
                ),
                "inventory_urls": [s for s in r.signals if "url" in s.lower()],
                "jsonld_types": [s for s in r.signals if "jsonld" in s.lower()],
                "vehicle_count_est": r.vehicle_count_est,
            })
            cur.execute("""
                UPDATE discovery_candidates
                SET inventory_tier       = %s,
                    inventory_probed_at  = NOW(),
                    inventory_signals    = %s::jsonb,
                    sitemap_status       = %s,
                    sitemap_probed_at    = NOW()
                WHERE domain = %s AND country = %s
            """, (r.tier, signals_json, _sitemap_status(r), r.domain, r.country))
    conn.commit()

# ── Async runner ──────────────────────────────────────────────────────────────

async def run_probes(rows: list[tuple], concurrency: int) -> list[ProbeResult]:
    sem = asyncio.Semaphore(concurrency)
    results: list[ProbeResult] = []
    total = len(rows)
    done = 0
    t_start = time.monotonic()

    connector = aiohttp.TCPConnector(limit=concurrency, ssl=SSL_CTX)
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        )
    }
    async with aiohttp.ClientSession(connector=connector, headers=headers) as session:

        async def _run(row):
            nonlocal done
            _, domain, country = row
            async with sem:
                r = await probe(session, domain, country)
            results.append(r)
            done += 1
            if done % 25 == 0 or done == total:
                elapsed = time.monotonic() - t_start
                rps = done / elapsed if elapsed > 0 else 0
                alive = sum(1 for x in results if x.tier != "DEAD")
                inv = sum(1 for x in results if x.has_inventory)
                print(f"  [{done}/{total}] alive={alive} inv={inv} "
                      f"elapsed={elapsed:.0f}s rps={rps:.1f}", flush=True)

        await asyncio.gather(*[_run(row) for row in rows])

    return results

# ── Report ────────────────────────────────────────────────────────────────────

def print_report(results: list[ProbeResult]) -> None:
    from collections import defaultdict

    by_country: dict[str, list[ProbeResult]] = defaultdict(list)
    for r in results:
        by_country[r.country].append(r)

    print("\n" + "=" * 68)
    print("RE-PROBE ES/FR/NL — timeout=15s + retry — RESULTADOS")
    print("=" * 68)

    total_t2 = 0
    header = f"{'Pais':<6} {'n':>4} {'Vivos':>6} {'T1':>4} {'T2':>4} {'T3':>4} {'DEAD':>6} {'%vivos':>7} {'%inv':>6}"
    print(header)
    print("-" * 68)
    for country in sorted(by_country):
        rs = by_country[country]
        n = len(rs)
        alive = sum(1 for r in rs if r.tier != "DEAD")
        t1 = sum(1 for r in rs if r.tier == "T1")
        t2 = sum(1 for r in rs if r.tier == "T2")
        t3 = sum(1 for r in rs if r.tier == "T3")
        dead = sum(1 for r in rs if r.tier == "DEAD")
        pct_alive = 100 * alive / n if n else 0
        pct_inv = 100 * (t1 + t2) / n if n else 0
        print(f"{country:<6} {n:>4} {alive:>6} {t1:>4} {t2:>4} {t3:>4} {dead:>6} {pct_alive:>6.1f}% {pct_inv:>5.1f}%")
        total_t2 += t2

    print("-" * 68)
    all_rs = results
    n = len(all_rs)
    alive = sum(1 for r in all_rs if r.tier != "DEAD")
    t1 = sum(1 for r in all_rs if r.tier == "T1")
    t2 = sum(1 for r in all_rs if r.tier == "T2")
    t3 = sum(1 for r in all_rs if r.tier == "T3")
    dead = sum(1 for r in all_rs if r.tier == "DEAD")
    print(f"{'TOTAL':<6} {n:>4} {alive:>6} {t1:>4} {t2:>4} {t3:>4} {dead:>6} "
          f"{100*alive/n:>6.1f}% {100*(t1+t2)/n:>5.1f}%")

    # T1/T2 examples
    examples = [r for r in results if r.has_inventory]
    if examples:
        print(f"\nEJEMPLOS INVENTARIO ({len(examples)} total):")
        for r in sorted(examples, key=lambda x: x.vehicle_count_est or 0, reverse=True)[:10]:
            sig = ", ".join(r.signals[:3])
            cnt = f"~{r.vehicle_count_est}" if r.vehicle_count_est else "?"
            waf = f" WAF={r.waf}" if r.waf else ""
            print(f"  [{r.country}] {r.domain:<45} {r.tier} {cnt:>6} veh | {sig}{waf}")

    print("=" * 68)


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--concurrency", type=int, default=15)
    ap.add_argument("--timeout", type=int, default=TIMEOUT)
    ap.add_argument("--no-retry", action="store_true")
    args = ap.parse_args()

    effective_timeout = args.timeout
    effective_retry = not args.no_retry

    conn = psycopg2.connect(DB_URL)
    rows = fetch_dead_es_fr_nl(conn)
    retry_label = "no-retry" if args.no_retry else "retry"
    print(f"[fetch] {len(rows)} DEAD ES/FR/NL domains to re-probe "
          f"(timeout={effective_timeout}s {retry_label})", flush=True)
    by_c = {}
    for _, _, c in rows:
        by_c[c] = by_c.get(c, 0) + 1
    print(f"[fetch] breakdown: {by_c}", flush=True)

    print(f"\n[probe] launching concurrency={args.concurrency} ...", flush=True)
    results = asyncio.run(run_probes(rows, args.concurrency))

    # Dump recovery JSONL
    dump_path = Path(__file__).resolve().parent / "evidence" / "dumps" / "reprobe_es_fr_nl.jsonl"
    dump_path.parent.mkdir(parents=True, exist_ok=True)
    with dump_path.open("w", encoding="utf-8") as fh:
        for r in results:
            fh.write(json.dumps(asdict(r), ensure_ascii=False) + "\n")
    print(f"[dump] {len(results)} results -> {dump_path}", flush=True)

    print(f"\n[db] updating {len(results)} rows in discovery_candidates ...", flush=True)
    write_results(conn, results)
    conn.close()
    print("[db] done", flush=True)

    print_report(results)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
