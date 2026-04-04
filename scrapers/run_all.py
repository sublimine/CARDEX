"""
run_all.py — CARDEX multi-scraper orchestrator.

Reads SCRAPER_TARGETS env var (comma-separated scraper names) and runs them
ALL concurrently as asyncio tasks. When all finish one full cycle, waits
CYCLE_WAIT_SECONDS (default 3600) and repeats indefinitely.

Each scraper already handles:
  - make × year exhaustive decomposition
  - incremental diff (cursor in Redis)
  - rate limiting & robots.txt compliance
  - gateway ingest with Bloom dedup

Usage:
  SCRAPER_TARGETS=autoscout24_de,mobile_de,kleinanzeigen_de python -m run_all
"""
from __future__ import annotations

import asyncio
import importlib
import os
import sys
import time

import structlog

log = structlog.get_logger()

TARGET_MAP: dict[str, str] = {
    # DE
    "autoscout24_de":   "scrapers.de.autoscout24_de",
    "mobile_de":        "scrapers.de.mobile_de",
    "kleinanzeigen_de": "scrapers.de.kleinanzeigen_de",
    "heycar_de":        "scrapers.de.heycar",
    "pkw_de":           "scrapers.de.pkw_de",
    "automobile_de":    "scrapers.de.automobile_de",
    "autohero_de":      "scrapers.de.autohero",
    # ES
    "autoscout24_es":   "scrapers.es.autoscout24_es",
    "coches_net":       "scrapers.es.coches_net",
    "milanuncios":      "scrapers.es.milanuncios",
    "wallapop":         "scrapers.es.wallapop",
    "autocasion":       "scrapers.es.autocasion",
    "motor_es":         "scrapers.es.motor_es",
    "coches_com":       "scrapers.es.coches_com",
    "flexicar":         "scrapers.es.flexicar",
    # FR
    "autoscout24_fr":   "scrapers.fr.autoscout24_fr",
    "leboncoin":        "scrapers.fr.leboncoin",
    "lacentrale":       "scrapers.fr.lacentrale",
    "paruvendu":        "scrapers.fr.paruvendu",
    "largus_fr":        "scrapers.fr.largus",
    "caradisiac_fr":    "scrapers.fr.caradisiac",
    "ouestfrance_auto": "scrapers.fr.ouestfrance_auto",
    # NL
    "autoscout24_nl":   "scrapers.nl.autoscout24_nl",
    "marktplaats":      "scrapers.nl.marktplaats",
    "autotrack":        "scrapers.nl.autotrack",
    "gaspedaal":        "scrapers.nl.gaspedaal",
    # BE
    "autoscout24_be":   "scrapers.be.autoscout24_be",
    "2dehands":         "scrapers.be.tweedehands",
    "gocar":            "scrapers.be.gocar",
    # CH
    "autoscout24_ch":   "scrapers.ch.autoscout24_ch",
    "tutti":            "scrapers.ch.tutti",
    "comparis":         "scrapers.ch.comparis",
    # Discovery / dealer spider
    "discovery":        "scrapers.discovery.orchestrator",
    "dealer_spider":    "scrapers.dealer_spider.spider",
}

CYCLE_WAIT = int(os.environ.get("CYCLE_WAIT_SECONDS", "3600"))


async def _run_one(target: str) -> None:
    module_path = TARGET_MAP.get(target)
    if not module_path:
        log.error("run_all.unknown_target", target=target, known=sorted(TARGET_MAP.keys()))
        return
    try:
        mod = importlib.import_module(module_path)
        log.info("run_all.scraper_start", target=target)
        await mod.run()
        log.info("run_all.scraper_done", target=target)
    except Exception as exc:
        log.error("run_all.scraper_error", target=target, error=str(exc))


async def run_cycle(targets: list[str]) -> None:
    await asyncio.gather(*[_run_one(t) for t in targets], return_exceptions=True)


def main() -> None:
    raw = os.environ.get("SCRAPER_TARGETS", "").strip()
    if not raw:
        print("ERROR: SCRAPER_TARGETS env var is required (comma-separated)", file=sys.stderr)
        sys.exit(1)

    targets = [t.strip() for t in raw.split(",") if t.strip()]
    log.info("run_all.init", targets=targets, cycle_wait_s=CYCLE_WAIT)

    cycle = 0
    while True:
        cycle += 1
        t0 = time.time()
        log.info("run_all.cycle_start", cycle=cycle, targets=targets)
        asyncio.run(run_cycle(targets))
        elapsed = int(time.time() - t0)
        log.info("run_all.cycle_complete", cycle=cycle, elapsed_s=elapsed)
        log.info("run_all.sleeping", next_cycle_in_s=CYCLE_WAIT)
        time.sleep(CYCLE_WAIT)


if __name__ == "__main__":
    main()
