"""Dealer inventory probe at scale — classify pending with-web dealers into T1/T2/T3/DEAD.

Reuses the P2 probe logic (HEAD → homepage 30KB → /sitemap.xml 100KB → WAF + inventory
signals) but batches over EVERY ``sitemap_status='pending'`` dealer with a domain, writes
``inventory_tier`` + ``inventory_signals`` back, and is SSRF-guarded (net_guard) + RAM-aware.

Probe core (regexes, WAF detection, classification) is ported from the stealth front's
dealer_inventory_prober.py — verbatim where it was tuned.
"""
from __future__ import annotations

import asyncio
import json
import re
import ssl
import time
from dataclasses import dataclass, field
from typing import Optional

import aiohttp

from scrapers.common.net_guard import is_safe_public_url
from scrapers.dealer_scraping.cms_fingerprint import fingerprint_cms

# ── signals & patterns (ported verbatim) ────────────────────────────────────────
VEHICLE_URL_RE = re.compile(
    r'(?:/gebrauchtwagen|/occasionen?|/neuwagen?|/angebote?|/fahrzeuge?|/gebraucht|/auto(?:s)?/'
    r'|/voitures?|/occasions?|/vehicules?|/nos-vehicules?|/occasion-|/annonce'
    r'|/coches?|/vehiculos?|/segunda-mano|/ocasion'
    r'|/stock|/inventory|/used-cars?|/pre-owned|/vehicles?|/cars?/|/listings?'
    r'|/vo/|/vn/|/vd/)', re.I)
VEHICLE_JSONLD_TYPES = frozenset({'car', 'vehicle', 'motorizedvehicle', 'automobile',
                                  'product', 'offercatalog', 'itemlist'})
WAF_CF_HEADERS = frozenset({'cf-ray', 'cf-cache-status', 'cf-request-id'})
WAF_DD_HEADERS = frozenset({'x-datadome', 'x-datadome-cid'})
WAF_AK_HEADERS = frozenset({'x-akamai-transformed', 'x-akamai-request-id', 'akamai-grn'})
PARKED_RE = re.compile(
    r'domain.{0,20}(?:for sale|zu verkaufen|à vendre|te koop)|sedoparking|hugedomains'
    r'|namecheap\.com/domains|godaddy\.com/domain|dan\.com/domain|parking(?:page|service)'
    r'|this domain(?:\s+is)?\s+(?:available|parked)', re.I)
INVENTORY_COUNT_RE = re.compile(
    r'(\d+)\s*(?:fahrzeuge?|voitures?|coches?|vehicles?|cars?|véhicules?|occasions?'
    r'|gebrauchtwagen|annonces?|angebote?)', re.I)

SSL_CTX = ssl.create_default_context()
SSL_CTX.check_hostname = False
SSL_CTX.verify_mode = ssl.CERT_NONE

