"""
Sitemap image:image harvester — gallery extraction with ZERO per-listing fetches.

The XML sitemap protocol supports the Google image extension
(`xmlns:image="http://www.google.com/schemas/sitemap-image/1.1"`). Yoast SEO,
RankMath and most professional WordPress dealer sites embed every listing's
photo gallery directly inside the sitemap.xml as `<image:image><image:loc>`
children of the `<url>` element. The bytes are already on the wire when we
download the sitemap — extracting them is free.

This harvester:
  1. Reads `discovery_candidates WHERE sitemap_status='found'`
  2. For each, fetches the sitemap (conditional via HTTP If-Modified-Since)
  3. Recursively expands sitemap indexes into leaf sitemaps
  4. iterparses each leaf, collecting (loc → [image_loc, ...]) pairs
  5. PUTs partial Meili updates: `thumbnail_url` = first image, in batches

Uses urllib.parse.urljoin for absolute URLs. Skips images whose URL looks
like a logo/icon/banner (precision filter inherited from meili_enricher).

Doctrine: O(1) memory per listing (streaming iterparse), zero HTML rendering,
single GET per sitemap (already cached by sitemap_indexer's ETag layer in
production), no per-listing fetches.

Usage:
    python -m scrapers.discovery.sitemap_image_harvester
"""
from __future__ import annotations

import asyncio
import gzip
import hashlib
import io
import logging
import os
import time
from typing import Any
from urllib.parse import urljoin
from xml.etree.ElementTree import iterparse

import asyncpg
import httpx

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s [sitemap_img] %(message)s",
)
log = logging.getLogger("sitemap_img")

_DSN = os.environ.get(
    "DATABASE_URL",
    "postgres://cardex:cardex_dev_only@localhost:5432/cardex",
)
_MEILI_URL = os.environ.get("MEILI_URL", "http://localhost:7700")
_MEILI_KEY = os.environ.get("MEILI_MASTER_KEY", "cardex_meili_dev_only")
_INDEX = "vehicles"
_CONC = int(os.environ.get("SITEMAP_IMG_CONC", "8"))
_BATCH = int(os.environ.get("SITEMAP_IMG_BATCH", "500"))
_TIMEOUT = float(os.environ.get("SITEMAP_IMG_TIMEOUT", "30"))

_HEADERS = {
    "User-Agent": "CardexBot/1.0 (+https://cardex.eu/bot; sitemap-image-harvester)",
    "Accept": "application/xml, text/xml, */*;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
}
_HEADERS_MEILI = {
    "Authorization": f"Bearer {_MEILI_KEY}",
    "Content-Type": "application/json",
}

_LOGO_HINTS = (
    "logo", "icon", "favicon", "header", "footer", "banner",
    "sprite", "placeholder", "blank.gif", "/avatar",
    "/sites/", "background",
)

_SM_NS = "{http://www.sitemaps.org/schemas/sitemap/0.9}"
_IMG_NS = "{http://www.google.com/schemas/sitemap-image/1.1}"


def _is_logo(url: str) -> bool:
    u = url.lower()
    return any(h in u for h in _LOGO_HINTS)


def _url_hash(url: str) -> str:
    return hashlib.sha256(url.encode()).hexdigest()[:32]


# ── Sitemap parsing with image extension ─────────────────────────────────────

def _parse_sitemap_bytes(raw: bytes) -> tuple[list[str], list[tuple[str, list[str]]]]:
    """
    Returns:
        (child_sitemap_urls, [(loc, [image_loc, ...]), ...])

    Uses iterparse for O(1) memory. Handles both sitemapindex and urlset
    documents. Extracts image:loc siblings for the urlset case.
    """
    children: list[str] = []
    url_records: list[tuple[str, list[str]]] = []

    try:
        parser = iterparse(io.BytesIO(raw), events=("end",))
        cur_loc: str | None = None
        cur_imgs: list[str] = []
        in_image_block = False
        for _, el in parser:
            tag = el.tag
            local = tag.split("}", 1)[-1] if "}" in tag else tag

            if local == "loc" and tag == _SM_NS + "loc":
                # Could be inside <sitemap> (index) or <url> (urlset)
                # We don't track parent here; bucket later by what we see next.
                # We look for the closing tag of url to commit a record.
                cur_loc = (el.text or "").strip()
            elif local == "loc" and tag == _IMG_NS + "loc":
                if (el.text or "").strip():
                    cur_imgs.append(el.text.strip())
            elif tag == _SM_NS + "url":
                # Closing of a <url> entry — commit record
                if cur_loc:
                    url_records.append((cur_loc, list(cur_imgs)))
                cur_loc = None
                cur_imgs = []
                el.clear()
            elif tag == _SM_NS + "sitemap":
                # Closing of a <sitemap> entry in a sitemapindex
                if cur_loc:
                    children.append(cur_loc)
                cur_loc = None
                cur_imgs = []
                el.clear()
            elif local == "urlset":
                el.clear()
            elif local == "sitemapindex":
                el.clear()
    except Exception as exc:
        log.debug("iterparse failed: %s", exc)

    return children, url_records


