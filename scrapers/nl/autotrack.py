"""
autotrack.nl — delegates to sitemap_indexer.

Verified 2026-04-28: 219 public sitemaps by make accessible without WAF.
URL pattern: https://www.autotrack.nl/a/{make-model-fuel-year-id}
DPG Media WAF blocks all dynamic access; sitemap bypasses it.
"""
import asyncio
from scrapers.sitemap_indexer import run as _run

async def run(): await _run(countries=["NL"], sources=["autotrack"])
if __name__ == "__main__": asyncio.run(run())
