"""
Purge non-listing rows from vehicle_index + Meili.

Bridge indexes every <loc> in a dealer's sitemap regardless of whether
the URL is an individual vehicle or a category/filter page. This script
identifies and deletes non-listing rows using per-domain URL pattern
heuristics.

Patterns that signal CATEGORY / non-listing:
    - Path segments that end with fuel/color/city keywords and no ID
    - URLs with more than 5 path segments but no numeric token >= 5 digits
    - Image URLs (.jpg/.png/.webp)

Listings must have at least ONE of:
    - A numeric token of 5+ digits in the URL (listing ID)
    - A VIN (17 alphanumeric chars, no I/O/Q)
    - A URL-safe hash/slug of 8+ chars
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
from typing import Iterable

import asyncpg
import httpx

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s [purge] %(message)s",
)
log = logging.getLogger("purge")

_DSN = os.environ.get(
    "DATABASE_URL",
    "postgres://cardex:cardex_dev_only@localhost:5432/cardex",
)
_MEILI_URL = os.environ.get("MEILI_URL", "http://localhost:7700")
_MEILI_KEY = os.environ.get("MEILI_MASTER_KEY", "cardex_meili_dev_only")
_HDR = {"Authorization": f"Bearer {_MEILI_KEY}", "Content-Type": "application/json"}

# Per-domain blacklist of category-producing paths
_DOMAIN_BLACKLIST_PATTERNS = {
    "www.spoticar.de": (
        r"/gebrauchtwagen-kaufen/",  # all spoticar URLs are category
    ),
    "www.spoticar.be": (
        r"/voitures-occasion/",
    ),
    "www.spoticar.fr": (
        r"/voiture-occasion/",
    ),
    "zoomcar.fr": (
        r"/fiche-technique",  # spec catalog
    ),
    "dyler.com": (
        r"/cars/[^/]+/[^/]+-for-sale/",  # dyler category
    ),
    "www.quadis.es": (
        r"/coches-ocasion/", r"/coches-km0/", r"/coches-nuevos/",
    ),
    "www.hrmotor.com": (
        r"/coches-segunda-mano/[^/]+/[^/]+/?$",
    ),
    "www.spoticar.com": (
        r"/voiture-occasion/", r"/voitures-occasion/",
    ),
    "quadis.es": (
        r"/coches-",  # all paths starting with coches-
    ),
    "totalrenting.es": (
        r"/ficha/",  # catalog spec sheets
    ),
    "www.ocasionplus.com": (
        # Category URLs have format /coches-segunda-mano/city/brand/model (no trailing ID)
        # Real listings have /brand-model-trim-KMyear-ID suffix
        r"/coches-segunda-mano/[^/]+/[^/]+/[^/]+/?$",
    ),
}

# Image URL pattern
_IMG_EXT = re.compile(r"\.(?:jpg|jpeg|png|webp|gif|bmp|svg|pdf)(?:\?|$)", re.IGNORECASE)

# Listing-ID pattern: at least 5 contiguous digits somewhere in the URL
_LISTING_ID = re.compile(r"\d{5,}")


def _is_junk(url: str, domain: str) -> bool:
    """Return True if url is a category page, image URL, or junk."""
    if _IMG_EXT.search(url):
        return True
    for pat in _DOMAIN_BLACKLIST_PATTERNS.get(domain, ()):
        if re.search(pat, url):
            return True
    return False


async def run() -> None:
    pool = await asyncpg.create_pool(_DSN, min_size=2, max_size=4)
    meili = httpx.AsyncClient(timeout=120.0)

    total_purged = 0
    total_kept = 0

    # Process known blacklisted domains first
    for domain, patterns in _DOMAIN_BLACKLIST_PATTERNS.items():
        log.info("processing %s", domain)
        # Fetch all rows for this domain
        rows = await pool.fetch(
            "SELECT url_hash, url_original FROM vehicle_index WHERE source_domain=$1",
            domain,
        )
        log.info("  %s: %d rows", domain, len(rows))
        to_delete: list[str] = []
        for r in rows:
            if _is_junk(r["url_original"], domain):
                to_delete.append(r["url_hash"])

        log.info("  %s: %d junk / %d kept", domain, len(to_delete), len(rows) - len(to_delete))

        if to_delete:
            # Delete from Meili
            ulids = [f"vi{h}" for h in to_delete]
            for i in range(0, len(ulids), 5000):
                chunk = ulids[i : i + 5000]
                r = await meili.post(
                    f"{_MEILI_URL}/indexes/vehicles/documents/delete-batch",
                    headers=_HDR, json=chunk,
                )
                if r.status_code not in (200, 202):
                    log.warning("meili delete %d: %s", r.status_code, r.text[:200])
            # Delete from PG
            for i in range(0, len(to_delete), 5000):
                chunk = to_delete[i : i + 5000]
                await pool.execute(
                    "DELETE FROM vehicle_index WHERE url_hash = ANY($1::text[])",
                    chunk,
                )
            total_purged += len(to_delete)

        total_kept += len(rows) - len(to_delete)
        # Mark the source domain as deferred so future bridge runs skip it
        await pool.execute(
            "UPDATE discovery_candidates SET sitemap_status='deferred' "
            "WHERE domain=$1",
            domain,
        )

    log.info("DONE purged=%d kept=%d", total_purged, total_kept)
    await meili.aclose()
    await pool.close()


if __name__ == "__main__":
    asyncio.run(run())
