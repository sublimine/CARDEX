"""marktplaats.nl — covered by sitemap_indexer. Delegates."""
import asyncio
from scrapers.sitemap_indexer import run as _run

async def run(): await _run(countries=["NL"], sources=["marktplaats"])
if __name__ == "__main__": asyncio.run(run())
