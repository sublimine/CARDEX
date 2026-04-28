"""AutoScout24 BE. JSON patterns: /annonces/ (FR) or /aanbod/ (NL)."""
import asyncio
from scrapers.common.autoscout24 import run as _run

_CFG = {
    "source": "autoscout24_be",
    "country": "BE",
    "domain": "www.autoscout24.be",
    "base_url": "https://www.autoscout24.be",
    "search_base": "https://www.autoscout24.be/lst",
    "listing_json_re": r'"(/(annonces|aanbod)/[^"\\]{20,})"',
}

async def run(): await _run(_CFG)
if __name__ == "__main__": asyncio.run(run())
