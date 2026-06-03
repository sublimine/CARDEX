"""
HttpPortalScraper — shared HTTP scraping base for direct-HTTP portals.

Generalizes the AutoScout24 retry / soft-block / extraction loop to any portal
reachable with a single HTTP request per page — a GET against an HTML search
page or a JSON POST against a search API. A concrete portal therefore declares
only two facts:

  _build_request(params, page_num) → PortalRequest   how to ask for one page
  _extract(response)               → list[str]        how to pull deep links out

Everything cross-cutting — the retry-with-backoff loop, block-status handling
(403/429/503), WAF soft-block detection, transport-error tolerance — lives here,
identical in behaviour to autoscout24_base but request-shape-agnostic so it
serves GET-HTML and POST-JSON portals from one code path.

The search-grid helpers (YEAR_BANDS, PRICE_RANGES, split_price) give every
portal the same partition and the same cap-recovery subdivision. Unlike AS24's
*cumulative* price ceilings, PRICE_RANGES are *disjoint* [from, to) windows: a
car appears in exactly one segment, so segments do not overlap. A segment that
hits the page cap is recovered by halving its price window (split_price); the
open-ended top window (no upper bound) cannot be halved and is left as-is — an
accepted, declared limitation since inventory above the top ceiling is sparse.

Soft-block detection delegates to intelligence.waf.classify: a 200 response
whose body or headers carry a challenge signal (Cloudflare interstitial,
DataDome captcha host, …) is treated as a soft block — retried with a longer
backoff, never emitted as data. A portal whose WAF has a non-body tell (e.g.
Akamai's rejected sensor cookie, a vendor "access denied" page) overrides
_is_soft_block and adds that check on top of the default.

Like autoscout24_base, this module issues requests only through the duck-typed
`session`, so it imports and unit-tests without curl_cffi / a browser present.
"""
from __future__ import annotations

import asyncio
import logging
import random
from abc import abstractmethod
from dataclasses import dataclass
from itertools import product
from typing import Any

from scrapers.intelligence import waf
from scrapers.portals.base import BasePortalScraper

log = logging.getLogger(__name__)

# ── shared search grid ─────────────────────────────────────────────────────────
# The same 11 year bands AS24 uses (verified gold nugget), reused so every portal
# partitions inventory identically. Each band is an inclusive [from, to] year
# window; a portal maps it onto whatever first-registration filter it exposes.
YEAR_BANDS: tuple[tuple[int, int], ...] = (
    (1990, 2000), (2000, 2005), (2005, 2008), (2008, 2011),
    (2011, 2014), (2014, 2016), (2016, 2018), (2018, 2020),
    (2020, 2022), (2022, 2024), (2024, 2026),
)

# Disjoint price windows [from, to). The final window's `to` is None — open-ended,
# "everything above the top ceiling". Disjoint (not cumulative like AS24's
# price_to ceilings), so segments never overlap and a listing is counted once.
PRICE_RANGES: tuple[tuple[int, int | None], ...] = (
    (0, 5_000), (5_000, 10_000), (10_000, 15_000), (15_000, 20_000),
    (20_000, 30_000), (30_000, 50_000), (50_000, 100_000), (100_000, None),
)

# A price window is only worth halving if it is bounded and wider than this; below
# it, finer subdivision cannot meaningfully shrink a capped result set.
_MIN_SPLIT_WIDTH = 500


def split_price(price_from: int, price_to: int | None) -> list[tuple[int, int]]:
    """
    Halve a bounded price window into two disjoint sub-windows for cap recovery.

    Returns [] for an open-ended window (price_to is None — unbounded, cannot be
    split) or one no wider than _MIN_SPLIT_WIDTH (splitting finer cannot help).
    """
    if price_to is None or price_to - price_from <= _MIN_SPLIT_WIDTH:
        return []
    mid = (price_from + price_to) // 2
    return [(price_from, mid), (mid, price_to)]


@dataclass(frozen=True)
class PortalRequest:
    """
    One HTTP request for a page of a segment.

    GET by default; set json_body to issue a JSON POST instead. headers are
    per-request extras layered on top of the session's impersonated defaults
    (headers do not affect JA3, so this is safe to vary per request).
    """

    url: str
    method: str = "GET"
    json_body: dict[str, Any] | None = None
    headers: dict[str, str] | None = None


