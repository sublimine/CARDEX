"""
DE discovery — GelbeSeiten.de dealer directory (Germany's yellow pages).

GelbeSeiten lists all Autohandel (car dealers) Bundesweit (nationwide).  Every
entry carries a UUID stable registry_id, and ~92 % of entries carry the dealer's
own website encoded as a base64 data attribute — making this one of the highest-
signal DE free sources for dealers WITH a domain.

Verified live 2026-06-07:
  Total listings: 27 455 (gesamtanzahlTreffer)
  Strategy: HTML page 1 (50 results) + AJAX /ajaxsuche POST (10 per batch, ~2741 batches)
  URL: https://www.gelbeseiten.de/suche/autohandel/bundesweit
  AJAX: POST https://www.gelbeseiten.de/ajaxsuche
        fields: WAS=autohandel, umkreis=-1, verwandt=false, position=<N>, anzahl=10

Each <article> inside the response HTML carries:
  data-realid="<uuid>"              → registry_id
  data-webseiteLink="<base64>"      → dealer website URL → domain
  <h2 class="mod-Treffer__name">   → dealer name
  data-prg="<base64>"              → several; one decodes to google maps URL with address

Usage:
    python -m scrapers.discovery.sources.de_gelbeseiten
    LOG_LEVEL=DEBUG python -m scrapers.discovery.sources.de_gelbeseiten
    MAX_PAGES=10 python -m scrapers.discovery.sources.de_gelbeseiten   # quick smoke test
"""
from __future__ import annotations

import asyncio
import base64
import html as html_mod
import json
import logging
import os
import re
import time
import urllib.parse
import urllib.request

import asyncpg

log = logging.getLogger("de_gelbeseiten")
logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s [de_gelbeseiten] %(message)s",
)

_DSN = os.environ.get(
    "DATABASE_URL", "postgresql://cardex:cardex_dev_only@localhost:5432/cardex"
)
_BASE_URL = "https://www.gelbeseiten.de/suche/autohandel/bundesweit"
_AJAX_URL = "https://www.gelbeseiten.de/ajaxsuche"
_SOURCE = "gelbeseiten"
_SOURCE_LAYER = 2
_COUNTRY = "DE"
_THROTTLE = float(os.environ.get("GS_THROTTLE", "0.3"))
_MAX_PAGES = int(os.environ.get("MAX_PAGES", "0"))  # 0 = unlimited

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)
_HEADERS_HTML = {
    "User-Agent": _UA,
    "Accept": "text/html,application/xhtml+xml,*/*;q=0.9",
}
_HEADERS_AJAX = {
    "User-Agent": _UA,
    "Accept": "text/html, */*; q=0.01",
    "Content-Type": "application/x-www-form-urlencoded",
    "X-Requested-With": "XMLHttpRequest",
    "Referer": _BASE_URL,
    "Origin": "https://www.gelbeseiten.de",
}

# ---------------------------------------------------------------------------
# Pure parsing helpers (testable without network)
# ---------------------------------------------------------------------------

def _s(v: object) -> str | None:
    """Coerce to stripped string or None."""
    if v is None:
        return None
    out = str(v).strip()
    return out or None


def _decode_b64(b64: str) -> str | None:
    """Decode a GelbeSeiten base64 field (no padding guaranteed).  Returns
    the decoded UTF-8 string, or None on failure."""
    if not b64:
        return None
    # Pad to a multiple of 4
    padded = b64 + "==" * ((4 - len(b64) % 4) % 4)
    try:
        return base64.b64decode(padded).decode("utf-8", "replace").strip()
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


def _extract_address_from_maps(art_html: str) -> str | None:
    """Extract street+city from a Google Maps data-prg value embedded in the
    article HTML.  Returns a raw string like 'Dieselstr. 2, 44805 Bochum', or
    None."""
    for b64 in re.findall(r'data-prg="([^"]+)"', art_html):
        decoded = _decode_b64(b64)
        if decoded and "maps/place/" in decoded:
            # maps URL looks like: ...maps/place/<address>
            try:
                path = urllib.parse.urlparse(decoded).path
                # path: /maps/place/Dieselstr. 2, 44805 Bochum
                addr = path.split("/maps/place/", 1)[-1]
                addr = urllib.parse.unquote_plus(addr).strip()
                return addr or None
            except Exception:
                pass
    return None


def parse_article(art_html: str) -> dict | None:
    """Parse one <article> block into a candidate dict.

    Returns None only when we cannot extract even a registry_id (uuid).
    A missing website is acceptable — we insert with registry_id only.
    """
    # registry_id: prefer data-realid, fallback to gsbiz path in href
    uuid_hits = re.findall(r'data-realid="([a-f0-9-]{36})"', art_html)
    if not uuid_hits:
        uuid_hits = re.findall(r"gsbiz/([a-f0-9-]{36})", art_html)
    if not uuid_hits:
        return None
    registry_id = uuid_hits[0]

    # website
    web_b64_hits = re.findall(r'data-webseiteLink="([^"]+)"', art_html)
    url_raw = _decode_b64(web_b64_hits[0]) if web_b64_hits else None
    url = _normalize_url(url_raw)
    dom = _domain(url)

    # name: <h2 class="mod-Treffer__name">…</h2>
    name_hits = re.findall(
        r'<h2[^>]*mod-Treffer__name[^>]*>([^<]+)</h2>', art_html
    )
    name = _s(html_mod.unescape(name_hits[0])) if name_hits else None

    # address from Google Maps data-prg
    address = _extract_address_from_maps(art_html)

    # phone: search for TelefonnummerKompakt text node
    phone_hits = re.findall(
        r'class="[^"]*(?:TelefonnummerKompakt|mod-Telefon)[^"]*"[^>]*>([^<\n]+)',
        art_html,
    )
    phone = _s(phone_hits[0]) if phone_hits else None
    # phone may be 'class=...' text garbage; sanity-check: must start with digit or +
    if phone and not re.match(r'^[\d\+]', phone):
        phone = None

    return {
        "domain": dom,
        "country": _COUNTRY,
        "source_layer": _SOURCE_LAYER,
        "source": _SOURCE,
        "url": url,
        "name": name,
        "address": address,
        "city": None,        # city is embedded in address string; not split separately
        "postcode": None,    # same
        "phone": phone,
        "email": None,
        "lat": None,
        "lng": None,
        "registry_id": registry_id,
        "external_refs": {"listing": f"https://www.gelbeseiten.de/gsbiz/{registry_id}"},
    }


