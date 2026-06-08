"""
Fuzzy decision layer — deterministic heuristics first, local LLM only on doubt.

Three pipeline micro-decisions that the regex/heuristic layer leaves ambiguous:

  1. ``classify_is_car_dealer`` — refines the homepage anti-FP gate
     (``validate.confirms_dealer``). The heuristic decides the clear cases; the LLM
     is asked ONLY in the ambiguous band — where the heuristic passed on weak/
     body-shop-ish evidence (FP-prone) or rejected a real dealer on a name/city
     technicality (FN-prone). This is what lifts the ~92 % precision and kills the
     Artcar / body-shop / parts-shop false positives.
  2. ``extract_vehicle_fields`` — fills make/model/price/year the structured parser
     missed (chaotic HTML), only when fields are actually absent.
  3. ``disambiguate_domain`` — picks among domain candidates only when the top two
     are within a score margin (a real tie the deterministic scorer can't break).

Every LLM path is fail-open: Ollama unavailable / slow / garbled ⇒ the heuristic
verdict stands. Steady-state (clear cases) never calls the LLM, so it costs no
tokens and near-zero local compute.
"""
from __future__ import annotations

import dataclasses
import os
import re

from scrapers.discovery.domain_resolution.candidate import name_tokens
from scrapers.discovery.domain_resolution.validate import (
    _STRONG_RE,
    _auto_ok,
    _text,
    confirms_dealer,
)
from scrapers.llm.ollama_client import OllamaClient, get_client

# STRONG auto words that also fit a body/paint shop — they pass the heuristic gate
# but are FP-prone for "sells cars", so a heuristic-TRUE resting only on them is
# routed to the LLM for a second opinion.
_BODY_PARTS_STRONG = frozenset({"carrosserie", "carrozzeria"})

_MAX_PAGE_CHARS = 1500  # input cap → bounded latency + RAM (prompts stay small)

# Routing policy (env-overridable, per-call overridable):
#   "economy"  (default) — LLM only on the genuinely-weak band (city-only / weak-only /
#               body-parts-strong positives, + name/city-technicality negatives on an
#               automotive page). Lowest LLM volume; honours "LLM only on doubt".
#   "precision" — LLM verifies EVERY heuristic-positive too. Catches vocab-rich FPs the
#               regex cannot (e.g. a B2B auto-software firm full of "gebrauchtwagen").
#               Higher LLM volume.
#   "off"      — never call the LLM (pure heuristic).
_DEFAULT_MODE = os.environ.get("LLM_DECISION_MODE", "economy").lower()

_DEALER_SCHEMA = {
    "type": "object",
    "properties": {
        "is_car_dealer": {"type": "boolean"},
        "kind": {"type": "string"},
        "confidence": {"type": "number"},
    },
    "required": ["is_car_dealer", "kind", "confidence"],
}
# A ``kind`` label that itself means "car dealer" — used by the consistency guard to
# reject a self-contradictory LLM downgrade (is_car_dealer=False + kind="dealership").
_DEALERISH_KIND_RE = re.compile(
    r"dealer|dealership|concession|concesionario|concessionnaire|concessionaria|"
    r"autohaus|h[aä]ndler|sells? cars",
    re.I,
)
_DEALER_SYSTEM = (
    "You are a precise classifier that decides whether a business is a CAR DEALERSHIP "
    "that SELLS cars to the public. A body/paint shop (carrosserie), spare-parts shop, "
    "car rental, driving school, museum, or any unrelated business is NOT a car dealer. "
    "Output only the JSON object."
)


@dataclasses.dataclass(frozen=True)
class DealerVerdict:
    """Result of :func:`classify_is_car_dealer`."""

    is_dealer: bool
    source: str            # "heuristic" | "llm"
    reason: str            # heuristic reason, possibly suffixed with an llm note
    kind: str = ""         # LLM's category label when source == "llm"
    confidence: float = 0.0
    consulted_llm: bool = False


def _ambiguous(heur_ok: bool, reason: str, text: str, mode: str) -> bool:
    """Is this verdict in the band where the LLM second opinion is worth its cost?"""
    if mode == "off":
        return False
    if heur_ok:
        if mode == "precision":
            return True   # verify every positive — catches vocab-rich FPs the regex can't
        strong = set(_STRONG_RE.findall(text))
        only_body = bool(strong) and strong <= _BODY_PARTS_STRONG
        weak_only = not strong
        # economy: TRUE on city-only, weak-only, or body/parts-strong evidence is FP-prone.
        return reason == "city+auto" or weak_only or only_body
    # FALSE only worth re-checking when the page IS automotive but failed on a
    # name/city technicality (a real dealer the literal token match missed).
    return reason in ("name_not_on_page", "no_name_or_city") and _auto_ok(text)


