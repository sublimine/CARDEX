"""
Entry point: reads SCRAPER_TARGET env var and runs the matching scraper.
e.g. SCRAPER_TARGET=autoscout24_de runs scrapers/de/autoscout24_de.py

Portal scraper targets: autoscout24_de, mobile_de, coches_net, ...
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
        # ── Discovery orchestrator + workers ─────────────────────────────────
        "discovery":        "scrapers.discovery.orchestrator",
        "ddg_worker":       "scrapers.discovery.ddg_worker",
        "sitemap_resolver": "scrapers.discovery.sitemap_resolver",
        "sitemap_bridge":   "scrapers.discovery.sitemap_bridge",
    }

    module_path = target_map.get(target)
    if not module_path:
        print(
            f"ERROR: unknown SCRAPER_TARGET '{target}'.\n"
            f"Valid targets: {sorted(target_map.keys())}",
            file=sys.stderr,
        )
        sys.exit(1)

    log.info("scraper.starting", target=target, module=module_path)
    mod = importlib.import_module(module_path)
    asyncio.run(mod.run())


if __name__ == "__main__":
    main()