# HARD SCOPE GUARD — strictly the 6 target countries, never IT/AT or any out-of-scope
# country/domain. Discovery contaminated discovery_candidates with IT/AT; this clause keeps
# the probe + harvest + funnel inside scope. Invariant: zero out-of-scope rows touched.
IN_SCOPE_SQL = (
    "country IN ('ES','FR','DE','BE','NL','CH') "
    "AND domain NOT ILIKE '%.it' AND domain NOT ILIKE '%.at'"
)


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
    # CMS-multiplier signal (additive): platform family fingerprinted from the SAME
    # homepage body the probe already fetched (see detector.py for the pattern).
    # Falsy defaults ("" / []) mean "no homepage HTML reached the fingerprint".
    cms: str = ""                                    # family key ("" = none fired)
    cms_confidence: str = ""                         # 'high' | 'medium' | 'unknown'
    cms_signals: list = field(default_factory=list)  # concrete markers that fired


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
    if "datadome" in text or "ddcaptcha" in text:
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
            text_raw, re.DOTALL | re.I)[:5]:
        try:
            data = json.loads(jld_raw)
            graphs = data.get("@graph", [data]) if isinstance(data, dict) else [data]
            for node in (graphs if isinstance(graphs, list) else [graphs]):
                t = node.get("@type", "") if isinstance(node, dict) else ""
                types = [t] if isinstance(t, str) else (t if isinstance(t, list) else [])
                if any(str(x).lower() in VEHICLE_JSONLD_TYPES for x in types):
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
                timeout: int = 15) -> ProbeResult:
    t0 = time.monotonic()
    result = ProbeResult(domain=domain, country=country)
    signals: list[str] = []
    base_https = f"https://{domain}"

    # SSRF guard: reject domains resolving to private/loopback/link-local before any fetch.
    try:
        safe = await asyncio.to_thread(is_safe_public_url, base_https, resolve=True)
    except Exception:
        safe = False
    if not safe:
        result.error = "unsafe_or_unresolvable"
        result.probe_ms = int((time.monotonic() - t0) * 1000)
        return result

    try:
        for base in (base_https, f"http://{domain}"):
            try:
                head = await session.head(base, timeout=aiohttp.ClientTimeout(total=min(timeout, 10), sock_connect=5),
                                          ssl=SSL_CTX, allow_redirects=True)
                result.alive = True
                result.http_status = head.status
                result.final_url = str(head.url)
                result.waf = _detect_waf_headers(dict(head.headers))
                break
            except Exception:
                continue
        if result.alive:
            base = base_https if (result.final_url or "").startswith("https") else f"http://{domain}"
            try:
                get = await session.get(base, timeout=aiohttp.ClientTimeout(total=timeout + 3, sock_connect=5),
                                        ssl=SSL_CTX, allow_redirects=True,
                                        headers={"Accept": "text/html",
                                                 "Accept-Language": "de,fr,es,nl,en;q=0.5"})
                text = (await _read_limited(get, 30_720)).decode("utf-8", errors="replace")
                _parse_homepage(text, signals, result)
                # CMS-multiplier signal (additive, pure, zero extra I/O): fingerprint
                # the platform family from the 30KB homepage body + response headers
                # already in hand. 'unknown' maps to "" so cms stays falsy unless a
                # real family fired. Tier classification below is NOT influenced.
                cms_verdict = fingerprint_cms(text, headers=dict(get.headers))
                result.cms = cms_verdict.cms if cms_verdict.cms != "unknown" else ""
                result.cms_confidence = cms_verdict.confidence
                result.cms_signals = list(cms_verdict.signals)
            except Exception:
                pass
            if not result.parked:
                try:
                    sm = await session.get(f"{base}/sitemap.xml",
                                           timeout=aiohttp.ClientTimeout(total=min(timeout, 10), sock_connect=5),
                                           ssl=SSL_CTX, allow_redirects=True)
                    if sm.status == 200:
                        sm_text = (await _read_limited(sm, 102_400)).decode("utf-8", errors="replace")
                        _parse_sitemap(sm_text, signals, result)
                except Exception:
                    pass
    except Exception as exc:  # noqa: BLE001
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


# ── DB layer (asyncpg, batched over pending) ────────────────────────────────────
async def claim_pending_batch(pg, size: int, country: str | None = None) -> list[dict]:
    rows = await pg.fetch(
        "SELECT id, domain, country FROM discovery_candidates "
        "WHERE domain IS NOT NULL AND domain<>'' AND sitemap_status='pending' "
        f"AND {IN_SCOPE_SQL} "
        "AND ($2::text IS NULL OR country=$2) "
        "ORDER BY country, id LIMIT $1", size, country)
    return [dict(r) for r in rows]


def _sitemap_status(r: ProbeResult) -> str:
    if r.tier in ("T1", "T2"):
        return "found"
    if r.error:
        return "error"
    return "none"


async def write_results(pg, results: list[ProbeResult]) -> None:
    payload = [
        (r.tier, json.dumps({"signals": r.signals, "waf": r.waf, "http_status": r.http_status,
                             "vehicle_count_est": r.vehicle_count_est, "parked": r.parked,
                             "final_url": r.final_url, "probe_ms": r.probe_ms, "error": r.error,
                             "cms": r.cms, "cms_confidence": r.cms_confidence,
                             "cms_signals": r.cms_signals}),
         _sitemap_status(r), r.domain, r.country)
        for r in results]
    async with pg.acquire() as conn:
        await conn.executemany(
            "UPDATE discovery_candidates SET inventory_tier=$1, inventory_probed_at=NOW(), "
            "inventory_signals=$2::jsonb, sitemap_status=$3, sitemap_probed_at=NOW() "
            "WHERE domain=$4 AND country=$5", payload)


async def run_probes(session, rows: list[dict], concurrency: int, timeout: int) -> list[ProbeResult]:
    sem = asyncio.Semaphore(concurrency)

    async def one(row):
        async with sem:
            return await probe(session, row["domain"], row["country"], timeout=timeout)

    return list(await asyncio.gather(*(one(r) for r in rows)))
