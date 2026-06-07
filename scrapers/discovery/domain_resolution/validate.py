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

# Automotive signals across DE/FR/ES/NL/IT/EN — a dealer homepage carries several.
_AUTO_SIGNALS: tuple[str, ...] = (
    "fahrzeug", "gebrauchtwagen", "neuwagen", "autohaus", "werkstatt", "kfz",
    "occasion", "occasioni", "voiture", "vehicule", "vehicules", "concession",
    "carrosserie", "coche", "vehiculo", "vehiculos", "automovil", "taller",
    "auto", "automobile", "automobili", "veicoli", "showroom", "dealer",
    "haendler", "handler", "garage", "inventory", "voorraad", "bedrijfswagen",
    "leasing", "probefahrt", "test drive", "modelle", "modelos",
)
_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


def _text(html: str, limit: int = 20000) -> str:
    """Strip tags → normalised lowercase text (bounded, so a huge page stays cheap)."""
    stripped = _TAG_RE.sub(" ", html[: limit * 4])
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
    auto_hit = any(sig in text for sig in _AUTO_SIGNALS)

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
    if not any(sig in text for sig in _AUTO_SIGNALS):
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
