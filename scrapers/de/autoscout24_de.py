"""AutoScout24 DE. Verified 2026-04-28: JSON "url":"/angebote/{slug}-{uuid}"."""
import asyncio
from scrapers.common.autoscout24 import run as _run

_CFG = {
    "source": "autoscout24_de",
    "country": "DE",
    "domain": "www.autoscout24.de",
    "base_url": "https://www.autoscout24.de",
    "search_base": "https://www.autoscout24.de/lst",
    "listing_json_re": r'"(/angebote/[^"\\]{20,})"',
}

async def run(): await _run(_CFG)
if __name__ == "__main__": asyncio.run(run())
