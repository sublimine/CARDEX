"""
E07 — browser-rendered extraction for JS/SPA portals (Playwright).

The static cascade (E01 JSON-LD / E03 sitemap) sees only pre-render HTML, so a SPA
that paints its vehicle into the DOM client-side yields nothing (the 5-country
portals + dealer sites all gave dlq/transient). E07 renders the page in a real
browser, then extracts the vehicle.

KEY INSIGHT (verified live on autolina.ch, autohero.com): even SPAs that ship NO
JSON-LD and NO clean data-XHR still populate **SEO meta** — ``og:title`` and the
``<meta name="description">`` — with the full vehicle, because they need it for
link previews / search. autolina's description is literally:

    "SKODA Kamiq 1.5 TSI … Kilometer: 10'600 km, …, Preis: CHF 29'500,
     Erstzulassung: 01.09.2025, Farbe: Silber, Inserat-ID: 4997584"

So E07's primary extractor is GENERIC (no per-portal CSS selectors): parse the
rendered ``og:title`` + meta description (multilingual labels) into the SAME raw
dict the static path produces, then through the SAME ``to_record`` + quality gate.
``parse_rendered_meta`` / ``record_from_rendered`` are PURE (HTML in → record out),
unit-tested without a browser; ``PlaywrightFetcher`` is the thin browser shell,
validated by the live E2E run.

Tier-1 portals behind Akamai/DataDome still need residential proxies → backlog (P3);
E07 unblocks the JS-render gap, not the anti-bot-challenge gap.
"""
from __future__ import annotations

import logging
import re
from html import unescape

from scrapers.pipeline.generic_extractor import FetchResult
from scrapers.pipeline.normalize import to_record
from scrapers.pipeline.parse import parse_listing
from scrapers.pipeline.quality import evaluate
from scrapers.pipeline.schema import VehicleRecord

log = logging.getLogger(__name__)

# ── meta extraction (pure) ──────────────────────────────────────────────────────
_META_TAG_RE = re.compile(r"<meta\b[^>]*>", re.I)
# Quote-aware per-attribute: a double-quoted value may contain apostrophes (Swiss
# thousands sep "29'500") and vice-versa — match the actual delimiter, never a
# shared [^"'] class (which truncates at the first inner quote).
_KEY_RE = re.compile(r'(?:property|name)\s*=\s*"([^"]+)"', re.I)
_KEY_RE_S = re.compile(r"(?:property|name)\s*=\s*'([^']+)'", re.I)
_CONTENT_RE = re.compile(r'content\s*=\s*"([^"]*)"', re.I)
_CONTENT_RE_S = re.compile(r"content\s*=\s*'([^']*)'", re.I)
_TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.I | re.S)

# currency-amount, both orders (CH "CHF 29'500" / FR "14 990 EUR"); Swiss (') / EU
# (. ,) thousands separators tolerated.
_PRICE_PRE_RE = re.compile(r"(CHF|EUR|€|Fr\.?)\s*([0-9][0-9'’.,\s]{2,}[0-9])", re.I)
_PRICE_POST_RE = re.compile(r"([0-9][0-9'’.,\s]{2,}[0-9])\s*(CHF|EUR|€)", re.I)
_CCY_NORM = {"€": "EUR", "FR": "CHF", "FR.": "CHF"}

# multilingual "label: value" — DE/FR/ES/NL/IT/EN
_KM_RE = re.compile(
    r"(?:Kilometer|Kilometerstand|Kilom[eèé]trage|Kil[oó]metros|Kilometrastand|Mileage|"
    r"Tellerstand|Chilometri|km-?Stand)\D{0,6}([0-9][0-9'’.,\s]{1,})\s*km",
    re.I,
)
_KM_FALLBACK = re.compile(r"([0-9][0-9'’.,\s]{2,})\s*km\b", re.I)
_YEAR_LABEL_RE = re.compile(
    r"(?:Erstzulassung|Inverkehrsetzung|Mise en circulation|1[èe]re mise|"
    r"Matriculaci[oó]n|Bouwjaar|Immatricolazione|First registration|Baujahr)\D{0,4}"
    r"(?:\d{1,2}[./-])?(?:\d{1,2}[./-])?((?:19|20)\d{2})",
    re.I,
)
_YEAR_ANY_RE = re.compile(r"\b((?:19|20)\d{2})\b")


