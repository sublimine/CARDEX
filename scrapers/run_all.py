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
    "autoscout24_de":   "de.autoscout24_de",
    "mobile_de":        "de.mobile_de",
    "kleinanzeigen_de": "de.kleinanzeigen_de",
    "heycar_de":        "de.heycar",
    "pkw_de":           "de.pkw_de",
    "automobile_de":    "de.automobile_de",
    "autohero_de":      "de.autohero",
    # ES
    "autoscout24_es":   "es.autoscout24_es",
    "coches_net":       "es.coches_net",
    "milanuncios":      "es.milanuncios",
    "wallapop":         "es.wallapop",
    "autocasion":       "es.autocasion",
    "motor_es":         "es.motor_es",
    "coches_com":       "es.coches_com",
    "flexicar":         "es.flexicar",
    # FR
    "autoscout24_fr":   "fr.autoscout24_fr",
    "leboncoin":        "fr.leboncoin",
    "lacentrale":       "fr.lacentrale",
    "paruvendu":        "fr.paruvendu",
    "largus_fr":        "fr.largus",
    "caradisiac_fr":    "fr.caradisiac",
    "ouestfrance_auto": "fr.ouestfrance_auto",
    # NL
    "autoscout24_nl":   "nl.autoscout24_nl",
    "marktplaats":      "nl.marktplaats",
    "autotrack":        "nl.autotrack",
    "gaspedaal":        "nl.gaspedaal",
    # BE
    "autoscout24_be":   "be.autoscout24_be",
    "2dehands":         "be.tweedehands",
    "gocar":            "be.gocar",
    # CH
    "autoscout24_ch":   "ch.autoscout24_ch",
    "tutti":            "ch.tutti",
    "comparis":         "ch.comparis",
    # Discovery / dealer spider
    "discovery":        "discovery.orchestrator",
    "dealer_spider":    "dealer_spider.spider",
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
