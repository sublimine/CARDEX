"""
WAF classifier — detecta qué protección tiene un dominio nuevo.

Usado para dominios que no están en DOMAIN_TIER_REGISTRY (dealers individuales).
La clasificación se persiste en engine.db domain_tier_state y no se repite
hasta que verified_at envejezca (is_stale) o forced=True.

Protocolo (SCRAPING_ENGINE.md §D1):
  1. GET con curl_cffi (JA3 Chrome) → analizar status + headers + body:
     x-datadome / datadome cookie  → DataDome → T3 (behavioral)
     _px* cookie / x-px header      → PerimeterX → T3 (behavioral)
     ak_bmsc / _abck cookie         → Akamai Bot Manager → T2
     cf-ray header / CF challenge   → Cloudflare → T2 si challenge, T1 si pasivo
  2. Asignar tier conservador (mejor sobre-proteger que sub-proteger).
  3. Registrar resultado en domain_tier_state (persist).

La decisión pura vive en classify_signals(status, headers, body) — sin red, sin
estado — para que sea testeable de forma aislada. classify() es solo la cáscara
de I/O que ejecuta el probe y delega la decisión.
"""
from __future__ import annotations

import logging
import sqlite3
import time
from collections.abc import Mapping

from scrapers.common.net_guard import is_safe_public_url
from scrapers.engine.router.domain_map import PortalSpec, Tier, WAF

log = logging.getLogger("router.classifier")

# Probe configuration.
_IMPERSONATE = "chrome"   # JA3 alias = latest Chrome, matches engine.antidetect.tls
_PROBE_TIMEOUT_S = 20
_BODY_SCAN_LIMIT = 65_536  # only the head of the body carries challenge markers
_STALE_DEFAULT_DAYS = 7

# Verified WAF signatures. Header keys/values and set-cookie names are matched
# case-insensitively against the joined header blob; body markers against the
# lowercased response head. Sources: discovery/sources/as24_curl_cffi.py,
# common/autoscout24.py CF markers, INTEL.md §4.
_DATADOME_MARKERS = (
    "x-datadome",
    "x-dd-b",
    "datadome=",
    "geo.captcha-delivery.com",
)
_PERIMETERX_MARKERS = (
    "x-px",
    "_pxhd",
    "_pxvid",
    "_px3",
    "_px=",
    "px-captcha",
    "perimeterx",
)
_AKAMAI_MARKERS = (
    "ak_bmsc",
    "bm_sz",
    "_abck",
    "x-akamai",
)
_CF_HEADER_MARKERS = (
    "cf-ray",
    "__cf_bm",
    "cf_clearance",
    "cloudflare",
)
_CF_CHALLENGE_MARKERS = (
    "just a moment",
    "__cf_chl_",
    "cf-browser-verification",
    "checking your browser",
    "jschl-answer",
    "attention required! | cloudflare",
)
_BLOCK_STATUSES = frozenset({403, 429, 503})


def classify_signals(
    status: int, headers: Mapping[str, str], body: str
) -> tuple[WAF, Tier]:
    """
    Pure WAF/tier decision from one probe response. No I/O, no state.

    Ordered strongest-protection-first so a behavioral WAF (DataDome/PerimeterX)
    always wins over a co-present passive layer. On an unidentified block status
    we return the conservative T2 rather than assume the cheap path is enough.
    """
    header_blob = " ".join(
        f"{str(k).lower()}: {str(v).lower()}" for k, v in headers.items()
    )
    body_head = (body or "").lower()[:_BODY_SCAN_LIMIT]

    def _seen(markers: tuple[str, ...]) -> bool:
        return any(m in header_blob or m in body_head for m in markers)

    if _seen(_DATADOME_MARKERS):
        return WAF.DATADOME, Tier.T3
    if _seen(_PERIMETERX_MARKERS):
        return WAF.PERIMETER_X, Tier.T3
    if _seen(_AKAMAI_MARKERS):
        return WAF.AKAMAI_V3, Tier.T2

    cf_present = any(m in header_blob for m in _CF_HEADER_MARKERS)
    cf_challenge = any(m in body_head for m in _CF_CHALLENGE_MARKERS)
    if cf_present or cf_challenge:
        if cf_challenge or status in _BLOCK_STATUSES:
            return WAF.CF_PRO, Tier.T2
        return WAF.CF_FREE, Tier.T1

    if status in _BLOCK_STATUSES:
        return WAF.UNKNOWN, Tier.T2  # blocked but no fingerprint → over-protect
    return WAF.NONE, Tier.T1


