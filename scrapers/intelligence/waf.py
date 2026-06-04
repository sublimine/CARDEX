"""
WAF classifier (D1) — identify a new domain's anti-bot vendor from one response.

SCRAPING_ENGINE.md §D1 fingerprints the vendor from HTTP signals: a CF-Ray header
is Cloudflare, an `x-datadome-*` header is DataDome, an `ak_bmsc` cookie confirms
Akamai, a "Just a moment" body is a Cloudflare interstitial. `classify` folds
those rules into one pure verdict so the coordinator can pick a starting tier for
a domain not yet in the registry, and `diag.py` can re-confirm in verbose mode.

`WafVendor` is a coarse *vendor* taxonomy, deliberately distinct from
`router.domain_map.WAF` (which distinguishes CF_FREE/CF_PRO/CF_BUSINESS). Response
headers reveal the vendor but not its plan, so conflating the two would invite a
false-precision claim the signals cannot support.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum

# Status codes a WAF returns when it blocks or challenges rather than serves.
_BLOCK_CODES = frozenset({403, 429, 503})

# Body fragments that betray an interactive challenge page (all lowercased).
_CHALLENGE_MARKERS = (
    "just a moment",                # Cloudflare interstitial
    "attention required",           # Cloudflare block
    "checking your browser",        # Cloudflare / generic JS challenge
    "enable javascript and cookies",
    "/cdn-cgi/challenge-platform",  # Cloudflare Turnstile/managed challenge
    "captcha-delivery.com",         # DataDome CAPTCHA host
    "px-captcha",                   # PerimeterX challenge
)


class WafVendor(str, Enum):
    """Anti-bot vendor identified from response signals (coarser than router.WAF)."""

    NONE = "none"
    CLOUDFLARE = "cloudflare"
    DATADOME = "datadome"
    AKAMAI = "akamai"
    PERIMETER_X = "perimeter_x"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class WafVerdict:
    """Result of classifying one response. `level` ∈ none/medium/high."""

    vendor: WafVendor
    active: bool
    level: str
    challenge: bool
    signals: tuple[str, ...]


def _cookie_names(cookies: Mapping[str, str] | None, set_cookie: str) -> set[str]:
    """Lowercased cookie names from both an explicit dict and any Set-Cookie header."""
    names: set[str] = set()
    if cookies:
        names |= {k.lower() for k in cookies}
    # Set-Cookie may stack multiple cookies; we only need their names.
    for chunk in set_cookie.split(","):
        name = chunk.split("=", 1)[0].strip().lower()
        if name:
            names.add(name)
    return names


def _detect_vendor(hdr: Mapping[str, str], cookie_names: set[str], body_lc: str) -> tuple[WafVendor, list[str]]:
    """Return the most specific vendor the signals support, plus the signal names."""
    signals: list[str] = []
    vendor = WafVendor.NONE

    server = hdr.get("server", "").lower()

    # Cloudflare — CF-Ray is definitive; server/cookies/body corroborate.
    if "cf-ray" in hdr or "cf-mitigated" in hdr or "cloudflare" in server:
        vendor = WafVendor.CLOUDFLARE
        signals.append("cf_header")
    if {"__cf_bm", "cf_clearance"} & cookie_names:
        vendor = WafVendor.CLOUDFLARE
        signals.append("cf_cookie")

    # DataDome — dedicated header or cookie.
    if any(k.startswith("x-datadome") for k in hdr) or "datadome" in cookie_names:
        vendor = WafVendor.DATADOME
        signals.append("datadome")

    # Akamai Bot Manager — the _abck / ak_bmsc / bm_sz cookie triad.
    if {"ak_bmsc", "_abck", "bm_sz"} & cookie_names or "akamaighost" in server:
        vendor = WafVendor.AKAMAI
        signals.append("akamai")

    # PerimeterX / HUMAN — _px* cookies or x-px headers.
    if {"_px", "_pxhd", "_pxvid"} & cookie_names or any(k.startswith("x-px") for k in hdr):
        vendor = WafVendor.PERIMETER_X
        signals.append("perimeter_x")

    # Vendor-specific body markers refine an otherwise unknown block page.
    if "captcha-delivery.com" in body_lc:
        vendor = WafVendor.DATADOME
        signals.append("datadome_body")
    elif "/cdn-cgi/challenge-platform" in body_lc or "just a moment" in body_lc:
        if vendor is WafVendor.NONE:
            vendor = WafVendor.CLOUDFLARE
        signals.append("cf_body")

    return vendor, signals


def classify(
    *,
    status_code: int,
    headers: Mapping[str, str],
    cookies: Mapping[str, str] | None = None,
    body: str = "",
) -> WafVerdict:
    """
    Classify a single response into a WAF verdict (SCRAPING_ENGINE.md §D1).

    An immediate block code (403/429/503) marks the WAF active at `high` even when
    no vendor header is present — step 1's "403 inmediato → nivel=high". A vendor
    detected on a clean 200 is `medium`: present and watching, but not challenging.
    """
    hdr = {k.lower(): v for k, v in headers.items()}
    set_cookie = hdr.get("set-cookie", "")
    cookie_names = _cookie_names(cookies, set_cookie)
    body_lc = body.lower()

    vendor, signals = _detect_vendor(hdr, cookie_names, body_lc)

    body_challenge = any(marker in body_lc for marker in _CHALLENGE_MARKERS)
    blocked = status_code in _BLOCK_CODES
    challenge = body_challenge or blocked
    if blocked:
        signals.append(f"status_{status_code}")
    if body_challenge:
        signals.append("challenge_body")

    active = vendor is not WafVendor.NONE or challenge
    if not active:
        level = "none"
    elif challenge:
        level = "high"
    else:
        level = "medium"

    # An active challenge with no vendor signal is still a WAF — just unidentified.
    if active and vendor is WafVendor.NONE:
        vendor = WafVendor.UNKNOWN

    return WafVerdict(
        vendor=vendor,
        active=active,
        level=level,
        challenge=challenge,
        signals=tuple(signals),
    )
