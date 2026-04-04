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
        "autoscout24_de":   "scrapers.de.autoscout24_de",
        "mobile_de":        "scrapers.de.mobile_de",
        "kleinanzeigen_de": "scrapers.de.kleinanzeigen_de",
        "heycar_de":        "scrapers.de.heycar",
        "pkw_de":           "scrapers.de.pkw_de",
        "automobile_de":    "scrapers.de.automobile_de",
        "autohero_de":      "scrapers.de.autohero",
        # ── ES portals ────────────────────────────────────────────────────────
        "autoscout24_es":   "scrapers.es.autoscout24_es",
        "coches_net":       "scrapers.es.coches_net",
        "milanuncios":      "scrapers.es.milanuncios",
        "wallapop":         "scrapers.es.wallapop",
        "autocasion":       "scrapers.es.autocasion",
        "motor_es":         "scrapers.es.motor_es",
        "coches_com":       "scrapers.es.coches_com",
        "flexicar":         "scrapers.es.flexicar",
        # ── FR portals ────────────────────────────────────────────────────────
        "autoscout24_fr":   "scrapers.fr.autoscout24_fr",
        "leboncoin":        "scrapers.fr.leboncoin",
        "lacentrale":       "scrapers.fr.lacentrale",
        "paruvendu":        "scrapers.fr.paruvendu",
        "largus_fr":        "scrapers.fr.largus",
        "caradisiac_fr":    "scrapers.fr.caradisiac",
        "ouestfrance_auto": "scrapers.fr.ouestfrance_auto",
        # ── NL portals ────────────────────────────────────────────────────────
        "autoscout24_nl":   "scrapers.nl.autoscout24_nl",
        "marktplaats":      "scrapers.nl.marktplaats",
        "autotrack":        "scrapers.nl.autotrack",
        "gaspedaal":        "scrapers.nl.gaspedaal",
        # ── BE portals ────────────────────────────────────────────────────────
        "autoscout24_be":   "scrapers.be.autoscout24_be",
        "2dehands":         "scrapers.be.tweedehands",
        "gocar":            "scrapers.be.gocar",
        # ── CH portals ────────────────────────────────────────────────────────
        "autoscout24_ch":   "scrapers.ch.autoscout24_ch",
        "tutti":            "scrapers.ch.tutti",
        "comparis":         "scrapers.ch.comparis",
        # ── Dealer discovery (7-layer orchestrator) ───────────────────────────
        "discovery":        "scrapers.discovery.orchestrator",
        "discovery_es":     "scrapers.discovery.orchestrator",
        "discovery_fr":     "scrapers.discovery.orchestrator",
        "discovery_de":     "scrapers.discovery.orchestrator",
        "discovery_nl":     "scrapers.discovery.orchestrator",
        "discovery_be":     "scrapers.discovery.orchestrator",
        "discovery_ch":     "scrapers.discovery.orchestrator",
        # ── Dealer website spider ─────────────────────────────────────────────
        "dealer_spider":    "scrapers.dealer_spider.spider",
        # ── Legacy Google Maps crawler (replaced by discovery) ────────────────
        "google_maps":      "scrapers.google_maps.crawler",
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
