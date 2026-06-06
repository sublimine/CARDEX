"""Audit-cited reference facts for the CARDEX dashboard.

These are NOT fabricated numbers. They are facts extracted verbatim from the
verified audit (AUDIT_CARDEX_2026-06-06.md) and blueprint (BLUEPRINT_CARDEX.md),
each annotated with its source. They give the renderer context that cannot be
derived from a single live query (e.g. *why* a giant portal sits at zero, or
which round counts are known pagination caps).

Anything whose value is not verifiable (e.g. real market totals of giant
portals behind WAFs) is deliberately absent — the renderer shows "sin dato"
rather than inventing a denominator.
"""

from __future__ import annotations

COUNTRY_NAMES = {
    "DE": "Alemania",
    "FR": "Francia",
    "ES": "España",
    "NL": "Países Bajos",
    "BE": "Bélgica",
    "CH": "Suiza",
}

# Extraction strategy per producing portal (AUDIT §2.1, verbatim). Shown in the
# coverage table. Domains absent here render "—" (strategy not catalogued).
STRATEGY_BY_DOMAIN = {
    "autolina.ch": "API-JSON",
    "tutti.ch": "Next.js embebido",
    "viabovag.nl": "Next.js/data-route",
    "truckscout24.com": "sitemap-XML",
    "gaspedaal.nl": "JSON-LD",
    "anibis.ch": "Next.js (hereda tutti)",
    "autohero.com": "API-JSON",
    "vroom.be": "sitemap",
    "autotrack.nl": "curl_cffi pager",
    "ocasionplus.com": "API-JSON",
    "simplicicar.com": "sitemap",
    "marktplaats.nl": "API-móvil",
    "occasions.jeanlain.com": "sitemap",
    "distinxion.fr": "sitemap",
    "paruvendu.fr": "HTML",
    "comparis.ch": "Next.js",
    "2ememain.be": "API-móvil",
    "2dehands.be": "API-móvil",
    "clicars.com": "API-JSON",
    "gowago.ch": "API-JSON",
}

# Round counts confirmed as un-broken pagination caps (AUDIT §2.1).
# Maps source_domain -> the cap value observed. Rendered as an amber warning.
CAP_SUSPECTS = {
    "anibis.ch": 40000,
    "comparis.ch": 1000,
}

# Leading marketplaces sitting at 0 listings, blocked by the economic wall
# (no residential proxies → park on no_identity). AUDIT §2.2 [VERIFICADO].
# These are the bulk of the real European used-car market.
KNOWN_GIANTS = [
    {"portal": "mobile.de", "country": "DE", "wall": "T2 Akamai · sin proxy"},
    {"portal": "autoscout24.de", "country": "DE", "wall": "T2 Akamai · sin proxy"},
    {"portal": "autoscout24.fr", "country": "FR", "wall": "T2 Akamai · sin proxy"},
    {"portal": "autoscout24.es", "country": "ES", "wall": "T2 Akamai · sin proxy"},
    {"portal": "autoscout24.nl", "country": "NL", "wall": "T2 Akamai · sin proxy"},
    {"portal": "autoscout24.be", "country": "BE", "wall": "T2 Akamai · sin proxy"},
    {"portal": "autoscout24.ch", "country": "CH", "wall": "T2 Cloudflare · 403 datacenter"},
    {"portal": "leboncoin.fr", "country": "FR", "wall": "T3 DataDome · sin proxy"},
    {"portal": "coches.net", "country": "ES", "wall": "T3 DataDome · sin proxy"},
    {"portal": "milanuncios.com", "country": "ES", "wall": "T3 DataDome · sin proxy"},
    {"portal": "kleinanzeigen.de", "country": "DE", "wall": "T2 Akamai · sin proxy"},
    {"portal": "lacentrale.fr", "country": "FR", "wall": "T3 CF/Akamai · sin proxy"},
    {"portal": "wallapop.com", "country": "ES", "wall": "T0 PerimeterX · re-run pendiente"},
]

# Placeholder source platform value that means "no real rich record yet".
SEED_PLATFORMS = {"SEED_DEMO"}

# The pipeline stages the owner cares about, in order. The renderer computes the
# live status of each from collected metrics; this list fixes the names/order
# and the question each stage answers.
PIPELINE_STAGES = [
    {"key": "discovery", "label": "Discovery", "q": "¿Encontramos targets?"},
    {"key": "scraping", "label": "Scraping", "q": "¿Extraemos los portales?"},
    {"key": "index", "label": "Índice L1", "q": "¿Guardamos los punteros?"},
    {"key": "delta", "label": "Delta", "q": "¿Detectamos altas/bajas?"},
    {"key": "enrich", "label": "Enriquecido L2", "q": "¿Puntero → coche rico?"},
    {"key": "entity", "label": "Entidades", "q": "¿Deduplicamos dealers?"},
]
