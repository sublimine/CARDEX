"""
E07 playwright_xhr — browser-rendered extraction for SPAs that carry the vehicle in a
JSON XHR (not in SEO meta or JSON-LD).

Many modern dealer platforms paint the detail page from a client-side ``fetch``/XHR that
returns the vehicle as JSON (the app state), so the static cascade AND the SEO-meta path
both see nothing. This vector renders the page, captures the JSON XHR responses, finds the
one that IS the vehicle, normalizes it (multilingual key aliases across DE/FR/ES/NL/IT/EN
dealer APIs), and — crucially — INJECTS it back into the returned HTML as a schema.org
``Car`` JSON-LD ``<script>``. So the EXISTING extractor (``extract_listing_rendered`` →
``record_from_rendered`` → ``parse_listing``) consumes it unchanged: **no seam change, no
new route**. ``PlaywrightXHRFetcher`` is a strict superset of ``PlaywrightFetcher`` — it
also returns the rendered HTML, so SEO-meta dealers still work and the page degrades to
``playwright_meta`` when no vehicle JSON is present.

The normalizer is PURE (JSON in → raw dict / JSON-LD out), unit-tested without a browser;
the fetcher is the thin browser shell, validated by the live run.
"""
from __future__ import annotations

import json
import logging
import re
from html import escape

from scrapers.pipeline.generic_extractor import FetchResult

log = logging.getLogger(__name__)

# Injected marker so callers can tell a record came from captured XHR (strategy label).
XHR_MARKER = "<!--cardex-xhr-jsonld-->"

# Canonical field -> the key aliases real dealer APIs use (lowercased match).
_KEY_ALIASES: dict[str, tuple[str, ...]] = {
    "make": ("make", "brand", "marke", "marca", "marque", "manufacturer", "makename",
             "brandname", "makedescription"),
    "model": ("model", "modell", "modello", "modele", "modelname", "modeldescription",
              "modeldenomination"),
    "price": ("price", "grossprice", "pricegross", "preis", "prix", "prezzo", "precio",
              "sellingprice", "retailprice", "grossamount", "amount", "consumerprice"),
    "currency": ("currency", "pricecurrency", "currencycode", "waehrung", "devise"),
    "year": ("year", "vehiclemodeldate", "firstregistration", "firstregistrationdate",
             "erstzulassung", "baujahr", "registrationyear", "modelyear", "matriculacion",
             "bouwjaar", "anneemiseencirculation"),
    "mileage": ("mileage", "mileagekm", "km", "kilometer", "kilometerstand", "kilometers",
                "kilometrage", "odometer", "mileagefromodometer", "kilometraje", "tellerstand"),
    "vin": ("vin", "fin", "vehicleidentificationnumber", "chassisnumber", "chassis"),
    "fuel_type": ("fueltype", "fuel", "kraftstoff", "kraftstoffart", "carburant",
                  "combustible", "energy", "brandstof"),
    "transmission": ("transmission", "vehicletransmission", "getriebe", "getriebeart",
                     "gearbox", "boitevitesse", "cambio", "transmissie"),
    "images": ("images", "image", "photos", "pictures", "media", "imageurls", "gallery",
               "bilder", "fotos"),
}
_VALUE_HOLDERS = ("value", "amount", "val", "raw", "displayvalue", "url", "href", "src", "name")
_SCORE_KEYS = ("make", "model", "price", "year", "vin", "mileage")


def _scalarize(v):
    """Pull a scalar/str out of a value that may be wrapped ({value:..}/{amount:..})."""
    if isinstance(v, (str, int, float)):
        return v
    if isinstance(v, dict):
        for h in _VALUE_HOLDERS:
            for k in v:
                if k.lower() == h and isinstance(v[k], (str, int, float)):
                    return v[k]
    return None


def _to_int_str(s) -> str | None:
    """Integer string from a number or a localized money/distance string.

    Handles DE/CH thousands ('.', ' ', apostrophe) and a trailing 2-digit decimal
    (',00' / '.00'): '36.900' -> '36900', "29'500" -> '29500', '12,500.00' -> '12500'.
    """
    if isinstance(s, bool):
        return None
    if isinstance(s, (int, float)):
        return str(int(s)) if s else None
    t = re.sub(r"[^\d.,]", "", str(s))
    t = re.sub(r"[.,]\d{2}$", "", t)   # drop trailing cents
    t = re.sub(r"[.,]", "", t)          # drop thousand separators
    return t or None


