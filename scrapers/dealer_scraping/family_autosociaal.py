"""autosociaal (Dealertemplates) family extractor — ONE recipe closes ~77 NL dealers.

Platform truth (lieutenant 4-way live probe 2026-06-09/10; re-verified 2026-06-11
with a 3-request fixture capture, see ``scrapers/tests/fixtures/autosociaal/``):

  * Laravel + Livewire dealer-site SaaS ("Dealertemplates", nginx). Frontend
    bundle ships from ``cdn.autosociaal.nl/dtweb/``; vehicle data backend is
    Hexon (7-digit stock ids). ``cms_fingerprint`` verdict key: ``autosociaal``.
  * Catalog = a Livewire grid on a ONE-segment route whose slug VARIES per
    dealer: ``/occasions`` | ``/aanbod`` | ``/voorraad``. A wrong slug 404s hard
    (garagevantreuren.nl/occasions -> 404, real capture 2026-06-11).
  * Availability truth: the page's ``wire:snapshot`` carries
    ``data.filteredOccasionsCount`` == the visible "Er zijn <N> voertuigen
    gevonden" heading. ``data.perPage`` = 15.
  * ``?page=N`` is CUMULATIVE (server-side load-more): GET
    ``<slug>?page=ceil(total/15)`` returns the ENTIRE live set in ONE request
    (janvandijk.nl p1=15 cards, p2=27/27 == count, re-verified on own capture).
  * Cards: ``div.grid-item.grid-item--link`` (attr ``wire:key`` = Hexon id);
    first ``a[href]`` = detail deep-link ``/<slug>/<merk>/<model>/<id>``;
    ``.grid-item-subtitle`` = make; ``.grid-item-title h3`` = model;
    ``.grid-item-detail-price h4`` = price (prefer the ``-primary`` variant);
    ``.grid-item-summary-item`` rows with icon classes ``ti-calendar-event`` /
    ``ti-road`` = year / km — THEME-DEPENDENT: themes without the summary row
    yield None there (robust year/km lives on the detail page's
    ``.details-table-item`` NL labels — the enrichment stage's job, not ours).
  * NO JSON-LD anywhere — the generic JSON-LD-first engine cannot extract this
    family, hence this dedicated module. ``configs/families/autosociaal.json``
    records the surface + provenance and keeps catalog tokens/detail-regex as a
    fallback for the generic availability-first listing walk.

Doctrine: availability-first (``?page=last`` IS the available set; sitemap.xml
also lists static pages and is only a slug hint here), fetcher injected (tests
run offline on fixtures), no state outside the returned dict, never raises on a
bad dealer. Output listings match the ``inventory_harvester.cage_inventory``
contract: ``[{"url", "title", "price", "year", "km"}]``.

One-dealer invocation (owner-run, hits the network):
    py -m scrapers.dealer_scraping.family_autosociaal janvandijk.nl
or from code:
    fetcher = make_dealer_fetcher()           # curl_cffi, JA3-coherent session
    result = await harvest_autosociaal("janvandijk.nl", fetcher)
    await cage_inventory(pg, rdb, result["domain"], "NL", result["listings"],
                         config_ref="configs/families/autosociaal.json")
"""
from __future__ import annotations

import logging
import math
import re
from collections import Counter
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup

log = logging.getLogger(__name__)

# Slug candidates verified by the lieutenant across the family (order = priority).
CANDIDATE_SLUGS: tuple[str, ...] = ("occasions", "aanbod", "voorraad")
DEFAULT_PER_PAGE = 15

# wire:snapshot is an HTML-escaped JSON attribute (&quot;) in wire format; tooling
# that re-serializes (BeautifulSoup round-trips) may yield plain quotes — match both.
_SNAPSHOT_COUNT_RE = re.compile(
    r'(?:&quot;|")filteredOccasionsCount(?:&quot;|")\s*:\s*(?:&quot;|")?(\d+)')
_SNAPSHOT_PERPAGE_RE = re.compile(r'(?:&quot;|")perPage(?:&quot;|")\s*:\s*(?:&quot;|")?(\d+)')
# Visible fallback: <h2>Er zijn 27 voertuigen gevonden</h2>
_FOUND_TEXT_RE = re.compile(r"(\d+)\s*voertuigen gevonden")
# PDP path shape: /<slug>/<merk>/<model>/<hexon id>. Verified ids are 7 digits;
# 6-9 tolerated deliberately so Hexon id growth never zeroes the family.
_DETAIL_PATH_RE = re.compile(r"^/([a-z0-9-]+)/[^/]+/[^/]+/\d{6,9}/?$")
_LOC_RE = re.compile(r"<loc>\s*([^<\s]+)\s*</loc>")
_YEAR_IN_TEXT_RE = re.compile(r"\b((?:19|20)\d{2})\b")


# ── value guards (parity with inventory_harvester._digits/_price/_year/_km;
#    duplicated on purpose: this module is self-contained and those are private) ──
def _digits(v) -> int | None:
    if v is None:
        return None
    m = re.search(r"\d[\d.\s']*", str(v))
    if not m:
        return None
    try:
        return int(re.sub(r"[.\s']", "", m.group(0)))
    except ValueError:
        return None


