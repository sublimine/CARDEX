"""AutoScout24 CH. JSON patterns: /annonces/ (FR) or /angebote/ (DE)."""
import asyncio
from scrapers.common.autoscout24 import run as _run

_CFG = {
    "source": "autoscout24_ch",
    "country": "CH",
    "domain": "www.autoscout24.ch",
    "base_url": "https://www.autoscout24.ch",
    "search_base": "https://www.autoscout24.ch/lst",
    "listing_json_re": r'"(/(annonces|angebote)/[^"\\]{20,})"',
}

async def run(): await _run(_CFG)
if __name__ == "__main__": asyncio.run(run())
