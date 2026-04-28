"""
run_as24.py — AS24 sequential runner.

AutoScout24 protects all 6 country domains with Cloudflare. Running them
concurrently triggers bot detection: all requests return challenge pages (0 URLs).

Fix: run each AS24 country SEQUENTIALLY with a 10s cooldown between countries.
This prevents cross-domain fingerprint correlation by CF's bot detector.

Verified 2026-04-28: isolation test extracts 20 URLs/page correctly.
Concurrent test (6 simultaneous): 0 URLs across all countries.
"""
from __future__ import annotations

import asyncio
import importlib
import logging
import os
import time

import structlog

log = structlog.get_logger()

# Sequential order: largest markets first for maximum early coverage.
AS24_TARGETS = [
    "autoscout24_de",
    "autoscout24_fr",
    "autoscout24_es",
    "autoscout24_nl",
    "autoscout24_be",
    "autoscout24_ch",
]

_MODULE_MAP = {t: f"scrapers.{t.split('_')[1]}.{t}" for t in AS24_TARGETS}
# Overrides for non-matching module paths:
_MODULE_MAP["autoscout24_de"] = "scrapers.de.autoscout24_de"
_MODULE_MAP["autoscout24_fr"] = "scrapers.fr.autoscout24_fr"
_MODULE_MAP["autoscout24_es"] = "scrapers.es.autoscout24_es"
_MODULE_MAP["autoscout24_nl"] = "scrapers.nl.autoscout24_nl"
_MODULE_MAP["autoscout24_be"] = "scrapers.be.autoscout24_be"
_MODULE_MAP["autoscout24_ch"] = "scrapers.ch.autoscout24_ch"

CYCLE_WAIT = int(os.environ.get("CYCLE_WAIT_SECONDS", "3600"))
COUNTRY_COOLDOWN = 10  # seconds between AS24 countries to avoid CF cross-domain detection


async def _run_one(target: str) -> None:
    mod_path = _MODULE_MAP[target]
    try:
        mod = importlib.import_module(mod_path)
        log.info("as24.start", target=target)
        await mod.run()
        log.info("as24.done", target=target)
    except Exception as exc:
        log.error("as24.error", target=target, error=str(exc))


def main() -> None:
    cycle = 0
    while True:
        cycle += 1
        t0 = time.time()
        log.info("as24.cycle_start", cycle=cycle)
        for target in AS24_TARGETS:
            asyncio.run(_run_one(target))
            if target != AS24_TARGETS[-1]:
                log.info("as24.country_cooldown", seconds=COUNTRY_COOLDOWN)
                time.sleep(COUNTRY_COOLDOWN)
        elapsed = int(time.time() - t0)
        log.info("as24.cycle_complete", cycle=cycle, elapsed_s=elapsed)
        log.info("as24.sleeping", next_cycle_in_s=CYCLE_WAIT)
        time.sleep(CYCLE_WAIT)


if __name__ == "__main__":
    main()