def _price(v) -> int | None:
    n = _digits(v)
    return n if n and 100 <= n <= 5_000_000 else None


def _year_from_text(text: str) -> int | None:
    # Themes render "2022" or "03-2022" — isolate the 4-digit year, then guard.
    m = _YEAR_IN_TEXT_RE.search(text or "")
    if not m:
        return None
    n = int(m.group(1))
    return n if 1950 <= n <= 2027 else None


def _km(v) -> int | None:
    n = _digits(v)
    return n if n is not None and 0 <= n <= 2_000_000 else None


def _normalize_host(host: str) -> str:
    """Bare lowercase hostname: scheme and any path/trailing slash stripped."""
    h = (host or "").strip().lower()
    for scheme in ("https://", "http://"):
        if h.startswith(scheme):
            h = h[len(scheme):]
    return h.split("/", 1)[0]


# ── pure parsers (offline-testable against fixtures) ─────────────────────────────
def parse_occasions_count(html: str) -> int | None:
    """The dealer's live availability total, or None when unreadable (drift).

    Authoritative source first (``wire:snapshot`` ``filteredOccasionsCount``),
    visible "<N> voertuigen gevonden" heading as fallback. Both verified equal
    live on janvandijk.nl (27/27, 2026-06-11).
    """
    m = _SNAPSHOT_COUNT_RE.search(html) or _FOUND_TEXT_RE.search(html)
    return int(m.group(1)) if m else None


def parse_per_page(html: str) -> int:
    """The snapshot's ``perPage`` (verified 15), defaulting safely."""
    m = _SNAPSHOT_PERPAGE_RE.search(html)
    if not m:
        return DEFAULT_PER_PAGE
    n = int(m.group(1))
    return n if n >= 1 else DEFAULT_PER_PAGE


def is_catalog_page(html: str) -> bool:
    """True when the HTML is the Livewire occasions grid (count is readable)."""
    return parse_occasions_count(html) is not None


def discover_slug_from_sitemap(xml: str) -> str | None:
    """Catalog slug = the first path segment PDP URLs share in the flat urlset.

    Only PDP-shaped paths (``/<slug>/<merk>/<model>/<id>``) vote, so static
    pages never pollute the verdict; majority wins. None on 0-stock dealers
    (no PDPs listed) — callers fall through to nav/candidates.
    """
    votes: Counter[str] = Counter()
    for loc in _LOC_RE.findall(xml or ""):
        m = _DETAIL_PATH_RE.match(urlsplit(loc.strip()).path)
        if m:
            votes[m.group(1)] += 1
    return votes.most_common(1)[0][0] if votes else None


def discover_slug_from_nav(html: str,
                           candidates: tuple[str, ...] = CANDIDATE_SLUGS) -> str | None:
    """First candidate slug present as a one-segment link in the site nav.

    Scoped to ``<nav>`` elements when present (janvandijk.nl nav carries
    ``/occasions``, verified), falling back to the whole document.
    """
    soup = BeautifulSoup(html or "", "html.parser")
    scopes = soup.find_all("nav") or [soup]
    found: set[str] = set()
    for scope in scopes:
        for a in scope.find_all("a", href=True):
            path = urlsplit(a["href"]).path.strip("/")
            if path in candidates:
                found.add(path)
    for cand in candidates:           # deterministic: candidate order, not DOM order
        if cand in found:
            return cand
    return None


def _card_to_listing(card, base_url: str) -> dict | None:
    a = card.find("a", href=True)
    if a is None:
        return None
    url = urljoin(base_url, a["href"])
    make_el = card.select_one(".grid-item-subtitle")
    model_el = card.select_one(".grid-item-title h3")
    make = make_el.get_text(" ", strip=True) if make_el else ""
    model = model_el.get_text(" ", strip=True) if model_el else ""
    title = " ".join(p for p in (make, model) if p) or None

    price_el = (card.select_one(".grid-item-detail-price-primary h4")
                or card.select_one(".grid-item-detail-price h4"))
    price = _price(price_el.get_text(" ", strip=True)) if price_el else None

    year = km = None
    for item in card.select(".grid-item-summary-item"):
        icon = item.find("i")
        icon_classes = " ".join(icon.get("class") or []) if icon else ""
        text = item.get_text(" ", strip=True)
        if year is None and ("ti-calendar" in icon_classes
                             or _YEAR_IN_TEXT_RE.fullmatch(text)):
            year = _year_from_text(text)
        elif km is None and ("ti-road" in icon_classes or text.lower().endswith("km")):
            km = _km(text)
    return {"url": url, "title": title, "price": price, "year": year, "km": km}


def parse_listing_cards(html: str, base_url: str) -> list[dict]:
    """Every vehicle card on a catalog page → cage_inventory-shaped dicts.

    Deduplicated by URL (the cumulative ``?page=last`` page must yield exactly
    ``filteredOccasionsCount`` listings — verified 27/27 on janvandijk.nl).
    """
    soup = BeautifulSoup(html or "", "html.parser")
    out: list[dict] = []
    seen: set[str] = set()
    for card in soup.select("div.grid-item.grid-item--link"):
        li = _card_to_listing(card, base_url)
        if li is not None and li["url"] not in seen:
            seen.add(li["url"])
            out.append(li)
    return out


