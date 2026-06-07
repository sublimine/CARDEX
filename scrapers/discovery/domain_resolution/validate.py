"""
Domain-resolution — homepage validation (anti-false-positive gate).

A search result is a GUESS. Before a domain is written to ``discovery_candidates``
its homepage is fetched and must prove it is THIS dealer: a distinctive name token
OR the dealer's city appears on the page, AND the page shows automotive signals.
Both halves matter — name/city alone could be a namesake or a directory mirror;
automotive alone could be the wrong dealer. A domain that fails is discarded, never
persisted (the mission's hard rule: nothing invented).

``confirms_dealer`` is pure (text in → bool); ``validate_domain`` is the thin async
shell that fetches the homepage through an injected fetcher (curl_cffi live; an
in-memory map in tests).
"""
from __future__ import annotations

import re

from scrapers.discovery.domain_resolution.candidate import _norm, name_tokens

# Automotive vocabulary, matched as WHOLE WORDS (\b) over accent-stripped VISIBLE text
# (script/style removed — see _text). Two tiers, because single weak words leak:
#   STRONG (≥1 confirms): terms that essentially only occur in the motor trade.
#   WEAK   (≥2 distinct confirm): real but ambiguous in isolation — an optician has a
#           "showroom", a law firm mentions a "fahrzeug" once. One alone is not enough;
#           a real dealer carries several. Deliberately EXCLUDED entirely: "occasion"/
#           "ocasion" (FR/ES = bargain), "garage" (= parking), bare "motor" (industrial).
_AUTO_STRONG: tuple[str, ...] = (
    "autohaus", "autohauser", "autohandel", "autohandler", "autohaendler",
    "autowerkstatt", "gebrauchtwagen", "neuwagen", "jahreswagen", "vorfuhrwagen",
    "vorfuehrwagen", "gebrauchtfahrzeug", "neufahrzeug", "occasionen",
    "occasionsfahrzeug", "probefahrt", "autozentrum", "kfz",
    "concessionnaire", "carrosserie", "concessionaria", "carrozzeria", "autovetture",
    "concesionario", "automocion", "autobedrijf", "bedrijfswagen",
    "automobile", "automobiles", "automobili", "automobiel",
)
_AUTO_WEAK: tuple[str, ...] = (
    "auto", "autos", "fahrzeug", "fahrzeuge", "marken", "voiture", "voitures",
    "vehicule", "vehicules", "vettura", "vetture", "veicoli", "coche", "coches",
    "vehiculo", "vehiculos", "automovil", "automoviles", "seminuevo", "seminuevos",
    "voertuig", "voertuigen", "tweedehands", "cars", "car", "motors", "dealership",
    "vehicles", "vehicle", "automotive", "showroom", "dealer",
)
_STRONG_RE = re.compile(r"\b(" + "|".join(re.escape(w) for w in _AUTO_STRONG) + r")\b")
_WEAK_RE = re.compile(r"\b(" + "|".join(re.escape(w) for w in _AUTO_WEAK) + r")\b")


def _auto_ok(text: str) -> bool:
    """True if the visible text shows ≥1 strong OR ≥2 distinct weak automotive words."""
    if _STRONG_RE.search(text):
        return True
    return len(set(_WEAK_RE.findall(text))) >= 2
# Script/style CONTENT must be removed before text extraction — CSS/JS source is full
# of "auto" (sizes=auto, autocomplete, tracker vars) that otherwise fakes an automotive
# signal on butcher/optician/lawyer pages (the real cause of the directory false
# positives). Strip those blocks and HTML comments first, THEN tags.
_SCRIPT_STYLE_RE = re.compile(r"<(script|style|noscript|template|svg)\b[^>]*>.*?</\1>", re.I | re.S)
_COMMENT_RE = re.compile(r"<!--.*?-->", re.S)
_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