def parse_html_page(page_html: str) -> list[dict]:
    """Parse articles from a full HTML page or an AJAX inner-HTML string.
    Returns only candidates that have at least a registry_id."""
    articles = re.findall(r"<article[^>]*>.*?</article>", page_html, re.DOTALL)
    candidates: list[dict] = []
    seen_ids: set[str] = set()
    for art in articles:
        c = parse_article(art)
        if c is None:
            continue
        rid = c["registry_id"]
        if rid in seen_ids:
            continue  # skip duplicates (pinned/sponsored repeat)
        seen_ids.add(rid)
        candidates.append(c)
    return candidates


# ---------------------------------------------------------------------------
# Network layer (synchronous — keeps RAM flat: one page at a time)
# ---------------------------------------------------------------------------

def _fetch_get(url: str) -> str:
    req = urllib.request.Request(url, headers=_HEADERS_HTML)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8", "replace")


def _fetch_ajax(position: int) -> tuple[list[dict], int]:
    """POST to /ajaxsuche, return (candidates, total_from_server).
    total_from_server is 0 when not available (parsing failure)."""
    form = urllib.parse.urlencode(
        {"umkreis": "-1", "verwandt": "false", "WAS": "autohandel",
         "position": str(position), "anzahl": "10"}
    ).encode()
    req = urllib.request.Request(_AJAX_URL, data=form, headers=_HEADERS_AJAX)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode("utf-8", "replace")
    except Exception as exc:
        log.warning("AJAX request failed pos=%d: %s", position, exc)
        return [], 0

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        log.warning("AJAX JSON decode failed pos=%d (len=%d)", position, len(raw))
        return [], 0

    inner_html = data.get("html", "")
    total = int(data.get("gesamtanzahlTreffer", 0))
    candidates = parse_html_page(inner_html)
    return candidates, total


# ---------------------------------------------------------------------------
# DB upsert (same two-route pattern as ch_agvs.py)
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
        c.get("lat"), c.get("lng"), registry_id,
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
# Main run: page-by-page, RAM-safe
# ---------------------------------------------------------------------------

async def run() -> int:
    """Fetch all GelbeSeiten Autohandel listings and upsert to discovery_candidates.

    Returns the total number of candidates upserted."""
    pool = await asyncpg.create_pool(_DSN, min_size=2, max_size=4)

    total_parsed = 0
    total_with_web = 0
    total_upserted = 0
    pages_scraped = 0
    max_pages = _MAX_PAGES  # 0 = unlimited

    # ---- Page 1: full HTML (50 results) ----
    log.info("Fetching page 1 from %s", _BASE_URL)
    try:
        html1 = _fetch_get(_BASE_URL)
    except Exception as exc:
        log.error("Failed to fetch page 1: %s", exc)
        await pool.close()
        return 0

    candidates1 = parse_html_page(html1)
    pages_scraped += 1
    for c in candidates1:
        total_parsed += 1
        if c["domain"]:
            total_with_web += 1
        if await _upsert(pool, c):
            total_upserted += 1

    log.info("Page 1: parsed=%d with_web=%d upserted=%d",
             len(candidates1), sum(1 for c in candidates1 if c["domain"]), total_upserted)

    if max_pages == 1:
        await pool.close()
        return total_upserted

    # ---- AJAX pages: position 51, 61, 71, ... ----
    # Discover total from page 1 or first AJAX call
    server_total = 27455  # verified 2026-06-07; will be updated from first AJAX response
    position = 51

    while True:
        if max_pages and pages_scraped >= max_pages:
            log.info("MAX_PAGES=%d reached — stopping early", max_pages)
            break

        time.sleep(_THROTTLE)

        candidates, srv_total = _fetch_ajax(position)

        if srv_total:
            server_total = srv_total  # keep refreshing for accuracy

        if not candidates:
            # Empty batch — either end of results or transient error
            log.info("Empty batch at position=%d, total_expected=%d — stopping", position, server_total)
            break

        pages_scraped += 1
        page_with_web = 0
        for c in candidates:
            total_parsed += 1
            if c["domain"]:
                total_with_web += 1
                page_with_web += 1
            if await _upsert(pool, c):
                total_upserted += 1

        if pages_scraped % 100 == 0:
            log.info(
                "Progress: pages=%d pos=%d parsed=%d with_web=%d upserted=%d / expected~%d",
                pages_scraped, position, total_parsed, total_with_web, total_upserted, server_total,
            )

        position += 10

        # Stop when we've fetched everything the server claims to have
        if total_parsed >= server_total:
            log.info("Reached server_total=%d after %d pages", server_total, pages_scraped)
            break

    await pool.close()

    log.info(
        "DONE de_gelbeseiten: pages=%d parsed=%d with_web=%d upserted=%d",
        pages_scraped, total_parsed, total_with_web, total_upserted,
    )
    return total_upserted


if __name__ == "__main__":
    asyncio.run(run())
