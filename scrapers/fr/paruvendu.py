"""paruvendu.fr — HTTP 404 on all known paths. Dead portal. Stub."""
import asyncio, logging
log = logging.getLogger(__name__)
async def run():
    log.warning("paruvendu: all known URLs return 404 — portal restructured/dead, skipping")
if __name__ == "__main__": asyncio.run(run())
