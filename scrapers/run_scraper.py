"""
Entry point: reads SCRAPER_TARGET env var and runs the matching scraper.
e.g. SCRAPER_TARGET=autoscout24_de runs scrapers/de/autoscout24_de.py

Discovery targets:
  discovery          — full 7-layer dealer discovery (all countries)
  discovery_es/fr/de/nl/be/ch — single-country discovery

Portal scraper targets: autoscout24_de, mobile_de, coches_net, ...
Dealer spider:         dealer_spider
"""
import asyncio
import importlib
import os
import sys

import structlog

log = structlog.get_logger()


def main() -> None:
    target = os.environ.get("SCRAPER_TARGET", "").strip()
    if not target:
        print("ERROR: SCRAPER_TARGET env var is required", file=sys.stderr)
        sys.exit(1)

    target_map: dict[str, str] = {
        # ── DE portals ────────────────────────────────────────────────────────
        "autoscout24_de":   "de.autoscout24_de",
        "mobile_de":        "de.mobile_de",
        "kleinanzeigen_de": "de.kleinanzeigen_de",
        "heycar_de":        "de.heycar",
        "pkw_de":           "de.pkw_de",
        "automobile_de":    "de.automobile_de",
        "autohero_de":      "de.autohero",
        # ── ES portals ────────────────────────────────────────────────────────
        "autoscout24_es":   "es.autoscout24_es",
        "coches_net":       "es.coches_net",
        "milanuncios":      "es.milanuncios",
        "wallapop":         "es.wallapop",
        "autocasion":       "es.autocasion",
        "motor_es":         "es.motor_es",
        "coches_com":       "es.coches_com",
        "flexicar":         "es.flexicar",
        # ── FR portals ────────────────────────────────────────────────────────
        "autoscout24_fr":   "fr.autoscout24_fr",
        "leboncoin":        "fr.leboncoin",
        "lacentrale":       "fr.lacentrale",
        "paruvendu":        "fr.paruvendu",
        "largus_fr":        "fr.largus",
        "caradisiac_fr":    "fr.caradisiac",
        "ouestfrance_auto": "fr.ouestfrance_auto",
        # ── NL portals ────────────────────────────────────────────────────────
        "autoscout24_nl":   "nl.autoscout24_nl",
        "marktplaats":      "nl.marktplaats",
        "autotrack":        "nl.autotrack",
        "gaspedaal":        "nl.gaspedaal",
        # ── BE portals ────────────────────────────────────────────────────────
        "autoscout24_be":   "be.autoscout24_be",
        "2dehands":         "be.tweedehands",
        "gocar":            "be.gocar",
        # ── CH portals ────────────────────────────────────────────────────────
        "autoscout24_ch":   "ch.autoscout24_ch",
        "tutti":            "ch.tutti",
        "comparis":         "ch.comparis",
        # ── Dealer discovery (7-layer orchestrator) ───────────────────────────
        "discovery":        "discovery.orchestrator",
        "discovery_es":     "discovery.orchestrator",
        "discovery_fr":     "discovery.orchestrator",
        "discovery_de":     "discovery.orchestrator",
        "discovery_nl":     "discovery.orchestrator",
        "discovery_be":     "discovery.orchestrator",
        "discovery_ch":     "discovery.orchestrator",
        # ── Dealer website spider ─────────────────────────────────────────────
        "dealer_spider":    "dealer_spider.spider",
        # ── Legacy Google Maps crawler (replaced by discovery) ────────────────
        "google_maps":      "google_maps.crawler",
    }

    module_path = target_map.get(target)
    if not module_path:
        print(
            f"ERROR: unknown SCRAPER_TARGET '{target}'.\n"
            f"Valid targets: {sorted(target_map.keys())}",
            file=sys.stderr,
        )
        sys.exit(1)

    # Single-country discovery: inject DISCOVERY_COUNTRIES env
    if target.startswith("discovery_") and "_" in target[len("discovery_"):]:
        country = target.split("_", 1)[1].upper()
        os.environ.setdefault("DISCOVERY_COUNTRIES", country)

    log.info("scraper.starting", target=target, module=module_path)
    mod = importlib.import_module(module_path)
    asyncio.run(mod.run())


if __name__ == "__main__":
    main()