class HttpPortalScraper(BasePortalScraper):
    """
    Direct-HTTP portal base. A concrete portal sets DOMAIN / COUNTRY and the
    pagination knobs (PAGE_SIZE / MAX_PAGES), then implements _build_request and
    _extract. It inherits the year×price partition, the price-split subdivision,
    and the retry / soft-block / transport loop unchanged.
    """

    # ── HTTP / retry behaviour (overridable, AS24-equivalent defaults) ─────────
    RETRY_ATTEMPTS: int = 3
    RETRY_BACKOFF_BASE: float = 2.0          # seconds, exponentiated per attempt
    REQUEST_TIMEOUT: int = 20
    BLOCK_STATUSES: frozenset[int] = frozenset({403, 429, 503})
    SOFTBLOCK_BACKOFF_FACTOR: float = 2.0    # soft blocks back off harder than 4xx

    # ── search grid (overridable per portal) ──────────────────────────────────
    YEAR_BANDS: tuple[tuple[int, int], ...] = YEAR_BANDS
    PRICE_RANGES: tuple[tuple[int, int | None], ...] = PRICE_RANGES

    # ── primitives the concrete portal must provide ────────────────────────────
    @abstractmethod
    def _build_request(self, params: dict[str, Any], page_num: int) -> PortalRequest:
        """Build the request for one page of one segment."""
        ...

    @abstractmethod
    def _extract(self, response: Any) -> list[str]:
        """Pull deep-link URLs out of a 200 response. Dedup within the page."""
        ...

    # ── partition + subdivision (year × disjoint price window) ──────────────────
    def partition_params(self) -> list[dict[str, Any]]:
        """Year band × disjoint price window — one dict per non-overlapping segment."""
        return [
            {"year_from": yf, "year_to": yt, "price_from": pf, "price_to": pt}
            for (yf, yt), (pf, pt) in product(self.YEAR_BANDS, self.PRICE_RANGES)
        ]

    def subdivide_segment(self, params: dict[str, Any]) -> list[dict[str, Any]]:
        """Halve the segment's price window when it hits the page cap."""
        halves = split_price(params["price_from"], params["price_to"])
        return [{**params, "price_from": pf, "price_to": pt} for pf, pt in halves]

    # ── fetch one page (generalized AS24 retry loop) ────────────────────────────
    async def fetch_segment(
        self, session: Any, params: dict[str, Any], page_num: int
    ) -> list[str]:
        """Fetch one page; retry block statuses / soft blocks; return deep-link URLs."""
        request = self._build_request(params, page_num)
        for attempt in range(1, self.RETRY_ATTEMPTS + 1):
            response = await self._send(session, request)
            if response is None:
                await self._retry_backoff(attempt)
                continue

            status = response.status_code
            if status in self.BLOCK_STATUSES:
                log.debug("HTTP %d (%d/%d) %s", status, attempt, self.RETRY_ATTEMPTS, request.url[:80])
                await self._retry_backoff(attempt)
                continue
            if status != 200:
                log.debug("HTTP %d (no retry) %s", status, request.url[:80])
                return []

            if self._is_soft_block(response):
                log.warning("softblock (%d/%d) %s", attempt, self.RETRY_ATTEMPTS, request.url[:80])
                await self._retry_backoff(attempt, factor=self.SOFTBLOCK_BACKOFF_FACTOR)
                continue

            return self._extract(response)

        log.warning("all %d attempts failed: %s", self.RETRY_ATTEMPTS, request.url[:80])
        return []

    # ── soft-block detection (overridable, WAF-classifier default) ──────────────
    def _is_soft_block(self, response: Any) -> bool:
        """
        True when a 200 response is actually a WAF challenge (soft block).

        Delegates to intelligence.waf.classify over the body, headers and cookies;
        any challenge verdict (CF interstitial, DataDome captcha host, …) is a soft
        block. A portal whose WAF has a non-body tell overrides this and ORs in the
        extra signal — see mobile.de (Akamai access-denied) for the pattern.
        """
        verdict = waf.classify(
            status_code=200,
            headers=self._as_str_map(getattr(response, "headers", None)),
            cookies=self._as_str_map(getattr(response, "cookies", None)),
            body=self._response_text(response),
        )
        return verdict.challenge

    # ── transport ───────────────────────────────────────────────────────────────
    async def _send(self, session: Any, request: PortalRequest) -> Any | None:
        """Issue one request (GET or JSON POST); None on transport error to back off."""
        try:
            if request.method == "POST":
                return await session.post(
                    request.url,
                    json=request.json_body,
                    headers=request.headers,
                    timeout=self.REQUEST_TIMEOUT,
                )
            return await session.get(
                request.url, headers=request.headers, timeout=self.REQUEST_TIMEOUT
            )
        except Exception as exc:  # transport-level: DNS, reset, timeout, proxy drop
            log.debug("transport error %s: %s", request.url[:80], exc)
            return None

    async def _retry_backoff(self, attempt: int, factor: float = 1.0) -> None:
        """Exponential backoff, skipped on the final attempt (about to give up)."""
        if attempt < self.RETRY_ATTEMPTS:
            await asyncio.sleep(self.RETRY_BACKOFF_BASE**attempt * factor + random.uniform(0, 0.25))

    # ── response helpers ─────────────────────────────────────────────────────────
    @staticmethod
    def _response_text(response: Any) -> str:
        text = getattr(response, "text", "")
        return text if isinstance(text, str) else ""

    @staticmethod
    def _response_json(response: Any) -> Any:
        """Parse a JSON body; None when the response is not JSON (so callers no-op)."""
        try:
            return response.json()
        except Exception:
            return None

    @staticmethod
    def _as_str_map(obj: Any) -> dict[str, str]:
        """Coerce a headers/cookies-like object into a plain {str: str} mapping."""
        if not obj:
            return {}
        try:
            items = obj.items()
        except AttributeError:
            return {}
        return {str(k): str(v) for k, v in items}
