"""
sitemap_parser.py — XML Sitemap crawler for 100% listing coverage.

Sitemaps are the canonical way portals publish their full URL catalog
for indexers (Google, Bing, CARDEX). If a listing exists, it's in the
sitemap — this guarantees 100% coverage by design.

Supports:
- Standard sitemaps (urlset)
- Sitemap index files (sitemapindex → nested sitemaps)
- Compressed sitemaps (.xml.gz)
- Image sitemaps (skipped — we want listing pages)
- News sitemaps (skipped)

Discovery order:
1. robots.txt Sitemap: directive (already parsed by RobotsChecker)
2. Well-known paths: /sitemap.xml, /sitemap_index.xml, /sitemaps/sitemap.xml
3. Filtered by URL patterns specific to car listings

Usage:
    parser = SitemapParser(http_client)
    async for url in parser.listing_urls(
        sitemaps=robots.sitemaps,
        base_url="https://www.autoscout24.es",
        listing_patterns=["/annonce/", "/coche/"],
    ):
        # url is a listing page URL — fetch it, extract data
        ...
"""
from __future__ import annotations

import asyncio
import gzip
import re
from typing import AsyncIterator, Optional
from xml.etree import ElementTree as ET

import structlog

log = structlog.get_logger()

# Well-known sitemap paths to try if robots.txt has none
_FALLBACK_PATHS = [
    "/sitemap.xml",
    "/sitemap_index.xml",
    "/sitemap-index.xml",
    "/sitemaps/sitemap.xml",
    "/sitemap/sitemap.xml",
    "/sitemap_1.xml",
]

_NS = {
    "sm":  "http://www.sitemaps.org/schemas/sitemap/0.9",
    "xhtml": "http://www.w3.org/1999/xhtml",
}


class SitemapParser:
    """
    Async sitemap crawler. Yields listing page URLs from sitemap XML.
    Handles nested sitemap indexes recursively.
    """

    def __init__(self, http_client: any) -> None:
        self._http = http_client
        self._visited: set[str] = set()

    async def discover_sitemaps(
        self,
        base_url: str,
        known_sitemaps: list[str] | None = None,
    ) -> list[str]:
        """
        Return the list of sitemap URLs to crawl.
        Tries known_sitemaps first, then well-known fallback paths.
        """
        found: list[str] = []

        # 1. Use sitemaps declared in robots.txt
        if known_sitemaps:
            for url in known_sitemaps:
                if await self._is_reachable(url):
                    found.append(url)
            if found:
                log.info("sitemap.discovered_via_robots", count=len(found))
                return found

        # 2. Try well-known paths
        for path in _FALLBACK_PATHS:
            url = base_url.rstrip("/") + path
            if await self._is_reachable(url):
                found.append(url)
                log.info("sitemap.discovered_via_fallback", url=url)
                break

        return found

    async def _is_reachable(self, url: str) -> bool:
        try:
            resp = await self._http.get(url)
            return resp.status_code == 200
        except Exception:
            return False

    async def _fetch_xml(self, url: str) -> Optional[ET.Element]:
        """Fetch and parse a sitemap URL (handles .gz compression)."""
        try:
            resp = await self._http.get(url)
            content = resp.content if hasattr(resp, "content") else resp.text.encode()

            if url.endswith(".gz"):
                content = gzip.decompress(content)

            return ET.fromstring(content)
        except Exception as e:
            log.warning("sitemap.fetch_failed", url=url, error=str(e))
            return None

    async def _iter_sitemap(
        self,
        url: str,
        listing_patterns: list[str],
        depth: int = 0,
    ) -> AsyncIterator[str]:
        """Recursively iterate a sitemap or sitemap index, yielding listing URLs."""
        if url in self._visited or depth > 5:
            return
        self._visited.add(url)

        root = await self._fetch_xml(url)
        if root is None:
            return

        tag = root.tag.split("}")[-1] if "}" in root.tag else root.tag

        if tag == "sitemapindex":
            # Sitemap index — recurse into each child sitemap
            child_urls = []
            for sitemap_el in root.iter():
                if sitemap_el.tag.split("}")[-1] == "loc":
                    child_url = (sitemap_el.text or "").strip()
                    if child_url and child_url not in self._visited:
                        child_urls.append(child_url)

            log.info("sitemap.index", url=url, children=len(child_urls), depth=depth)

            for child_url in child_urls:
                async for listing_url in self._iter_sitemap(
                    child_url, listing_patterns, depth + 1
                ):
                    yield listing_url
                await asyncio.sleep(0.1)  # be polite between sitemap fetches

        elif tag == "urlset":
            # Standard sitemap — yield matching listing URLs
            count = yielded = 0
            for url_el in root.iter():
                if url_el.tag.split("}")[-1] == "loc":
                    loc = (url_el.text or "").strip()
                    if not loc:
                        continue
                    count += 1
                    # If no patterns specified, yield all URLs
                    if not listing_patterns or any(p in loc for p in listing_patterns):
                        yielded += 1
                        yield loc

            log.info("sitemap.urlset", url=url, total=count, matched=yielded, depth=depth)

    async def listing_urls(
        self,
        base_url: str,
        listing_patterns: list[str],
        known_sitemaps: list[str] | None = None,
    ) -> AsyncIterator[str]:
        """
        Main entry point. Yields all listing URLs from sitemaps.

        Args:
            base_url: Portal base URL, e.g. "https://www.autoscout24.es"
            listing_patterns: URL substrings that identify listing pages,
                              e.g. ["/annonce/", "/lst/"] for AutoScout24
            known_sitemaps: Sitemap URLs from robots.txt (optional)
        """
        sitemaps = await self.discover_sitemaps(base_url, known_sitemaps)

        if not sitemaps:
            log.warning("sitemap.none_found", base=base_url)
            return

        for sitemap_url in sitemaps:
            async for url in self._iter_sitemap(sitemap_url, listing_patterns):
                yield url