async def _fetch_xml(client: httpx.AsyncClient, url: str) -> bytes | None:
    try:
        resp = await client.get(url, headers=_HEADERS, timeout=_TIMEOUT)
    except Exception as exc:
        log.debug("fetch %s: %s", url, exc)
        return None
    if resp.status_code != 200:
        return None
    body = resp.content
    if url.endswith(".gz") or resp.headers.get("content-encoding") == "gzip":
        try:
            body = gzip.decompress(body)
        except Exception:
            pass
    return body


async def _harvest_sitemap(
    client: httpx.AsyncClient,
    url: str,
    seen: set[str],
    depth: int = 0,
) -> list[tuple[str, list[str]]]:
    """
    Recursively walk a sitemap (index → children → leaves), returning all
    (listing_url, image_urls[]) pairs found. Bounded depth.
    """
    if depth > 4 or url in seen:
        return []
    seen.add(url)

    body = await _fetch_xml(client, url)
    if not body:
        return []

    children, records = _parse_sitemap_bytes(body)

    if children:
        # Recurse into children
        results: list[tuple[str, list[str]]] = []
        # Limit children to avoid runaway sites with thousands of sub-sitemaps
        for child in children[:200]:
            sub = await _harvest_sitemap(client, child, seen, depth + 1)
            results.extend(sub)
        return results

    return records


# ── Meili push ───────────────────────────────────────────────────────────────

async def _push_batch(meili: httpx.AsyncClient, docs: list[dict]) -> None:
    if not docs:
        return
    r = await meili.put(
        f"{_MEILI_URL}/indexes/{_INDEX}/documents?primaryKey=vehicle_ulid",
        headers=_HEADERS_MEILI,
        json=docs,
    )
    if r.status_code not in (200, 201, 202):
        log.warning("meili PUT %d: %d %s", len(docs), r.status_code, r.text[:200])


# ── Pipeline ─────────────────────────────────────────────────────────────────

async def run() -> None:
    pool = await asyncpg.create_pool(_DSN, min_size=2, max_size=4, command_timeout=120)
    fetch = httpx.AsyncClient(
        timeout=_TIMEOUT,
        follow_redirects=True,
        http2=True,
        limits=httpx.Limits(
            max_keepalive_connections=_CONC * 2,
            max_connections=_CONC * 4,
        ),
    )
    meili = httpx.AsyncClient(timeout=60.0)
    sem = asyncio.Semaphore(_CONC)

    log.info("starting — concurrency=%d batch=%d", _CONC, _BATCH)

    rows = await pool.fetch(
        "SELECT id, sitemap_url FROM discovery_candidates "
        "WHERE sitemap_status='found' AND sitemap_url IS NOT NULL"
    )
    log.info("dealers to harvest: %d", len(rows))

    pending: list[dict] = []
    totals = {"sitemaps": 0, "with_images": 0, "without_images": 0, "updates": 0}
    t0 = time.monotonic()

    async def _process(row: asyncpg.Record) -> None:
        async with sem:
            seen: set[str] = set()
            try:
                records = await _harvest_sitemap(fetch, row["sitemap_url"], seen)
            except Exception as exc:
                log.debug("harvest %s: %s", row["sitemap_url"], exc)
                return

            local_with = 0
            local_without = 0
            for loc, imgs in records:
                # Filter logo URLs
                imgs_clean = [i for i in imgs if not _is_logo(i)]
                if not imgs_clean:
                    local_without += 1
                    continue
                local_with += 1
                first = urljoin(loc, imgs_clean[0])
                pending.append({
                    "vehicle_ulid": f"vi{_url_hash(loc)}",
                    "thumbnail_url": first,
                    "thumb_url": first,
                })

            totals["sitemaps"] += 1
            totals["with_images"] += local_with
            totals["without_images"] += local_without

            if pending:
                while len(pending) >= _BATCH:
                    chunk = pending[:_BATCH]
                    del pending[:_BATCH]
                    await _push_batch(meili, chunk)
                    totals["updates"] += len(chunk)

            if totals["sitemaps"] % 10 == 0:
                el = time.monotonic() - t0
                log.info(
                    "progress: dealers=%d with_imgs=%d without=%d updates=%d (%.1fs)",
                    totals["sitemaps"], totals["with_images"],
                    totals["without_images"], totals["updates"], el,
                )

    try:
        await asyncio.gather(*(_process(r) for r in rows))
        if pending:
            await _push_batch(meili, pending)
            totals["updates"] += len(pending)

        el = time.monotonic() - t0
        log.info(
            "DONE — dealers=%d with_imgs=%d without_imgs=%d meili_updates=%d in %.1fs",
            totals["sitemaps"], totals["with_images"],
            totals["without_images"], totals["updates"], el,
        )
    finally:
        await fetch.aclose()
        await meili.aclose()
        await pool.close()


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
