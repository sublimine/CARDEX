"""
Adversarial count verification — the "CARDEX no vende mentiras" gate (Bloque E).

Re-derives an entity's inventory count by methods INDEPENDENT of the primary harvest
pipeline, then gates: a published count must be corroborated by >=1 independent method
within tolerance, or it is treated as UNVERIFIED. This is the institutional form of the
ad-hoc check that caught the dacia 17-vs-229 sub-count (a 12x lie).

Design: pure functions over already-fetched content (sitemap XML, a listing page's HTML)
so the gate is deterministic and unit-testable. The network fetch is the caller's job
(reuse the harvest fetcher), keeping this layer side-effect-free and composable into the
verify path. Each method is INDEPENDENT of the pipeline's discover->seam count by design:
counting the source's own published artifacts, not our extraction.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from html import unescape
from typing import Iterator, Mapping

_LOC_RE = re.compile(r"<loc>\s*(.*?)\s*</loc>", re.IGNORECASE | re.DOTALL)
_JSONLD_RE = re.compile(
    r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
    re.IGNORECASE | re.DOTALL,
)
_JSONLD_TOTAL_KEYS = ("numberOfItems", "totalCount", "totalResults", "resultCount")


def count_pdp_in_sitemap(sitemap_xml: str, detail_url_re: str) -> int:
    """
    Distinct ``<loc>`` URLs whose path matches the recipe's detail-PDP pattern.

    Independent of the pipeline: counts the SOURCE's own sitemap entries, classified by
    the same ``detail_url_re`` the recipe pins (PDP vs catalog/CMS). Empty pattern → 0
    (no claim) rather than a misleading raw ``<loc>`` count.
    """
    if not detail_url_re:
        return 0
    rx = re.compile(detail_url_re)
    seen: set[str] = set()
    for m in _LOC_RE.finditer(sitemap_xml):
        url = unescape(m.group(1).strip())
        if url and rx.search(url):
            seen.add(url)
    return len(seen)


def _iter_jsonld(html: str) -> Iterator[dict]:
    for m in _JSONLD_RE.finditer(html):
        try:
            obj = json.loads(m.group(1).strip())
        except (ValueError, TypeError):
            continue
        stack = [obj]
        while stack:
            cur = stack.pop()
            if isinstance(cur, dict):
                yield cur
                graph = cur.get("@graph")
                if isinstance(graph, list):
                    stack.extend(graph)
            elif isinstance(cur, list):
                stack.extend(cur)


def count_jsonld_total(html: str) -> int | None:
    """
    Best-effort independent total from a listing page's JSON-LD, or None if absent.

    Reads the source's OWN declared total (``numberOfItems``/``totalCount``/…) or, failing
    that, the length of an ``itemListElement`` array — independent of our extraction.
    """
    best: int | None = None
    for obj in _iter_jsonld(html):
        for key in _JSONLD_TOTAL_KEYS:
            v = obj.get(key)
            n: int | None = None
            if isinstance(v, bool):
                continue
            if isinstance(v, (int, float)):
                n = int(v)
            elif isinstance(v, str) and v.strip().isdigit():
                n = int(v.strip())
            if n is not None and n > 0:
                best = n if best is None else max(best, n)
        items = obj.get("itemListElement")
        if isinstance(items, list) and len(items) > (best or 0):
            best = len(items)
    return best


@dataclass(frozen=True)
class CountVerdict:
    """Verdict of an adversarial cross-check of a primary count vs independent methods."""

    primary: int
    independent: Mapping[str, int]
    converged: bool
    max_divergence: float  # worst relative gap vs primary among USABLE (>0) methods
    detail: str

    @property
    def trustworthy(self) -> bool:
        """A count is trustworthy only when independently corroborated."""
        return self.converged


def cross_check(
    primary: int, independent: Mapping[str, int], *, tolerance: float = 0.02
) -> CountVerdict:
    """
    Gate a primary (pipeline) count against independent re-derivations.

    ``converged`` = at least one independent method is non-zero AND within ``tolerance``
    (relative to ``primary``). A count with no corroborating independent method is NOT
    trustworthy — the "no vende mentiras" gate. Methods reporting 0 are treated as
    "could not derive" and ignored for convergence (but still reported in ``detail``).
    ``max_divergence`` surfaces the WORST usable gap so a divergent method (e.g. an
    inflated marketing total) is never silently dropped.
    """
    usable = {k: v for k, v in independent.items() if v > 0}
    if primary <= 0 or not usable:
        reason = "primary is zero" if primary <= 0 else "no usable independent method"
        return CountVerdict(primary, dict(independent), False, 1.0, reason)
    divergences = {k: abs(v - primary) / max(primary, 1) for k, v in usable.items()}
    best = min(divergences.values())
    worst = max(divergences.values())
    converged = best <= tolerance
    detail = "; ".join(f"{k}={v} ({divergences[k] * 100:.1f}%)" for k, v in sorted(usable.items()))
    return CountVerdict(primary, dict(independent), converged, worst, detail)