# ── orchestration (fetcher injected; FetchResult duck-typed: status_code + body/text)
async def _fetch(fetcher, url: str):
    """One guarded GET — transport faults are a miss, never an abort."""
    try:
        return await fetcher(url)
    except Exception as exc:  # noqa: BLE001 — one bad URL never aborts the dealer
        log.warning("autosociaal fetch failed url=%s err=%s", url, exc)
        return None


def _text_of(fr) -> str:
    text = getattr(fr, "text", None)
    if isinstance(text, str):
        return text
    body = getattr(fr, "body", b"") or b""
    return body.decode("utf-8", errors="replace")


def _final_url(fr, fallback: str) -> str:
    return str(getattr(fr, "url", "") or fallback)


async def harvest_autosociaal(host: str, fetcher, *,
                              candidate_slugs: tuple[str, ...] = CANDIDATE_SLUGS) -> dict:
    """Full availability-first harvest of one autosociaal dealer. Never raises.

    1. Discover the catalog slug: sitemap PDP prefix → home nav → candidates.
    2. GET the catalog, read ``filteredOccasionsCount`` (availability truth).
    3. When count > page-1 cards: ONE extra GET of ``?page=ceil(count/perPage)``
       — cumulative load-more returns the whole live set.
    4. Parse cards → ``listings`` in the cage_inventory shape.

    Returns ``{"domain", "slug", "total", "complete", "listings", "ok", "reason"}``.
    0-stock dealers are a VALID result (ok=True, total=0, listings=[]); only a
    dealer with no reachable catalog comes back ok=False.
    """
    domain = _normalize_host(host)
    base = f"https://{domain}"

    # (1) slug discovery — cheap hints first, declared candidates as the floor
    order: list[str] = []
    sm = await _fetch(fetcher, f"{base}/sitemap.xml")
    if sm is not None and getattr(sm, "status_code", 0) == 200:
        slug = discover_slug_from_sitemap(_text_of(sm))
        if slug:
            order.append(slug)
    if not order:
        home = await _fetch(fetcher, f"{base}/")
        if home is not None and getattr(home, "status_code", 0) == 200:
            slug = discover_slug_from_nav(_text_of(home), candidate_slugs)
            if slug:
                order.append(slug)
    for cand in candidate_slugs:
        if cand not in order:
            order.append(cand)

    # (2) first candidate that renders the Livewire grid (wrong slug 404s hard)
    slug = page1 = page1_url = None
    for cand in order:
        url = f"{base}/{cand}"
        fr = await _fetch(fetcher, url)
        if fr is not None and getattr(fr, "status_code", 0) == 200:
            text = _text_of(fr)
            if is_catalog_page(text):
                slug, page1, page1_url = cand, text, _final_url(fr, url)
                break
    if page1 is None:
        return {"domain": domain, "slug": None, "total": None, "complete": False,
                "listings": [], "ok": False, "reason": "catalog_not_found"}

    total = parse_occasions_count(page1)
    per_page = parse_per_page(page1)
    if total == 0:
        return {"domain": domain, "slug": slug, "total": 0, "complete": True,
                "listings": [], "ok": True, "reason": None}

    # (3+4) page 1 cards; ONE cumulative last-page GET when more exist
    listings = parse_listing_cards(page1, page1_url)
    if total is not None and len(listings) < total:
        last = math.ceil(total / per_page)
        url = f"{base}/{slug}?page={last}"
        fr = await _fetch(fetcher, url)
        if fr is not None and getattr(fr, "status_code", 0) == 200:
            full = parse_listing_cards(_text_of(fr), _final_url(fr, url))
            if len(full) >= len(listings):    # cumulative superset, else keep page 1
                listings = full
        else:
            log.warning("autosociaal %s: last-page fetch failed (%s) — keeping page-1 set",
                        domain, url)

    complete = total is not None and len(listings) == total
    if not complete:
        log.warning("autosociaal %s: parsed %d cards vs filteredOccasionsCount=%s",
                    domain, len(listings), total)
    return {"domain": domain, "slug": slug, "total": total, "complete": complete,
            "listings": listings, "ok": True,
            "reason": None if complete else "count_mismatch"}


if __name__ == "__main__":  # pragma: no cover — live CLI, owner-invoked explicitly
    import argparse
    import asyncio
    import json
    import sys

    from scrapers.dealer_scraping.harvester import make_dealer_fetcher

    ap = argparse.ArgumentParser(description="Harvest ONE autosociaal dealer (live).")
    ap.add_argument("host", help="dealer host, e.g. janvandijk.nl")
    args = ap.parse_args()

    async def _main() -> int:
        fetcher = make_dealer_fetcher()
        try:
            result = await harvest_autosociaal(args.host, fetcher)
        finally:
            aclose = getattr(fetcher, "aclose", None)
            if aclose is not None:
                await aclose()
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result["ok"] else 1

    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    raise SystemExit(asyncio.run(_main()))
