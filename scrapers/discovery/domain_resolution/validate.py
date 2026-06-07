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


def confirms_dealer(html: str, name: str, city: str) -> tuple[bool, str]:
    """
    True iff the homepage proves it is this dealer (pure).

    A distinctive NAME token MUST appear on the page when the name has one. City
    alone confirms ONLY when the name is entirely generic/brand (no distinctive
    token), otherwise a same-city namesake passes (live: "ASTURHIBRIDO Gijón"
    matched an unrelated Gijón workshop via city alone). Either path also requires
    ≥1 automotive signal. Returns (ok, reason) — reason names the failing half.
    """
    if not html or len(html) < 200:
        return False, "empty_page"
    text = _text(html)
    toks = name_tokens(name)
    name_hit = any(t in text for t in toks)
    city_n = _norm(city)
    city_hit = bool(city_n) and len(city_n) >= 3 and city_n in text
    auto_hit = any(sig in text for sig in _AUTO_SIGNALS)

    if toks:                              # distinctive name → it must be on the page
        if not name_hit:
            return False, "name_not_on_page"
        if not auto_hit:
            return False, "no_automotive_signal"
        return True, "name+auto"
    if not city_hit:                      # generic/brand-only name → city fallback
        return False, "no_name_or_city"
    if not auto_hit:
        return False, "no_automotive_signal"
    return True, "city+auto"


async def validate_domain(host: str, name: str, city: str, fetcher) -> tuple[bool, str]:
    """
    Fetch ``host``'s homepage and confirm it is the dealer.

    ``fetcher(url) -> object with .status_code and .text/.body`` is injected (a
    curl_cffi session.get live; an in-memory map in tests). Transport faults and
    non-200s are treated as "unconfirmed" (the domain is not persisted).
    """
    url = f"https://{host}/"
    try:
        resp = await fetcher(url)
    except Exception as exc:  # noqa: BLE001 — unreachable candidate = not confirmed
        return False, f"fetch_error:{type(exc).__name__}"
    status = int(getattr(resp, "status_code", 0) or 0)
    if status and status >= 400:
        return False, f"http_{status}"
    html = getattr(resp, "text", None)
    if html is None:
        body = getattr(resp, "body", b"") or b""
        html = body.decode("utf-8", "replace") if isinstance(body, (bytes, bytearray)) else str(body)
    return confirms_dealer(html, name, city)
