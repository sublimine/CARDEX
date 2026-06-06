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

# Framing banner. The owner read low/red numbers as dashboard bugs; they are
# the real, broken state of a system under repair. This makes that explicit.
READ_ME_TITLE = "Cómo leer este panel"
READ_ME_BODY = (
    "Esto muestra el ESTADO REAL del sistema, hoy EN REPARACIÓN (plan de obra P0→P3 "
    "del blueprint). Una cifra baja, en ámbar o en rojo NO es un fallo del panel: es la "
    "foto honesta de lo que todavía falta cablear. Donde se conoce, cada número lleva su "
    "CAUSA y su OBJETIVO. Verde = ya funciona · Ámbar/Rojo = estado real a mejorar · "
    "Gris = sin datos o trabajo futuro."
)

# Targets ("objetivo") + root causes for the ugly-but-real metrics, so each red
# number reads as the real state to improve — never a panel bug. Targets from
# BLUEPRINT_CARDEX.md §12 (P0→P3); causes from AUDIT §2-4. Keyed by metric.
GOALS = {
    "vehicles_l2": {
        "target": "que `vehicles` crezca desde listings reales (no seed)",
        "cause": "el enrich_worker (puente P0-3) está cableado pero no se ejecuta en el host → las colas Redis están vacías y solo quedan 30 filas de demo",
        "ref": "P0-3",
    },
    "entities": {
        "target": "> 0 entidades · dealers multilingües dedupados",
        "cause": "la resolución de entidades (P0-4) aún no escribe en PostgreSQL",
        "ref": "P0-4",
    },
    "scraping": {
        "target": "los 71 portales produciendo",
        "cause": "los gigantes T2/T3 (mobile.de, AutoScout24×6, leboncoin…) parkean sin proxy residencial; es un bloqueo económico por diseño, no un fallo",
        "ref": "P3",
    },
    "disc_web": {
        "target": "> 15 % de candidatos con dominio web",
        "cause": "el 84 % son razones sociales del registro SIRENE (sin web) y el resolver razón-social→dominio aún no está orquestado",
        "ref": "P1-3",
    },
    "disc_crawled": {
        "target": "dealers crawleados > 0",
        "cause": "los 460 K candidatos siguen en sitemap_status='pending': la cadena de dealers (sitemap_resolver → bridge) no corre sostenida en el host",
        "ref": "P2-1",
    },
    "fr_monoculture": {
        "target": "FR < 50 % del discovery (los 6 países equilibrados)",
        "cause": "FR = 84 % por la fuente única SIRENE (360 K); el resto de países necesita OSM exhaustivo / OEM-locators / yellow-pages",
        "ref": "P1-1",
    },
    "giants": {
        "target": "gigantes > 0 listings",
        "cause": "sin proxies residenciales parkean en no_identity por diseño — muro económico, no bug del scraper",
        "ref": "P3-1",
    },
}

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