def _norm_amount(s: str) -> str | None:
    """A price string ('29'500' / '18.500' / '12 345') → integer string, or None."""
    digits = re.sub(r"[^0-9]", "", s or "")
    return digits or None


def _meta_map(html: str) -> dict[str, str]:
    """{og:title, description, og:image, …} → value, robust to inner quotes."""
    out: dict[str, str] = {}
    for tag in _META_TAG_RE.findall(html):
        key = _KEY_RE.search(tag) or _KEY_RE_S.search(tag)
        val = _CONTENT_RE.search(tag) or _CONTENT_RE_S.search(tag)
        if key and val:
            out.setdefault(key.group(1).lower().strip(), unescape(val.group(1)).strip())
    return out


def _split_make_model(title: str) -> tuple[str | None, str | None]:
    """Heuristic make/model from a title head ('SKODA Kamiq 1.5 TSI …')."""
    # cut trailing noise (price / 'gebraucht'/'occasion'/'kaufen'/site name)
    head = re.split(
        r"\b(?:gebraucht|occasion|occasione|kaufen|f[üu]r|pour|auf|sur|\bCHF\b|\bEUR\b|[|–\-])",
        title, maxsplit=1, flags=re.I,
    )[0]
    toks = [t for t in re.split(r"\s+", head.strip()) if t]
    if not toks:
        return None, None
    make = toks[0]
    model = toks[1] if len(toks) > 1 else None
    return make, model


def parse_rendered_meta(html: str) -> dict:
    """
    Extract a raw vehicle dict from a RENDERED page's SEO meta + title (pure).

    Reads og:title / twitter:title / <title> for make/model/price, and the meta
    description (the richest, label:value source) for km/year/price/color. Returns
    the same raw-dict shape ``to_record`` consumes; absent fields simply stay out.
    """
    meta = _meta_map(html)
    title = meta.get("og:title") or meta.get("twitter:title") or ""
    if not title:
        m = _TITLE_RE.search(html)
        title = unescape(m.group(1)).strip() if m else ""
    desc = meta.get("description") or meta.get("og:description") or ""
    blob = f"{title} — {desc}"

    raw: dict = {}
    make, model = _split_make_model(title)
    if make:
        raw["make"] = make
    if model:
        raw["model"] = model

    pm = _PRICE_PRE_RE.search(blob)
    if pm:
        amt, ccy = pm.group(2), pm.group(1)
    else:
        pm = _PRICE_POST_RE.search(blob)
        amt, ccy = (pm.group(1), pm.group(2)) if pm else (None, None)
    if amt:
        n = _norm_amount(amt)
        if n:
            raw["price"] = n
            raw["currency"] = _CCY_NORM.get(ccy.upper(), ccy.upper())

    km = _KM_RE.search(blob) or _KM_FALLBACK.search(desc)
    if km:
        v = _norm_amount(km.group(1))
        if v:
            raw["mileage"] = v

    ym = _YEAR_LABEL_RE.search(blob) or _YEAR_ANY_RE.search(title)
    if ym:
        raw["year"] = ym.group(1)

    imgs = [meta[k] for k in ("og:image", "og:image:secure_url", "twitter:image") if meta.get(k)]
    if imgs:
        raw["images"] = imgs
    return raw