def _text(html: str, limit: int = 20000) -> str:
    """Visible-text only: drop script/style/comments, then tags → normalised lowercase."""
    h = html[:300000]                      # generous window: body text can follow big inline JS
    h = _SCRIPT_STYLE_RE.sub(" ", h)
    h = _COMMENT_RE.sub(" ", h)
    stripped = _TAG_RE.sub(" ", h)
    return _WS_RE.sub(" ", _norm(stripped))[:limit]


def confirms_dealer(html: str, name: str, city: str, *, require_name: bool = True) -> tuple[bool, str]:
    """
    True iff the homepage proves it is this dealer (pure). Per-via strictness.

    ``require_name=True`` (web search — noisy results): a distinctive NAME token MUST
    appear; city alone confirms only when the name is entirely generic/brand (else a
    same-city namesake passes — live: "ASTURHIBRIDO Gijón" matched an unrelated Gijón
    workshop via city alone).

    ``require_name=False`` (directory / email-domain — the candidate already carries
    name+city provenance from a matched listing or the dealer's own published address):
    name OR city is enough. Both modes still require ≥1 automotive signal.
    Returns (ok, reason) — reason names the failing half.
    """
    if not html or len(html) < 200:
        return False, "empty_page"
    text = _text(html)
    toks = name_tokens(name)
    name_hit = any(t in text for t in toks)
    city_n = _norm(city)
    city_hit = bool(city_n) and len(city_n) >= 3 and city_n in text
    auto_hit = _auto_ok(text)

    if require_name and toks:             # strict: distinctive name must be on the page
        if not name_hit:
            return False, "name_not_on_page"
        if not auto_hit:
            return False, "no_automotive_signal"
        return True, "name+auto"
    if not (name_hit or city_hit):        # lenient (or generic name): name|city fallback
        return False, "no_name_or_city"
    if not auto_hit:
        return False, "no_automotive_signal"
    return True, "name+auto" if name_hit else "city+auto"


def confirms_automotive(html: str) -> tuple[bool, str]:
    """
    Lightweight gate for the email-domain via: the email's apex is the dealer's own
    published address (strong provenance), so we only require the page to be a live
    automotive site (≥1 signal), not a name match. Guards against parked/empty pages.
    """
    if not html or len(html) < 200:
        return False, "empty_page"
    text = _text(html)
    if not _auto_ok(text):
        return False, "no_automotive_signal"
    return True, "email+auto"


async def _fetch_html(host: str, fetcher) -> tuple[str | None, str]:
    """Fetch a homepage → (html, reason). html is None on transport/HTTP failure."""
    url = f"https://{host}/"
    try:
        resp = await fetcher(url)
    except Exception as exc:  # noqa: BLE001 — unreachable candidate = not confirmed
        return None, f"fetch_error:{type(exc).__name__}"
    status = int(getattr(resp, "status_code", 0) or 0)
    if status and status >= 400:
        return None, f"http_{status}"
    html = getattr(resp, "text", None)
    if html is None:
        body = getattr(resp, "body", b"") or b""
        html = body.decode("utf-8", "replace") if isinstance(body, (bytes, bytearray)) else str(body)
    return html, "ok"


async def validate_domain(
    host: str, name: str, city: str, fetcher, *, require_name: bool = True,
) -> tuple[bool, str]:
    """
    Fetch ``host``'s homepage and confirm it is the dealer (strict by default; pass
    ``require_name=False`` for directory/email vias whose candidate already carries
    name+city provenance). ``fetcher(url) -> resp(.status_code,.text/.body)`` injected.
    """
    html, reason = await _fetch_html(host, fetcher)
    if html is None:
        return False, reason
    return confirms_dealer(html, name, city, require_name=require_name)


async def validate_automotive(host: str, fetcher) -> tuple[bool, str]:
    """Email-domain via: fetch homepage, require only that it is a live automotive site."""
    html, reason = await _fetch_html(host, fetcher)
    if html is None:
        return False, reason
    return confirms_automotive(html)
