"""
FR discovery — PagesJaunes.fr dealer directory (France's yellow pages).

PagesJaunes lists «concessionnaires automobiles» searchable by département (96 total).
Each listing page returns up to 20 dealers.  The dealer name and partial address are
in static HTML; the website URL (when present, ~12% of listings) is base64-encoded
in a ``data-pjlb`` attribute on a ``bi-website`` anchor.

Access pattern:
  - URL: https://www.pagesjaunes.fr/annuaire/chercherlespros
          ?quoiqui=concessionnaire+automobile&ou=<DEPT>&page=N
  - Anti-bot: Cloudflare present but accessible with curl (chunked response).
              Python stdlib urll returns 403 → use subprocess curl to file.
  - Response is chunked: fetch to a temp file via curl, then parse.

Strategy:
  Iterate 96 French département codes (01–95 + 2A + 2B) × pages.  For each dealer:
    - Extract codeEtablissement from ``id="bi-<CODE>"`` → registry_id = "pj-<CODE>"
    - Extract name from ``<h3>`` inside ``bi-denomination``
    - Extract address from ``<div class="bi-address">`` text node
    - Decode website URL from ``data-pjlb`` on any ``bi-website`` anchor (base64)
    - Upsert to discovery_candidates

Environment variables:
  DATABASE_URL          PostgreSQL DSN (default: dev)
  PJ_THROTTLE           Seconds between page fetches (default: 1.0)
  PJ_MAX_DEPT           Stop after N départements — 0 = all 96 (default: 0)
  PJ_MAX_PAGES_PER_DEPT Max pages per département — 0 = all (default: 0)

Usage:
    python -m scrapers.discovery.sources.fr_pagesjaunes
    PJ_MAX_DEPT=3 PJ_MAX_PAGES_PER_DEPT=2 python -m scrapers.discovery.sources.fr_pagesjaunes
"""
from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
import re
import subprocess
import tempfile
import time
import urllib.parse

import asyncpg

log = logging.getLogger("fr_pagesjaunes")
logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s [fr_pagesjaunes] %(message)s",
)

_DSN = os.environ.get(
    "DATABASE_URL", "postgresql://cardex:cardex_dev_only@localhost:5432/cardex"
)
_BASE = "https://www.pagesjaunes.fr/annuaire/chercherlespros"
_QUERY = "concessionnaire+automobile"
_SOURCE = "pagesjaunes"
_SOURCE_LAYER = 2
_COUNTRY = "FR"

_THROTTLE = float(os.environ.get("PJ_THROTTLE", "3.0"))
_MAX_DEPT = int(os.environ.get("PJ_MAX_DEPT", "0"))
_MAX_PAGES_PER_DEPT = int(os.environ.get("PJ_MAX_PAGES_PER_DEPT", "0"))
# Wait on Cloudflare challenge / 403 before retrying next dept
_CF_BACKOFF = float(os.environ.get("PJ_CF_BACKOFF", "120.0"))

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)

# All 96 French département codes (01–95 + 2A + 2B + DOM-TOM excluded for simplicity)
_DEPARTMENTS = (
    [f"{i:02d}" for i in range(1, 20)]
    + ["2A", "2B"]
    + [f"{i:02d}" for i in range(21, 96)]
)
assert len(_DEPARTMENTS) == 96, f"Expected 96 depts, got {len(_DEPARTMENTS)}"


# ---------------------------------------------------------------------------
# Pure parsing helpers (testable without network)
# ---------------------------------------------------------------------------

def _decode_b64(b64: str) -> str | None:
    """Decode a PagesJaunes base64 URL (variable padding). Returns decoded str or None."""
    if not b64:
        return None
    padded = b64 + "==" * ((4 - len(b64) % 4) % 4)
    try:
        return base64.b64decode(padded).decode("utf-8", errors="replace").strip()
    except Exception:
        return None


def _normalize_url(u: str | None) -> str | None:
    if not u:
        return None
    u = u.strip()
    if not u:
        return None
    if not u.startswith(("http://", "https://")):
        u = "https://" + u
    # Filter self-references or non-dealer URLs
    for bad in ("pagesjaunes.fr", "solocal.com", "javascript:"):
        if bad in u:
            return None
    return u.rstrip("/")