async def classify(domain: str, proxy_url: str | None = None) -> PortalSpec:
    """
    Classify a new domain. Returns PortalSpec with detected tier and WAF.

    Runs a single curl_cffi GET (~2-5s) and delegates the verdict to
    classify_signals. A probe that cannot complete yields the conservative
    (UNKNOWN, T2) spec — never an optimistic T1 on uncertainty.
    """
    # Lazy import keeps the pure decision logic (and persistence helpers)
    # importable without the native curl_cffi dependency loaded.
    from curl_cffi.requests import AsyncSession

    host = domain.strip().rstrip("/")
    url = f"https://{host}/"
    # SSRF guard: `domain` is external (newly discovered dealer host) and the probe
    # may run WITHOUT a proxy (direct egress from the scraper host). Refuse internal
    # / loopback / link-local targets — most importantly the cloud metadata service.
    # resolve=True also blocks a public name that resolves to a private IP.
    if not is_safe_public_url(url, resolve=True):
        log.warning("classify refused unsafe target %s (SSRF guard)", host)
        return PortalSpec(domain_pattern=host, tier=Tier.T2, waf=WAF.UNKNOWN, notes="ssrf-blocked")
    proxies = {"https": proxy_url, "http": proxy_url} if proxy_url else None
    try:
        async with AsyncSession() as sess:
            r = await sess.get(
                url,
                impersonate=_IMPERSONATE,
                timeout=_PROBE_TIMEOUT_S,
                proxies=proxies,
                allow_redirects=True,
            )
        waf, tier = classify_signals(r.status_code, dict(r.headers), r.text)
        notes = f"auto-classified status={r.status_code}"
    except Exception as exc:  # network/TLS failure — degrade conservatively
        log.warning("classify probe failed for %s: %s", host, exc)
        waf, tier = WAF.UNKNOWN, Tier.T2
        notes = "auto-classified probe-failed"
    return PortalSpec(domain_pattern=host, tier=tier, waf=waf, notes=notes)


def persist(conn: sqlite3.Connection, spec: PortalSpec) -> None:
    """
    Save classification to domain_tier_state. Sets verified_at and seeds
    effective_tier with the classified baseline tier (upsert by domain+tier).
    """
    now = int(time.time())
    tier = spec.tier.value
    conn.execute(
        "INSERT INTO domain_tier_state (domain, tier, waf, effective_tier, verified_at) "
        "VALUES (?, ?, ?, ?, ?) "
        "ON CONFLICT(domain, tier) DO UPDATE SET "
        "waf=excluded.waf, "
        "effective_tier=excluded.effective_tier, "
        "verified_at=excluded.verified_at",
        (spec.domain_pattern, tier, spec.waf.value, tier, now),
    )


def is_stale(
    conn: sqlite3.Connection, domain: str, max_age_days: int = _STALE_DEFAULT_DAYS
) -> bool:
    """
    True if domain has no classification yet, or the freshest verified_at is
    older than max_age_days. Uses MAX(verified_at) so circuit-breaker rows
    written without verified_at never mask a real classification.
    """
    row = conn.execute(
        "SELECT MAX(verified_at) AS v FROM domain_tier_state WHERE domain = ?",
        (domain,),
    ).fetchone()
    if row is None or row["v"] is None:
        return True
    return (int(time.time()) - int(row["v"])) > max_age_days * 86_400