def classify_is_car_dealer(
    html: str,
    name: str,
    city: str,
    *,
    require_name: bool = True,
    client: OllamaClient | None = None,
    mode: str | None = None,
) -> DealerVerdict:
    """
    Decide if ``html`` is a car dealer's homepage — heuristic first, LLM on doubt.

    The heuristic (``confirms_dealer``) decides clear accepts/rejects with zero LLM
    cost. Only the ambiguous band (see :func:`_ambiguous`, gated by ``mode``)
    consults the local LLM, which can downgrade a body-shop/parts/B2B FP or rescue a
    name-mismatch FN. Fail-open. ``mode`` defaults to ``LLM_DECISION_MODE`` env.
    """
    mode = (mode or _DEFAULT_MODE).lower()
    heur_ok, reason = confirms_dealer(html, name, city, require_name=require_name)

    # Hard rejects are never overturned (empty / declared non-dealer / no auto signal).
    if not heur_ok and reason in ("empty_page", "non_dealer_category", "no_automotive_signal"):
        return DealerVerdict(False, "heuristic", reason)

    text = _text(html)
    if not _ambiguous(heur_ok, reason, text, mode):
        return DealerVerdict(heur_ok, "heuristic", reason)

    cl = client or get_client()
    if not cl.available():
        return DealerVerdict(heur_ok, "heuristic", reason + "|llm_unavailable")

    excerpt = text[:_MAX_PAGE_CHARS]
    prompt = (
        f"Dealer candidate name: {name!r}\n"
        f"City: {city!r}\n"
        f"Homepage visible text (truncated):\n{excerpt}\n\n"
        "Is this business a car dealership that sells cars to the public?"
    )
    obj = cl.generate_json(prompt, system=_DEALER_SYSTEM, schema=_DEALER_SCHEMA, max_tokens=120)
    if not obj or "is_car_dealer" not in obj:
        return DealerVerdict(heur_ok, "heuristic", reason + "|llm_nores")
    is_dealer = bool(obj["is_car_dealer"])
    kind = str(obj.get("kind", ""))
    # Consistency guard: small models sometimes return is_car_dealer=False while
    # labelling the kind a "car dealership" — a self-contradiction. Never act on a
    # contradictory downgrade; keep the (well-founded) heuristic verdict instead.
    if heur_ok and not is_dealer and _DEALERISH_KIND_RE.search(kind):
        return DealerVerdict(heur_ok, "heuristic", reason + "|llm_inconsistent")
    try:
        conf = float(obj.get("confidence", 0) or 0)
    except (TypeError, ValueError):
        conf = 0.0
    if conf > 1.0:  # models often answer 0-100; normalise
        conf /= 100.0
    return DealerVerdict(
        is_dealer=is_dealer,
        source="llm",
        reason=reason + "|llm",
        kind=kind,
        confidence=conf,
        consulted_llm=True,
    )


# ── field extraction ────────────────────────────────────────────────────────────
_FIELDS_SCHEMA = {
    "type": "object",
    "properties": {
        "make": {"type": "string"},
        "model": {"type": "string"},
        "year": {"type": "integer"},
        "price": {"type": "number"},
    },
    "required": ["make", "model", "year", "price"],
}
_FIELDS_SYSTEM = (
    "You extract used-car listing fields from messy page text. Return only the JSON "
    "object. Use an empty string / 0 for any field you cannot find. Do not guess."
)
_CRITICAL_FIELDS = ("make", "model", "price", "year")


def extract_vehicle_fields(
    text: str,
    partial: dict,
    *,
    client: OllamaClient | None = None,
) -> dict:
    """
    Fill make/model/price/year the structured parser missed — LLM only if missing.

    ``partial`` is whatever the deterministic extractor produced. If all critical
    fields are present, the LLM is never called. Fail-open: returns ``partial``
    unchanged on any LLM fault. The result carries ``_llm_filled`` (list of fields
    the LLM supplied) for observability.
    """
    missing = [f for f in _CRITICAL_FIELDS if not partial.get(f)]
    if not missing:
        return dict(partial)

    cl = client or get_client()
    if not cl.available():
        return dict(partial)

    prompt = (
        "Extract the vehicle's make, model, year and price from this listing text. "
        "Unknown → empty/0.\n\n" + (text or "")[:_MAX_PAGE_CHARS]
    )
    obj = cl.generate_json(prompt, system=_FIELDS_SYSTEM, schema=_FIELDS_SCHEMA, max_tokens=120)
    if not obj:
        return dict(partial)

    out = dict(partial)
    filled: list[str] = []
    for f in missing:
        v = obj.get(f)
        if v not in (None, "", 0, 0.0):
            out[f] = v
            filled.append(f)
    if filled:
        out["_llm_filled"] = filled
    return out


# ── domain disambiguation ─────────────────────────────────────────────────────────
_CHOICE_SCHEMA = {
    "type": "object",
    "properties": {"domain": {"type": "string"}, "confidence": {"type": "number"}},
    "required": ["domain"],
}
_CHOICE_SYSTEM = (
    "You pick which domain most likely belongs to the named car dealer in the named "
    "city. Choose exactly one from the provided list. Output only the JSON object."
)


def disambiguate_domain(
    name: str,
    city: str,
    candidates: list[tuple[str, float]],
    *,
    margin: float = 0.10,
    client: OllamaClient | None = None,
) -> str | None:
    """
    Pick the dealer's domain among scored candidates — LLM only on a near-tie.

    ``candidates`` = ``[(domain, score), …]``. If empty → ``None``; if there is a
    single candidate or the top two differ by more than ``margin`` → the top scorer
    (no LLM). Only a genuine tie consults the LLM. Fail-open to the top scorer.
    """
    if not candidates:
        return None
    ranked = sorted(candidates, key=lambda c: -c[1])
    if len(ranked) == 1 or (ranked[0][1] - ranked[1][1]) > margin:
        return ranked[0][0]

    close = [d for d, s in ranked if ranked[0][1] - s <= margin][:5]
    cl = client or get_client()
    if not cl.available():
        return ranked[0][0]

    prompt = (
        f"Dealer name: {name!r}\nCity: {city!r}\n"
        f"Candidate domains: {close}\n\nWhich domain belongs to this dealer?"
    )
    obj = cl.generate_json(prompt, system=_CHOICE_SYSTEM, schema=_CHOICE_SCHEMA, max_tokens=60)
    if not obj or obj.get("domain") not in close:
        return ranked[0][0]
    return obj["domain"]


__all__ = [
    "DealerVerdict",
    "classify_is_car_dealer",
    "extract_vehicle_fields",
    "disambiguate_domain",
]
