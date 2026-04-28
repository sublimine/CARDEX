"""AutoScout24 ES. JSON pattern: "/anuncios/{slug}-{uuid}"."""
import asyncio
from scrapers.common.autoscout24 import run as _run

_CFG = {
    "source": "autoscout24_es",
    "country": "ES",
    "domain": "www.autoscout24.es",
    "base_url": "https://www.autoscout24.es",
    "search_base": "https://www.autoscout24.es/lst",
    "listing_json_re": r'"(/anuncios/[^"\\]{20,})"',
}

async def run(): await _run(_CFG)
if __name__ == "__main__": asyncio.run(run())