def _collect_images(v) -> list[str]:
    """Every http(s) URL anywhere under an image field (string / list / nested dicts)."""
    out: list[str] = []

    def rec(x, depth: int = 0) -> None:
        if depth > 4:
            return
        if isinstance(x, str):
            if x.startswith("http"):
                out.append(x)
        elif isinstance(x, list):
            for e in x[:80]:
                rec(e, depth + 1)
        elif isinstance(x, dict):
            for e in x.values():
                rec(e, depth + 1)

    rec(v)
    seen: set[str] = set()
    res: list[str] = []
    for u in out:
        if u not in seen:
            seen.add(u)
            res.append(u)
    return res


def _normkeys(node: dict) -> dict[str, str]:
    """Lowercased, separator-stripped key map so 'first_registration' == 'firstregistration'."""
    return {k.lower().replace("_", "").replace("-", "").replace(" ", ""): k for k in node}


def _vehicle_score(node: dict) -> int:
    """How vehicle-like a dict is: count of canonical fields its keys resolve to."""
    low = _normkeys(node)
    score = 0
    for canon in _SCORE_KEYS:
        if any(alias in low for alias in _KEY_ALIASES[canon]):
            score += 1
    return score


def _deep_best_vehicle(obj, depth: int = 0, best=(0, None)):
    """DFS for the dict node with the most vehicle-like keys (handles nested/list JSON)."""
    if depth > 6:
        return best
    if isinstance(obj, dict):
        s = _vehicle_score(obj)
        if s > best[0]:
            best = (s, obj)
        for v in obj.values():
            best = _deep_best_vehicle(v, depth + 1, best)
    elif isinstance(obj, list):
        for v in obj[:50]:
            best = _deep_best_vehicle(v, depth + 1, best)
    return best


def vehicle_json_to_raw(obj) -> dict:
    """
    Normalize a captured JSON payload to the raw dict ``to_record`` consumes.

    Finds the most vehicle-like node anywhere in the payload, then maps its keys via the
    multilingual alias table. Returns {} when nothing vehicle-like is present.
    """
    score, node = _deep_best_vehicle(obj)
    if node is None or score < 2:
        return {}
    low = _normkeys(node)
    raw: dict = {}
    for canon, aliases in _KEY_ALIASES.items():
        key = next((low[a] for a in aliases if a in low), None)
        if key is None:
            continue
        val = node[key]
        if canon == "images":
            imgs = _collect_images(val)
            if imgs:
                raw["images"] = imgs
            continue
        if canon == "price" or canon == "mileage":
            # price/mileage may be nested ({value:..}/{amount:..}) — scalarize, then
            # parse the localized integer (DE '.' thousands etc.).
            n = _to_int_str(_scalarize(val))
            if n:
                raw[canon] = n
            continue
        sval = _scalarize(val)
        if sval in (None, ""):
            continue
        if canon == "year":
            m = re.search(r"(19|20)\d{2}", str(sval))
            if m:
                raw["year"] = m.group(0)
        else:
            raw[canon] = str(sval).strip()
    return raw


def vehicle_json_to_jsonld(raw: dict) -> str | None:
    """Build a schema.org ``Car`` JSON-LD ``<script>`` from a raw dict, or None."""
    if not raw.get("make") or not raw.get("model"):
        return None
    car: dict = {"@context": "https://schema.org", "@type": "Car",
                 "brand": {"name": raw["make"]}, "model": raw["model"]}
    if raw.get("year"):
        car["vehicleModelDate"] = str(raw["year"])
    if raw.get("mileage"):
        car["mileageFromOdometer"] = {"value": str(raw["mileage"])}
    if raw.get("fuel_type"):
        car["fuelType"] = raw["fuel_type"]
    if raw.get("transmission"):
        car["vehicleTransmission"] = raw["transmission"]
    if raw.get("vin"):
        car["vehicleIdentificationNumber"] = raw["vin"]
    if raw.get("images"):
        car["image"] = list(raw["images"])
    if raw.get("price"):
        car["offers"] = {"@type": "Offer", "price": str(raw["price"]),
                         "priceCurrency": (raw.get("currency") or "EUR")}
    payload = json.dumps(car, ensure_ascii=False)
    return f'{XHR_MARKER}<script type="application/ld+json">{payload}</script>'


