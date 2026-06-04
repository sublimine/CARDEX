"""
Poison detection (D3) — Cloudflare AI-Labyrinth honeypot classifier.

A WAF under attack may serve an AI-Labyrinth page: a plausible-looking but
machine-generated document meant to waste a scraper's budget and poison its
dataset. SCRAPING_ENGINE.md §D3 enumerates seven independent signals; two or more
active signals (`POISON_THRESHOLD`) condemn the page.

`detect` is a pure function: every contextual fact it needs (whether the portal
always prints a price, whether this body was already seen at another URL) arrives
as a keyword argument, so the classifier is unit-testable without a live fetch.
The coordinator computes `body_hash` across a window of fetches and feeds the
`is_duplicate_body` verdict back in — signal 7 (identical HTML for distinct URLs)
cannot be judged from a single page in isolation.

This module is the single source of truth for poison signals; pipeline quality
GATE 2 imports `detect` rather than re-deriving the logic (intelligence → pipeline
import direction; `parse` is stdlib-only so no cycle forms).
"""
from __future__ import annotations

import hashlib
import re
from collections.abc import Sequence
from dataclasses import dataclass
from urllib.parse import urlparse

from scrapers.pipeline.parse import jsonld_types

# §D3: two or more active signals → reject.
POISON_THRESHOLD = 2

# Signal 2 — a genuine listing page is markup-heavy; a sub-15KB body is suspect.
MIN_HTML_BYTES = 15 * 1024

# Signal 3 — visible-text / total-markup ratio above this means prose with almost
# no structure (an article), not a listing dense with elements and attributes.
TEXT_RATIO_MAX = 0.8

# Signal 1 — schema.org article-family types never describe a vehicle listing.
_ARTICLE_TYPES = {"article", "blogposting", "newsarticle", "liveblogposting"}

# Signal 5 — images served from Cloudflare's own delivery network instead of the
# portal's CDN: the honeypot has no real media to point at.
_CF_IMAGE_HOSTS = (
    "imagedelivery.net",
    "cloudflarestorage.com",
    "cloudflare-ipfs.com",
    ".r2.dev",
)
_CF_PATH_MARKER = "/cdn-cgi/"

# Stable signal names — emitted in the verdict and used by metrics/telemetry.
SIG_ARTICLE_TYPE = "article_type"
SIG_TINY_HTML = "tiny_html"
SIG_TEXT_CODE_RATIO = "text_code_ratio"
SIG_PRICE_ABSENT = "price_absent"
SIG_CLOUDFLARE_IMAGES = "cloudflare_images"
SIG_VIN_ABSENT = "vin_absent"
SIG_DUPLICATE_BODY = "duplicate_body"

_SCRIPT_STYLE_RE = re.compile(r"<(script|style)\b[^>]*>.*?</\1>", re.IGNORECASE | re.DOTALL)
_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


@dataclass(frozen=True)
class PoisonVerdict:
    """Outcome of poison classification. `signals` lists every active signal name."""

    is_poison: bool
    signals: tuple[str, ...]
    score: int

    @property
    def reason(self) -> str:
        """Human-readable signal list for logs/DLQ, or 'clean' when nothing fired."""
        return ", ".join(self.signals) if self.signals else "clean"


def _visible_text(html: str) -> str:
    """Strip script/style blocks then all tags, collapsing whitespace to one space."""
    no_blocks = _SCRIPT_STYLE_RE.sub(" ", html)
    no_tags = _TAG_RE.sub(" ", no_blocks)
    return _WS_RE.sub(" ", no_tags).strip()


def _text_code_ratio(html: str) -> float:
    """visible-text length / total-markup length; 0.0 for an empty document."""
    if not html:
        return 0.0
    return len(_visible_text(html)) / len(html)


def _has_cloudflare_image(image_urls: Sequence[str]) -> bool:
    """True if any image is delivered from Cloudflare infra rather than the portal CDN."""
    for url in image_urls:
        if _CF_PATH_MARKER in url:
            return True
        host = urlparse(url).netloc.lower()
        if host and any(host == h.lstrip(".") or host.endswith(h) for h in _CF_IMAGE_HOSTS):
            return True
    return False


def body_hash(html: str) -> str:
    """
    32-hex-char content hash over the page's *visible text* (not raw bytes).

    Hashing visible text rather than the full markup makes the duplicate-body
    signal robust to per-request wrapper noise (nonces, timestamps, CSRF tokens):
    two honeypot pages with identical prose collide even if their shells differ.
    The coordinator stores recent hashes per portal and passes the comparison back
    in as `is_duplicate_body`.
    """
    return hashlib.sha256(_visible_text(html).encode("utf-8")).hexdigest()[:32]


def detect(
    html: str,
    *,
    image_urls: Sequence[str] = (),
    portal_always_prices: bool = False,
    price_present: bool = True,
    portal_always_vins: bool = False,
    vin_present: bool = True,
    is_duplicate_body: bool = False,
) -> PoisonVerdict:
    """
    Score the seven §D3 signals; `is_poison` when at least `POISON_THRESHOLD` fire.

    Signals 4 and 6 (price/VIN absent) only fire when the caller asserts the portal
    *always* carries that field — an absent price is poison-relevant only where its
    presence is the norm. Signal 7 is supplied pre-computed via `is_duplicate_body`.
    """
    signals: list[str] = []

    if jsonld_types(html) & _ARTICLE_TYPES:
        signals.append(SIG_ARTICLE_TYPE)
    if len(html.encode("utf-8")) < MIN_HTML_BYTES:
        signals.append(SIG_TINY_HTML)
    if _text_code_ratio(html) > TEXT_RATIO_MAX:
        signals.append(SIG_TEXT_CODE_RATIO)
    if portal_always_prices and not price_present:
        signals.append(SIG_PRICE_ABSENT)
    if _has_cloudflare_image(image_urls):
        signals.append(SIG_CLOUDFLARE_IMAGES)
    if portal_always_vins and not vin_present:
        signals.append(SIG_VIN_ABSENT)
    if is_duplicate_body:
        signals.append(SIG_DUPLICATE_BODY)

    score = len(signals)
    return PoisonVerdict(
        is_poison=score >= POISON_THRESHOLD,
        signals=tuple(signals),
        score=score,
    )