def _domain(url: str | None) -> str | None:
    if not url:
        return None
    try:
        netloc = urllib.parse.urlparse(url).netloc.lower()
    except ValueError:
        return None
    if netloc.startswith("www."):
        netloc = netloc[4:]
    return netloc or None


def _clean_text(raw: str) -> str | None:
    """Strip HTML tags and normalise whitespace from a raw HTML fragment."""
    text = re.sub(r"<[^>]+>", " ", raw)
    text = re.sub(r"&[a-z]+;|&#\d+;", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text or None


def parse_listing_page(html: str) -> list[dict]:
    """Parse one PagesJaunes listing HTML page into candidate dicts.

    Each ``<li id="bi-<CODE>">`` block contains one dealer.

    Returns list of candidate dicts.  Website is present only for ~12% of
    dealers (those that have a ``bi-website`` link with a non-PJ base64 URL).
    """
    # Find all bi block starts
    bi_starts = [m.start() for m in re.finditer(r'<li\s+id="bi-(\d+)"', html)]
    if not bi_starts:
        return []

    candidates: list[dict] = []
    for idx, start in enumerate(bi_starts):
        end = bi_starts[idx + 1] if idx + 1 < len(bi_starts) else start + 25000
        block = html[start:min(end, start + 25000)]

        cand = _parse_bi_block(block)
        if cand is not None:
            candidates.append(cand)
    return candidates


def _parse_bi_block(block: str) -> dict | None:
    """Parse one ``<li id="bi-CODE">`` block into a candidate dict."""
    # codeEtablissement from id="bi-CODE"
    id_m = re.search(r'id="bi-(\d+)"', block)
    if not id_m:
        return None
    code_etab = id_m.group(1)
    registry_id = f"pj-{code_etab}"

    # Name: <h3 ...>NAME</h3> inside bi-denomination
    name_m = re.search(r'class="bi-denomination[^"]*"[^>]*>.*?<h3[^>]*>(.*?)</h3>', block, re.DOTALL)
    if not name_m:
        # Fallback: any h3 in the block
        name_m = re.search(r'<h3[^>]*>([^<]+)</h3>', block)
    name = _clean_text(name_m.group(1)) if name_m else None

    # Address: text node directly inside bi-address div (before any child tag)
    addr_m = re.search(r'<div[^>]*class="bi-address[^"]*"[^>]*>(.*?)</div>', block, re.DOTALL)
    address = None
    if addr_m:
        addr_raw = addr_m.group(1)
        # The address text is the first text node — strip inner tags
        address = _clean_text(addr_raw)
        # Remove "Voir le plan" and similar map CTA text
        if address:
            address = re.sub(r"Voir le plan.*$", "", address, flags=re.IGNORECASE).strip()
            address = re.sub(r"\s+", " ", address).strip() or None

    # Website: look for bi-website anchor with data-pjlb containing a base64 URL
    # Pattern: class="... bi-website ..." data-pjlb='{"url":"<b64>","ucod":"b64u8"}'
    website = None
    domain = None
    pjlb_matches = re.findall(r"data-pjlb='(\{[^']+\})'", block)
    for raw_json in pjlb_matches:
        try:
            obj = json.loads(raw_json)
        except json.JSONDecodeError:
            continue
        b64 = obj.get("url", "")
        decoded = _decode_b64(b64)
        if decoded and decoded.startswith("http"):
            url_candidate = _normalize_url(decoded)
            if url_candidate:
                website = url_candidate
                domain = _domain(website)
                break

    # Also check for a direct href (rare but present for some propay blocks)
    if not website:
        ext_hrefs = re.findall(
            r'href="(https?://(?!(?:www\.pagesjaunes|www\.solocal|www\.google)[./])[^"]+)"',
            block,
        )
        for href in ext_hrefs:
            url_candidate = _normalize_url(href)
            if url_candidate:
                website = url_candidate
                domain = _domain(website)
                break

    return {
        "domain": domain,
        "country": _COUNTRY,
        "source_layer": _SOURCE_LAYER,
        "source": _SOURCE,
        "url": website,
        "name": name,
        "address": address,
        "city": None,       # city is part of address string; not split separately
        "postcode": None,
        "phone": None,      # phone is loaded via AJAX on PJ — not in HTML
        "email": None,
        "lat": None,
        "lng": None,
        "registry_id": registry_id,
        "external_refs": {
            "pj_detail": f"https://www.pagesjaunes.fr/pros/detail?code_etablissement={code_etab}"
        },
    }


def parse_total_results(html: str) -> int:
    """Extract total result count from PJ listing page."""
    m = re.search(r'id="SEL-nbresultat"[^>]*>(\d+)<', html)
    if m:
        try:
            return int(m.group(1))
        except ValueError:
            pass
    return 0


def pages_for_count(total: int, per_page: int = 20) -> int:
    """Compute number of pages needed for total results."""
    if total <= 0:
        return 1
    return max(1, (total + per_page - 1) // per_page)


# ---------------------------------------------------------------------------
# Network layer — must use curl (Python urllib returns 403 on PJ)
# ---------------------------------------------------------------------------

def _fetch_via_curl(url: str) -> str | None:
    """Fetch URL via subprocess curl to a temp file, return content or None.

    Returns None on error, Cloudflare challenge, or empty response.
    The caller is responsible for detecting 0-result pages and backing off.
    """
    with tempfile.NamedTemporaryFile(suffix=".html", delete=False) as tmp:
        tmp_path = tmp.name

    cmd = [
        "curl", "-s", "-L",
        "-A", _UA,
        "-H", "Accept: text/html,application/xhtml+xml,*/*;q=0.9",
        "-H", "Accept-Language: fr-FR,fr;q=0.9",
        "-H", "Accept-Encoding: identity",
        "-H", "Referer: https://www.pagesjaunes.fr/",
        "--max-time", "35",
        "-o", tmp_path,
        url,
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, timeout=45)
        if result.returncode != 0:
            log.debug("curl failed (rc=%d) for %s", result.returncode, url)
            return None
        with open(tmp_path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
        if not content.strip():
            return None
        # Detect Cloudflare JS challenge (very short page with no bi blocks)
        if len(content) < 15000 and 'id="SEL-nbresultat"' not in content and '<li id="bi-' not in content:
            log.debug("Likely Cloudflare challenge for %s (size=%d)", url, len(content))
            return None
        return content
    except subprocess.TimeoutExpired:
        log.debug("curl timeout for %s", url)
        return None
    except Exception as exc:
        log.debug("curl error for %s: %s", url, exc)
        return None
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


# ---------------------------------------------------------------------------
# DB upsert (same pattern as ch_agvs / de_gelbeseiten)
# ---------------------------------------------------------------------------

_COLS = (
    "domain, country, source_layer, source, url, name, address, city, postcode, "
    "phone, email, lat, lng, registry_id, external_refs"
)
_VALS = "$1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15::jsonb"

_UPSERT_DOMAIN = f"""
INSERT INTO discovery_candidates ({_COLS}) VALUES ({_VALS})
ON CONFLICT (domain, country) WHERE domain IS NOT NULL
DO UPDATE SET last_seen = NOW()
WHERE discovery_candidates.last_seen < NOW() - INTERVAL '1 hour'
"""
_UPSERT_IDENTITY = f"""
INSERT INTO discovery_candidates ({_COLS}) VALUES ({_VALS})
ON CONFLICT (source, registry_id, country) WHERE domain IS NULL AND registry_id IS NOT NULL
DO UPDATE SET last_seen = NOW()
WHERE discovery_candidates.last_seen < NOW() - INTERVAL '1 hour'
"""


async def _upsert(pool: asyncpg.Pool, c: dict) -> bool:
    domain = c.get("domain")
    registry_id = c.get("registry_id")
    if not domain and not registry_id:
        return False
    params = (
        domain, c["country"], c["source_layer"], c["source"],
        c.get("url"), c.get("name"), c.get("address"), c.get("city"),
        c.get("postcode"), c.get("phone"), c.get("email"),
        c.get("lat"), c.get("lng"),
        registry_id,
        json.dumps(c.get("external_refs") or {}),
    )
    sql = _UPSERT_DOMAIN if domain else _UPSERT_IDENTITY
    try:
        await pool.execute(sql, *params)
        return True
    except Exception as exc:
        log.warning("upsert failed name=%r: %s", (c.get("name") or "")[:50], exc)
        return False


# ---------------------------------------------------------------------------
# Main run
# ---------------------------------------------------------------------------

async def run() -> dict:
    """Iterate all départements × pages and upsert dealers to discovery_candidates."""
    pool = await asyncpg.create_pool(_DSN, min_size=2, max_size=4)

    stats = {
        "depts_visited": 0,
        "pages_fetched": 0,
        "parsed": 0,
        "with_web": 0,
        "upserted": 0,
    }

    depts = _DEPARTMENTS[:_MAX_DEPT] if _MAX_DEPT else _DEPARTMENTS

    consecutive_empty = 0  # track consecutive depts with 0 results (Cloudflare signal)

    for dept in depts:
        dept_parsed = 0
        dept_with_web = 0

        # Page 1
        p1_url = f"{_BASE}?quoiqui={_QUERY}&ou={dept}&page=1"
        time.sleep(_THROTTLE)
        html1 = _fetch_via_curl(p1_url)
        if not html1:
            log.debug("Dept %s page 1 — no content (CF blocked?), skipping", dept)
            consecutive_empty += 1
            if consecutive_empty >= 3:
                log.warning(
                    "%d consecutive empty depts — Cloudflare likely active; "
                    "backing off %.0fs", consecutive_empty, _CF_BACKOFF
                )
                time.sleep(_CF_BACKOFF)
                consecutive_empty = 0
            continue

        total = parse_total_results(html1)
        total_pages = pages_for_count(total)
        if _MAX_PAGES_PER_DEPT and total_pages > _MAX_PAGES_PER_DEPT:
            total_pages = _MAX_PAGES_PER_DEPT

        candidates = parse_listing_page(html1)
        if not candidates and total == 0:
            # Truly empty dept (small rural dept with no concessionnaires)
            log.debug("Dept %s has 0 results (genuinely empty)", dept)
            consecutive_empty += 1
            if consecutive_empty >= 5:
                log.warning(
                    "%d consecutive 0-result depts — possible CF block; "
                    "backing off %.0fs", consecutive_empty, _CF_BACKOFF
                )
                time.sleep(_CF_BACKOFF)
                consecutive_empty = 0
            stats["depts_visited"] += 1
            log.info(
                "Dept %s: pages=1 parsed=0 with_web=0 | totals: parsed=%d with_web=%d upserted=%d",
                dept, stats["parsed"], stats["with_web"], stats["upserted"],
            )
            continue

        consecutive_empty = 0  # reset on successful data fetch
        stats["pages_fetched"] += 1
        for c in candidates:
            dept_parsed += 1
            if c.get("domain"):
                dept_with_web += 1
            if await _upsert(pool, c):
                stats["upserted"] += 1

        # Pages 2..N
        for page_num in range(2, total_pages + 1):
            if _MAX_PAGES_PER_DEPT and page_num > _MAX_PAGES_PER_DEPT:
                break
            time.sleep(_THROTTLE)
            url = f"{_BASE}?quoiqui={_QUERY}&ou={dept}&page={page_num}"
            page_html = _fetch_via_curl(url)
            if not page_html:
                log.debug("Dept %s page %d — no content, stopping dept", dept, page_num)
                break

            candidates = parse_listing_page(page_html)
            if not candidates:
                break

            stats["pages_fetched"] += 1
            for c in candidates:
                dept_parsed += 1
                if c.get("domain"):
                    dept_with_web += 1
                if await _upsert(pool, c):
                    stats["upserted"] += 1

        stats["depts_visited"] += 1
        stats["parsed"] += dept_parsed
        stats["with_web"] += dept_with_web

        log.info(
            "Dept %s: pages=%d parsed=%d with_web=%d | totals: parsed=%d with_web=%d upserted=%d",
            dept, total_pages, dept_parsed, dept_with_web,
            stats["parsed"], stats["with_web"], stats["upserted"],
        )

    await pool.close()
    log.info(
        "DONE fr_pagesjaunes: depts=%d pages=%d parsed=%d with_web=%d upserted=%d",
        stats["depts_visited"], stats["pages_fetched"],
        stats["parsed"], stats["with_web"], stats["upserted"],
    )
    return stats


if __name__ == "__main__":
    asyncio.run(run())
