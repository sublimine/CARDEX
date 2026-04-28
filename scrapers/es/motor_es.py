"""motor.es — HTTP 410 Gone. Dead portal. Stub that logs and returns empty."""
import asyncio, logging
from scrapers.common.indexer import run_portal

log = logging.getLogger(__name__)

async def run():
    log.warning("motor_es: HTTP 410 Gone — portal defunct, skipping")

if __name__ == "__main__": asyncio.run(run())
