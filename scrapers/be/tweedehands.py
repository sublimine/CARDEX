"""2dehands.be — covered by sitemap_indexer. Delegates."""
import asyncio
from scrapers.sitemap_indexer import run as _run

async def run(): await _run(countries=["BE"], sources=["2dehands"])
if __name__ == "__main__": asyncio.run(run())