def record_from_rendered(
    html: str, *, source_url: str, source_domain: str, country: str
) -> tuple[VehicleRecord | None, str]:
    """
    Turn a rendered page into a VehicleRecord (pure).

    Merges the static cascade (``parse_listing`` — catches any JS-injected JSON-LD,
    OG, heuristics) with the rendered-meta extractor (the SPA win), preferring the
    static value when present, then runs the SAME ``to_record`` + quality gate as
    every other strategy — so E07 output is contract-identical to E01/E03.
    """
    static = parse_listing(html)
    meta = parse_rendered_meta(html)
    # META WINS: on a SPA the static cascade returns heuristic noise (it grabbed
    # "600" for a 10'600 km car); the labelled SEO meta is authoritative. Static
    # only fills fields meta did not extract (e.g. JS-injected JSON-LD make/model).
    merged = {**static, **{k: v for k, v in meta.items() if v not in (None, "", [], (), {})}}
    if not merged:
        return None, "no_fields"
    record = to_record(merged, source_url=source_url, source_domain=source_domain, country=country)
    if not record.has_critical_fields():
        return None, "missing_critical:" + ",".join(record.missing_critical())
    verdict = evaluate(record, html=html)
    if not verdict.ok:
        return None, verdict.reason
    return record, "ok"


# ── browser shell (Playwright) — integration, validated by the live E2E run ─────
class PlaywrightFetcher:
    """
    A ``Fetcher`` that returns the JS-RENDERED HTML of a page.

    One headless Chromium reused across calls (launch is expensive). Drop-in for
    the seam: the worker builds it once per SPA source and closes it at the end.
    Use as an async context manager. ``wait_until='domcontentloaded'`` + a short
    settle beats ``networkidle`` (SPA ad/tracker traffic never goes idle).
    """

    def __init__(self, *, settle_ms: int = 3500, timeout_ms: int = 40000,
                 locale: str = "de-CH",
                 user_agent: str = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                                    "Chrome/131.0.0.0 Safari/537.36")) -> None:
        self._settle = settle_ms
        self._timeout = timeout_ms
        self._locale = locale
        self._ua = user_agent
        self._pw = None
        self._browser = None
        self._ctx = None

    async def __aenter__(self) -> "PlaywrightFetcher":
        from playwright.async_api import async_playwright

        self._pw = await async_playwright().start()
        self._browser = await self._pw.chromium.launch(headless=True)
        self._ctx = await self._browser.new_context(user_agent=self._ua, locale=self._locale)
        return self

    async def __aexit__(self, *exc) -> None:
        for closer in (self._ctx, self._browser):
            try:
                if closer is not None:
                    await closer.close()
            except Exception:  # noqa: BLE001
                pass
        if self._pw is not None:
            await self._pw.stop()

    async def __call__(self, url: str) -> FetchResult:
        page = await self._ctx.new_page()
        status = 200
        try:
            resp = await page.goto(url, wait_until="domcontentloaded", timeout=self._timeout)
            if resp is not None:
                status = resp.status
            await page.wait_for_timeout(self._settle)
            html = await page.content()
            final = page.url
        finally:
            await page.close()
        return FetchResult(url=final, status_code=status, body=html.encode("utf-8"))


async def extract_listing_rendered(
    url: str, fetcher, *, country: str, source_domain: str | None = None
) -> tuple[VehicleRecord | None, str]:
    """
    E07 per-URL extraction: render via ``fetcher`` (Playwright) then meta-parse.

    Mirrors ``generic_extractor.extract_listing``'s signature/return so it is a
    drop-in strategy. ``fetcher`` is injected (PlaywrightFetcher live; an in-memory
    map of rendered HTML in tests).
    """
    from urllib.parse import urlparse

    try:
        result = await fetcher(url)
    except Exception as exc:  # noqa: BLE001 — transport fault → transient
        return None, f"fetch_error:{type(exc).__name__}"
    if result.status_code != 200:
        return None, f"http_{result.status_code}"
    final = result.url or url
    domain = source_domain or urlparse(final).netloc.lower().removeprefix("www.")
    return record_from_rendered(result.text, source_url=final, source_domain=domain, country=country)
