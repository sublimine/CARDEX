"""
Adversarial count verifier (Bloque E, applied) — "CARDEX no vende mentiras" CLI.

Re-derives an entity's inventory count INDEPENDENTLY of the harvest pipeline (by counting
the source's own sitemap PDP entries, classified by the recipe's ``detail_url_re``), and —
when a ``--claim N`` is given — gates it via ``intelligence.count_verify.cross_check``.

This is the operator tool for the owner's mandate "re-derive every number by a 2nd method;
a count without an independent corroboration is not trustworthy." Read-only, no seam, fast.

    python -m scripts.verify_count dacia-meaux.fr:FR
    python -m scripts.verify_count dacia-meaux.fr:FR --claim 229
"""
from __future__ import annotations

import argparse
import asyncio
import sys

sys.path.insert(0, __import__("os").path.dirname(__import__("os").path.dirname(__import__("os").path.abspath(__file__))))

from scrapers.dealer_scraping.harvester import make_dealer_fetcher  # noqa: E402
from scrapers.intelligence import count_verify as cv  # noqa: E402
from scrapers.pipeline.generic_extractor import (  # noqa: E402
    _safe_fetch,
    decode_sitemap,
    discover_sitemap_candidates,
    looks_like_sitemap,
    is_sitemap_index,
    parse_sitemap_locs,
)
from scrapers.portals import config as portal_config  # noqa: E402


async def independent_sitemap_count(domain: str, detail_url_re: str, *, max_sitemaps: int = 100) -> int:
    """Distinct PDP URLs across all of a domain's sitemaps that match the recipe pattern.

    Walks sitemap-index children (bounded), counting <loc> matching ``detail_url_re`` with
    GLOBAL dedup — independent of our discover→seam path.
    """
    fetcher = make_dealer_fetcher()
    base = f"https://{domain}"
    queue = await discover_sitemap_candidates(base, fetcher)
    visited: set[str] = set()
    pdps: set[str] = set()
    expanded = 0
    while queue and expanded < max_sitemaps:
        url = queue.pop(0)
        if url in visited:
            continue
        visited.add(url)
        r = await _safe_fetch(fetcher, url)
        if r is None or r.status_code != 200:
            continue
        xml = decode_sitemap(r)
        if not looks_like_sitemap(xml):
            continue
        expanded += 1
        if is_sitemap_index(xml):
            for loc in parse_sitemap_locs(xml):
                if loc not in visited:
                    queue.append(loc)
            continue
        # one urlset's worth of PDP matches (count_pdp dedups within; we union globally)
        for loc in parse_sitemap_locs(xml):
            if detail_url_re and cv.count_pdp_in_sitemap(f"<loc>{loc}</loc>", detail_url_re):
                pdps.add(loc)
    return len(pdps)


async def main() -> int:
    ap = argparse.ArgumentParser(description="Adversarial independent count verifier (Bloque E)")
    ap.add_argument("domains", nargs="+", help="domain:CC ... (CC optional)")
    ap.add_argument("--claim", type=int, default=None, help="pipeline-claimed count to gate")
    ap.add_argument("--tolerance", type=float, default=0.02)
    args = ap.parse_args()

    rc = 0
    for spec in args.domains:
        domain = spec.split(":")[0].strip()
        cfg = portal_config.load(domain)
        detail_re = (cfg.endpoints.detail_url_re if cfg else "") or ""
        if not detail_re:
            print(f"{domain}: NO detail_url_re in recipe — cannot classify PDPs independently (skipped)")
            continue
        indep = await independent_sitemap_count(domain, detail_re)
        line = f"{domain}: independent sitemap PDP count = {indep} (detail_url_re={detail_re!r})"
        if args.claim is not None:
            verdict = cv.cross_check(args.claim, {"sitemap": indep}, tolerance=args.tolerance)
            tag = "TRUSTWORTHY" if verdict.trustworthy else "NOT-TRUSTWORTHY"
            line += f" | claim={args.claim} -> {tag} ({verdict.detail})"
            if not verdict.trustworthy:
                rc = 1
        print(line)
    return rc


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