def inject_jsonld(html: str, jsonld_script: str) -> str:
    """Insert the synthesized JSON-LD into the page <head> (or prepend) so parse sees it."""
    if not jsonld_script:
        return html
    idx = html.lower().find("</head>")
    if idx != -1:
        return html[:idx] + jsonld_script + html[idx:]
    return jsonld_script + html


def was_xhr_injected(html: str) -> bool:
    """True when this HTML carries a vehicle synthesized from a captured XHR."""
    return XHR_MARKER in html


def best_vehicle_jsonld(captured: list) -> str | None:
    """From captured JSON payloads, pick the most vehicle-like and build its JSON-LD."""
    best_raw: dict = {}
    best_score = 0
    for obj in captured:
        raw = vehicle_json_to_raw(obj)
        score = sum(1 for k in ("make", "model", "price", "year") if raw.get(k))
        if score > best_score:
            best_score, best_raw = score, raw
    return vehicle_json_to_jsonld(best_raw) if best_score >= 2 else None


# ── browser shell (Playwright) — superset of PlaywrightFetcher: render + XHR capture ──
class PlaywrightXHRFetcher:
    """
    A ``Fetcher`` that renders a page AND captures its vehicle JSON XHR, injecting the
    captured vehicle (as schema.org JSON-LD) into the returned HTML.

    Drop-in for ``extract_listing_rendered``: it returns the rendered HTML (so SEO-meta
    dealers keep working) augmented with a JSON-LD ``<script>`` whenever a vehicle JSON
    XHR was seen — so a single fetcher serves both ``playwright_meta`` and
    ``playwright_xhr`` sources. One headless Chromium reused; use as an async CM.
    """

    _VEH_HINT = re.compile(
        r"\b(make|brand|marke|model|modell|price|preis|prix|grossprice|vin|"
        r"mileage|kilometer|firstregistration|erstzulassung|vehiclemodeldate)\b", re.I)

    def __init__(self, *, settle_ms: int = 4000, timeout_ms: int = 40000,
                 locale: str = "de-DE", max_body: int = 3_000_000,
                 user_agent: str = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                                    "Chrome/131.0.0.0 Safari/537.36")) -> None:
        self._settle = settle_ms
        self._timeout = timeout_ms
        self._locale = locale
        self._ua = user_agent
        self._max_body = max_body
        self._pw = None
        self._browser = None
        self._ctx = None

    async def __aenter__(self) -> "PlaywrightXHRFetcher":
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

    def _attach_capture(self, page) -> list:
        """Wire a response listener that collects vehicle-looking JSON XHR bodies."""
        captured: list = []

        async def on_response(resp) -> None:
            try:
                if resp.request.resource_type not in ("xhr", "fetch"):
                    return
                ct = (resp.headers or {}).get("content-type", "")
                if "json" not in ct and not resp.url.lower().endswith(".json"):
                    return
                body = await resp.body()
                if not body or len(body) > self._max_body:
                    return
                text = body.decode("utf-8", "replace")
                if not self._VEH_HINT.search(text):
                    return
                captured.append(json.loads(text))
            except Exception:  # noqa: BLE001 — never let capture break the fetch
                return

        page.on("response", on_response)
        return captured

    async def __call__(self, url: str) -> FetchResult:
        page = await self._ctx.new_page()
        captured = self._attach_capture(page)
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

        jsonld = best_vehicle_jsonld(captured)
        if jsonld:
            html = inject_jsonld(html, jsonld)
        return FetchResult(url=final, status_code=status, body=html.encode("utf-8"))

    async def capture_json(self, url: str) -> list:
        """
        Render ``url`` and return the captured vehicle-JSON payloads (no injection).

        The inventory-list path (DMS/widget connector): a catalog render makes the
        embedded widget call its provider API (cross-origin XHR, captured all the same),
        whose JSON array is the dealer's whole inventory — extracted by
        ``dms_connector.extract_vehicles_from_captured``.
        """
        page = await self._ctx.new_page()
        captured = self._attach_capture(page)
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=self._timeout)
            await page.wait_for_timeout(self._settle)
            # Nudge lazy-loaded inventory grids to fetch more of the feed (bounded).
            for _ in range(3):
                try:
                    await page.mouse.wheel(0, 6000)
                    await page.wait_for_timeout(1200)
                except Exception:  # noqa: BLE001
                    break
        finally:
            await page.close()
        return captured
