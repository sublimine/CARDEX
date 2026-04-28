"""AutoScout24 NL. JSON pattern: "/aanbod/{slug}-{uuid}"."""
import asyncio
from scrapers.common.autoscout24 import run as _run

_CFG = {
    "source": "autoscout24_nl",
    "country": "NL",
    "domain": "www.autoscout24.nl",
    "base_url": "https://www.autoscout24.nl",
    "search_base": "https://www.autoscout24.nl/lst",
    "listing_json_re": r'"(/aanbod/[^"\\]{20,})"',
}

async def run(): await _run(_CFG)
if __name__ == "__main__": asyncio.run(run())
