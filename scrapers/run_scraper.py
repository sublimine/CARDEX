"""
Entry point: reads SCRAPER_TARGET env var and runs the matching scraper.
e.g. SCRAPER_TARGET=autoscout24_de runs scrapers/de/autoscout24_de.py
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

    # Map target → module path
    # Convention: scraper file must expose async run() coroutine
    target_map: dict[str, str] = {
        # DE
        "autoscout24_de": "de.autoscout24_de",
        "mobile_de": "de.mobile_de",
        "kleinanzeigen_de": "de.kleinanzeigen_de",
        # ES
        "autoscout24_es": "es.autoscout24_es",
        "coches_net": "es.coches_net",
        "milanuncios": "es.milanuncios",
        "wallapop": "es.wallapop",
        "autocasion": "es.autocasion",
        # FR
        "autoscout24_fr": "fr.autoscout24_fr",
        "leboncoin": "fr.leboncoin",
        "lacentrale": "fr.lacentrale",
        "paruvendu": "fr.paruvendu",
        # NL
        "autoscout24_nl": "nl.autoscout24_nl",
        "marktplaats": "nl.marktplaats",
        "autotrack": "nl.autotrack",
        "gaspedaal": "nl.gaspedaal",
        # BE
        "autoscout24_be": "be.autoscout24_be",
        "2dehands": "be.tweedehands",
        "gocar": "be.gocar",
        # CH
        "autoscout24_ch": "ch.autoscout24_ch",
        "tutti": "ch.tutti",
        "comparis": "ch.comparis",
        # Discovery
        "google_maps": "google_maps.crawler",
    }

    module_path = target_map.get(target)
    if not module_path:
        print(f"ERROR: unknown SCRAPER_TARGET '{target}'. Valid targets: {list(target_map)}", file=sys.stderr)
        sys.exit(1)

    log.info("scraper.starting", target=target, module=module_path)
    mod = importlib.import_module(module_path)
    asyncio.run(mod.run())


if __name__ == "__main__":
    main()
