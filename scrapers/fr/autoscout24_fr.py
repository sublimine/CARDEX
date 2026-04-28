"""AutoScout24 FR. JSON pattern: "/annonces/{slug}-{uuid}"."""
import asyncio
from scrapers.common.autoscout24 import run as _run

_CFG = {
    "source": "autoscout24_fr",
    "country": "FR",
    "domain": "www.autoscout24.fr",
    "base_url": "https://www.autoscout24.fr",
    "search_base": "https://www.autoscout24.fr/lst",
    "listing_json_re": r'"(/annonces/[^"\\]{20,})"',
}

async def run(): await _run(_CFG)
if __name__ == "__main__": asyncio.run(run())
